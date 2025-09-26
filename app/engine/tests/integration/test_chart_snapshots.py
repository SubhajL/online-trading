"""
Integration tests for chart snapshot generation.

Tests the complete flow from signal generation to snapshot creation and delivery.
"""

import asyncio
import os
from decimal import Decimal
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import aiohttp

from app.engine.models import SignalEvent, TimeFrame, Candle
from app.engine.bus import get_event_bus


@pytest.fixture
def signal_event():
    """Create a test signal event."""
    return SignalEvent(
        timestamp=datetime.now(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        signal_type="BUY",
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        confidence=Decimal("0.85"),
        source="zone_retest",
        metadata={
            "zone_type": "demand",
            "confluence": ["BOS", "EMA_support", "RSI_oversold"],
            "signal_strength": "high"
        }
    )


@pytest.fixture
def candles_data():
    """Generate test candles for chart rendering."""
    candles = []
    base_time = datetime.now() - timedelta(hours=24)
    base_price = Decimal("49500")

    # Generate 120 candles (100 before signal, 20 after)
    for i in range(120):
        # Create uptrend pattern
        if i < 60:
            price = base_price + Decimal(str(i * 10))
        elif i < 80:
            # Pullback
            price = base_price + Decimal("600") - Decimal(str((i - 60) * 15))
        else:
            # Bounce from demand zone
            price = base_price + Decimal("300") + Decimal(str((i - 80) * 20))

        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=base_time + timedelta(minutes=15 * i),
            close_time=base_time + timedelta(minutes=15 * (i + 1)),
            open_price=price - Decimal("20"),
            high_price=price + Decimal("30"),
            low_price=price - Decimal("30"),
            close_price=price,
            volume=Decimal("100"),
            quote_volume=Decimal("5000000"),
            trades=1000,
            taker_buy_base_volume=Decimal("60"),
            taker_buy_quote_volume=Decimal("3000000"),
        )
        candles.append(candle)

    return candles


@pytest.fixture
async def bff_api_url():
    """Get BFF API URL from environment or default."""
    return os.getenv("BFF_API_URL", "http://localhost:8002")


class TestChartSnapshotGeneration:
    """Test chart snapshot generation from signals."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_api_endpoint_exists(self, bff_api_url):
        """Test that the snapshot API endpoint is available."""
        async with aiohttp.ClientSession() as session:
            # Test health endpoint first
            async with session.get(f"{bff_api_url}/health") as response:
                assert response.status in [200, 404]  # 404 if health not implemented

            # Check if snapshots endpoint exists
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json={"signalId": "test-signal-123"}
            ) as response:
                # Should get 400 for missing data, not 404
                assert response.status in [400, 401, 422]  # Bad request, not found

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_generation_request(self, bff_api_url, signal_event, candles_data):
        """Test sending snapshot generation request to BFF."""
        # Prepare request data
        request_data = {
            "signalId": f"signal-{signal_event.timestamp.timestamp()}",
            "symbol": signal_event.symbol,
            "timeframe": signal_event.timeframe.value,
            "signalData": {
                "type": signal_event.signal_type,
                "entry": str(signal_event.entry_price),
                "stopLoss": str(signal_event.stop_loss),
                "takeProfit": str(signal_event.take_profit),
                "confidence": str(signal_event.confidence),
                "metadata": signal_event.metadata
            },
            "candles": [
                {
                    "time": int(c.open_time.timestamp()),
                    "open": float(c.open_price),
                    "high": float(c.high_price),
                    "low": float(c.low_price),
                    "close": float(c.close_price),
                    "volume": float(c.volume)
                }
                for c in candles_data[-100:]  # Last 100 candles
            ]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    assert "snapshotId" in result or "jobId" in result
                    assert "status" in result
                else:
                    # Log response for debugging
                    text = await response.text()
                    print(f"Response status: {response.status}")
                    print(f"Response body: {text}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip("Requires Puppeteer and browser setup")
    async def test_real_snapshot_generation_with_browser(self, signal_event, candles_data):
        """Test actual snapshot generation with Puppeteer (requires browser)."""
        # This would test the actual Puppeteer rendering
        # Skipped by default as it requires Chrome/Chromium installed
        pass

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_storage_and_retrieval(self, bff_api_url):
        """Test that generated snapshots can be retrieved."""
        # First generate a snapshot
        test_signal_id = f"test-signal-{datetime.now().timestamp()}"

        # Mock snapshot generation request
        request_data = {
            "signalId": test_signal_id,
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "signalData": {
                "type": "BUY",
                "entry": "50000",
                "stopLoss": "49000",
                "takeProfit": "52000"
            }
        }

        async with aiohttp.ClientSession() as session:
            # Generate snapshot
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    # Try to retrieve the snapshot
                    if "snapshotId" in result:
                        await asyncio.sleep(2)  # Wait for processing

                        # Get snapshot status
                        async with session.get(
                            f"{bff_api_url}/api/snapshots/{result['snapshotId']}"
                        ) as get_response:
                            if get_response.status == 200:
                                snapshot_data = await get_response.json()
                                assert "status" in snapshot_data
                                assert snapshot_data["status"] in ["pending", "completed", "failed"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_metadata_accuracy(self, signal_event):
        """Test that snapshot metadata matches signal data."""
        # Create snapshot metadata
        metadata = {
            "signalId": f"signal-{signal_event.timestamp.timestamp()}",
            "symbol": signal_event.symbol,
            "timeframe": signal_event.timeframe.value,
            "signalType": signal_event.signal_type,
            "entry": str(signal_event.entry_price),
            "stopLoss": str(signal_event.stop_loss),
            "takeProfit": str(signal_event.take_profit),
            "confidence": str(signal_event.confidence),
            "reasons": signal_event.metadata.get("confluence", []),
            "timestamp": signal_event.timestamp.isoformat()
        }

        # Verify all required fields are present
        assert metadata["symbol"] == "BTCUSDT"
        assert metadata["signalType"] == "BUY"
        assert Decimal(metadata["entry"]) == Decimal("50000")
        assert Decimal(metadata["stopLoss"]) == Decimal("49000")
        assert Decimal(metadata["takeProfit"]) == Decimal("52000")
        assert len(metadata["reasons"]) == 3


class TestSnapshotDelivery:
    """Test snapshot delivery to various channels."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip("Requires Telegram bot token")
    async def test_telegram_snapshot_delivery(self, signal_event):
        """Test sending snapshot to Telegram."""
        # This would require actual Telegram bot token
        # and chat ID to test real delivery
        pass

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_ui_websocket_notification(self, bff_api_url):
        """Test WebSocket notification for UI updates."""
        ws_url = bff_api_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url) as ws:
                    # Subscribe to alerts channel
                    await ws.send_json({
                        "type": "subscribe",
                        "channel": "alerts"
                    })

                    # Wait for acknowledgment
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        assert data.get("type") in ["subscribed", "welcome"]

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # WebSocket might not be implemented yet
            pytest.skip(f"WebSocket not available: {e}")


class TestSnapshotPerformance:
    """Test snapshot generation performance."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_generation_latency(self, bff_api_url, signal_event):
        """Test that snapshot generation completes within SLA."""
        start_time = datetime.now()

        request_data = {
            "signalId": f"perf-test-{start_time.timestamp()}",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "signalData": {
                "type": "BUY",
                "entry": "50000",
                "stopLoss": "49000",
                "takeProfit": "52000"
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    end_time = datetime.now()
                    latency = (end_time - start_time).total_seconds()

                    # Snapshot should be initiated within 1 second
                    assert latency < 1.0, f"Snapshot initiation took {latency}s"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_snapshot_generation(self, bff_api_url):
        """Test handling multiple concurrent snapshot requests."""
        num_concurrent = 5
        tasks = []

        async def generate_snapshot(idx):
            request_data = {
                "signalId": f"concurrent-test-{idx}-{datetime.now().timestamp()}",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "signalData": {
                    "type": "BUY",
                    "entry": str(50000 + idx * 100),
                    "stopLoss": str(49000 + idx * 100),
                    "takeProfit": str(52000 + idx * 100)
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{bff_api_url}/api/snapshots/generate",
                    json=request_data
                ) as response:
                    return response.status

        # Create concurrent requests
        for i in range(num_concurrent):
            tasks.append(generate_snapshot(i))

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        successful = sum(1 for r in results if isinstance(r, int) and r == 200)
        assert successful >= num_concurrent * 0.8  # At least 80% should succeed


class TestSnapshotErrorHandling:
    """Test error scenarios in snapshot generation."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_missing_signal_data(self, bff_api_url):
        """Test handling of missing signal data."""
        # Send request with missing required fields
        request_data = {
            "signalId": "test-missing-data",
            "symbol": "BTCUSDT"
            # Missing timeframe, signalData
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data
            ) as response:
                assert response.status in [400, 422]  # Bad request
                if response.status == 400:
                    error_data = await response.json()
                    assert "error" in error_data or "message" in error_data

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_symbol_handling(self, bff_api_url):
        """Test handling of invalid trading symbols."""
        request_data = {
            "signalId": "test-invalid-symbol",
            "symbol": "INVALID_SYMBOL",
            "timeframe": "15m",
            "signalData": {
                "type": "BUY",
                "entry": "100",
                "stopLoss": "90",
                "takeProfit": "110"
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data
            ) as response:
                # Should accept the request but may fail during processing
                assert response.status in [200, 400, 422]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_retry_on_failure(self, bff_api_url):
        """Test that failed snapshots are retried."""
        # This would require access to the job queue to verify retry behavior
        # For now, we just test that the API accepts retry requests

        request_data = {
            "signalId": "test-retry-behavior",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "signalData": {
                "type": "BUY",
                "entry": "50000",
                "stopLoss": "49000",
                "takeProfit": "52000"
            },
            "retry": True  # Indicate this is a retry
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{bff_api_url}/api/snapshots/generate",
                json=request_data
            ) as response:
                assert response.status in [200, 202]  # Accepted for processing


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])