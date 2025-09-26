"""
Integration tests for chart snapshot delivery to Telegram and UI.

Tests the complete flow from snapshot generation to delivery via:
- Telegram bot API
- WebSocket notifications to UI
- Error handling and retries
"""

import asyncio
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch, call
import base64
import io

import pytest
import aiohttp
from PIL import Image

from app.engine.models import (
    RetestSignalEvent, RetestSignal, TimeFrame
)
from app.engine.monitoring.metrics import (
    record_snapshot_delivery,
    get_metrics
)


class TestTelegramDelivery:
    """Test chart snapshot delivery to Telegram."""

    @pytest.fixture
    def telegram_config(self):
        """Telegram bot configuration."""
        return {
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", "test_bot_token"),
            "chat_id": os.getenv("TELEGRAM_CHAT_ID", "-1001234567890"),
            "api_url": "https://api.telegram.org",
            "timeout": 30,
            "max_retries": 3
        }

    @pytest.fixture
    def mock_signal_event(self):
        """Create a test signal event."""
        signal = RetestSignal(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime.now(),
            level_price=Decimal("50000"),
            retest_type="zone_retest",
            success_probability=Decimal("0.85"),
            volume_confirmation=True,
            confluence_factors=["BOS", "EMA_support", "RSI_oversold"]
        )
        return RetestSignalEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            signal=signal
        )

    @pytest.fixture
    def mock_snapshot_image(self):
        """Create a mock chart snapshot image."""
        # Create a simple test image
        img = Image.new('RGB', (1200, 600), color='white')

        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        return img_byte_arr.getvalue()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telegram_photo_delivery(self, telegram_config, mock_signal_event, mock_snapshot_image):
        """Test sending chart snapshot to Telegram."""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Mock successful Telegram API response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "ok": True,
                "result": {
                    "message_id": 12345,
                    "chat": {"id": telegram_config["chat_id"]},
                    "photo": [{"file_id": "test_file_id"}]
                }
            })
            mock_session.post.return_value.__aenter__.return_value = mock_response

            # Create delivery service
            from app.engine.delivery.telegram import TelegramDelivery
            telegram = TelegramDelivery(telegram_config)

            # Prepare message
            caption = telegram._format_signal_caption(mock_signal_event.signal)

            # Send snapshot
            result = await telegram.send_snapshot(
                image_data=mock_snapshot_image,
                caption=caption,
                signal_event=mock_signal_event
            )

            # Verify API call
            assert mock_session.post.called
            call_args = mock_session.post.call_args

            # Check URL
            expected_url = f"{telegram_config['api_url']}/bot{telegram_config['bot_token']}/sendPhoto"
            assert call_args[0][0] == expected_url

            # Check multipart data
            assert 'data' in call_args[1]
            form_data = call_args[1]['data']

            # Verify form fields
            assert form_data._fields[0][0]['name'] == 'chat_id'
            assert form_data._fields[1][0]['name'] == 'photo'
            assert form_data._fields[2][0]['name'] == 'caption'
            assert form_data._fields[3][0]['name'] == 'parse_mode'

            # Verify result
            assert result["success"] is True
            assert result["message_id"] == 12345

            # Check metrics
            metrics = get_metrics().decode('utf-8')
            assert 'snapshot_delivery_success_total{channel="telegram"} 1' in metrics

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telegram_caption_formatting(self, mock_signal_event):
        """Test Telegram caption formatting."""
        from app.engine.delivery.telegram import TelegramDelivery

        telegram = TelegramDelivery({})
        caption = telegram._format_signal_caption(mock_signal_event.signal)

        # Verify caption contains key information
        assert "Zone Retest Signal" in caption  # Retest type
        assert "BTCUSDT" in caption
        assert "15m" in caption
        assert "*Level Price:* $50,000" in caption
        assert "*Success Probability:* 85%" in caption
        assert "*Volume:* ✅ Confirmed" in caption  # Volume confirmation

        # Check confluence factors
        assert "Confluence Factors:" in caption
        assert "✓ Break of Structure" in caption  # BOS
        assert "✓ EMA Support" in caption
        assert "✓ RSI Oversold" in caption

        # Check markdown formatting
        assert "*" in caption  # Bold markers
        assert "📊" in caption  # Chart emoji
        assert "🟢" in caption  # Zone retest emoji

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telegram_retry_on_failure(self, telegram_config, mock_snapshot_image):
        """Test retry mechanism for Telegram delivery failures."""
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session

            # Mock failures then success
            mock_responses = []

            # First attempt: Network error
            mock_response1 = AsyncMock()
            mock_response1.status = 429  # Rate limit
            mock_response1.json = AsyncMock(return_value={
                "ok": False,
                "error_code": 429,
                "parameters": {"retry_after": 2}
            })
            mock_responses.append(mock_response1)

            # Second attempt: Server error
            mock_response2 = AsyncMock()
            mock_response2.status = 500
            mock_responses.append(mock_response2)

            # Third attempt: Success
            mock_response3 = AsyncMock()
            mock_response3.status = 200
            mock_response3.json = AsyncMock(return_value={
                "ok": True,
                "result": {"message_id": 67890}
            })
            mock_responses.append(mock_response3)

            # Configure mock to return different responses
            mock_session.post.return_value.__aenter__.side_effect = mock_responses

            from app.engine.delivery.telegram import TelegramDelivery
            telegram = TelegramDelivery(telegram_config)

            # Send with retries
            result = await telegram.send_snapshot(
                image_data=mock_snapshot_image,
                caption="Test signal",
                signal_event=None
            )

            # Should succeed after retries
            assert result["success"] is True
            assert mock_session.post.call_count == 3  # Three attempts

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_telegram_error_handling(self, telegram_config):
        """Test error handling for various Telegram API errors."""
        test_cases = [
            {
                "error": {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"},
                "expected": "Chat not found"
            },
            {
                "error": {"ok": False, "error_code": 401, "description": "Unauthorized"},
                "expected": "Invalid bot token"
            },
            {
                "error": {"ok": False, "error_code": 413, "description": "Request Entity Too Large"},
                "expected": "Image too large"
            }
        ]

        from app.engine.delivery.telegram import TelegramDelivery
        telegram = TelegramDelivery(telegram_config)

        for test_case in test_cases:
            with patch('aiohttp.ClientSession') as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session

                mock_response = AsyncMock()
                mock_response.status = test_case["error"]["error_code"]
                mock_response.json = AsyncMock(return_value=test_case["error"])
                mock_session.post.return_value.__aenter__.return_value = mock_response

                result = await telegram.send_snapshot(
                    image_data=b"test",
                    caption="Test",
                    signal_event=None
                )

                assert result["success"] is False
                assert test_case["expected"] in result["error"]


class TestWebSocketUIDelivery:
    """Test chart snapshot delivery to UI via WebSocket."""

    @pytest.fixture
    def ws_server_url(self):
        """WebSocket server URL."""
        return os.getenv("WS_SERVER_URL", "ws://localhost:8002/ws")

    @pytest.fixture
    def mock_snapshot_data(self):
        """Create mock snapshot data for UI."""
        return {
            "type": "chart_snapshot",
            "signal_id": f"signal_{int(datetime.now().timestamp())}",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "signal_type": "BUY",
            "timestamp": datetime.now().isoformat(),
            "snapshot": {
                "image_url": "/api/snapshots/abc123.png",
                "width": 1200,
                "height": 600
            },
            "signal_data": {
                "entry": 50000,
                "stop_loss": 49000,
                "take_profit": 52000,
                "confidence": 0.85
            }
        }

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_websocket_notification(self, ws_server_url, mock_snapshot_data):
        """Test WebSocket notification for new snapshot."""
        with patch('websockets.connect') as mock_connect:
            # Mock WebSocket connection
            mock_ws = AsyncMock()
            mock_connect.return_value.__aenter__.return_value = mock_ws

            from app.engine.delivery.websocket import WebSocketDelivery
            ws_delivery = WebSocketDelivery(ws_server_url)

            # Connect
            await ws_delivery.connect()
            assert mock_connect.called

            # Send notification
            await ws_delivery.notify_snapshot(mock_snapshot_data)

            # Verify message sent
            mock_ws.send.assert_called_once()
            sent_data = json.loads(mock_ws.send.call_args[0][0])

            assert sent_data["type"] == "chart_snapshot"
            assert sent_data["signal_id"] == mock_snapshot_data["signal_id"]
            assert sent_data["symbol"] == "BTCUSDT"

            # Check metrics
            metrics = get_metrics().decode('utf-8')
            assert 'snapshot_delivery_success_total{channel="ui"} 1' in metrics

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_websocket_broadcast_to_subscribers(self, ws_server_url):
        """Test broadcasting to multiple WebSocket subscribers."""
        # Mock multiple client connections
        mock_clients = []
        for i in range(3):
            mock_client = AsyncMock()
            mock_client.id = f"client_{i}"
            mock_client.subscriptions = ["alerts", "snapshots"]
            mock_clients.append(mock_client)

        with patch('app.engine.delivery.websocket.WebSocketManager.broadcast') as mock_broadcast:
            from app.engine.delivery.websocket import WebSocketManager

            manager = WebSocketManager()
            manager.active_connections = mock_clients

            # Broadcast snapshot notification
            notification = {
                "type": "chart_snapshot",
                "channel": "snapshots",
                "data": {"signal_id": "test123"}
            }

            await manager.broadcast_to_channel("snapshots", notification)

            # Verify broadcast was called
            mock_broadcast.assert_called_once()

            # Should send to all 3 clients
            assert len(mock_broadcast.call_args[0][0]) == 3

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_websocket_reconnection(self, ws_server_url):
        """Test WebSocket reconnection on disconnect."""
        disconnect_count = 0

        async def mock_connect(*args, **kwargs):
            nonlocal disconnect_count
            mock_ws = AsyncMock()

            # First connection fails after some time
            if disconnect_count == 0:
                mock_ws.recv = AsyncMock(side_effect=aiohttp.ClientConnectionError())
                disconnect_count += 1
            else:
                # Second connection succeeds
                mock_ws.recv = AsyncMock(return_value='{"type": "pong"}')

            return mock_ws

        with patch('websockets.connect', side_effect=mock_connect):
            from app.engine.delivery.websocket import WebSocketDelivery

            ws_delivery = WebSocketDelivery(ws_server_url)
            ws_delivery.reconnect_delay = 0.1  # Fast reconnect for testing

            # Start connection with auto-reconnect
            await ws_delivery.connect(auto_reconnect=True)

            # Wait for reconnection
            await asyncio.sleep(0.2)

            # Should have reconnected
            assert ws_delivery.connected
            assert disconnect_count == 1


class TestDeliveryOrchestration:
    """Test coordinated delivery to multiple channels."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_channel_delivery(self):
        """Test delivering snapshot to both Telegram and UI."""
        signal = RetestSignal(
            symbol="ETHUSDT",
            timeframe=TimeFrame.H1,
            timestamp=datetime.now(),
            level_price=Decimal("3000"),
            retest_type="resistance_retest",
            success_probability=Decimal("0.75"),
            volume_confirmation=True,
            confluence_factors=["CHOCH", "supply_zone", "trend_alignment"]
        )
        signal_event = RetestSignalEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            signal=signal
        )

        # Mock successful deliveries
        telegram_result = {"success": True, "message_id": 111}
        ws_result = {"success": True, "clients_notified": 5}

        with patch('app.engine.delivery.telegram.TelegramDelivery.send_snapshot') as mock_telegram, \
             patch('app.engine.delivery.websocket.WebSocketDelivery.notify_snapshot') as mock_ws:

            mock_telegram.return_value = telegram_result
            mock_ws.return_value = ws_result

            from app.engine.delivery.orchestrator import DeliveryOrchestrator

            orchestrator = DeliveryOrchestrator()
            results = await orchestrator.deliver_snapshot(
                signal_event=signal_event,
                snapshot_data=b"test_image_data",
                channels=["telegram", "websocket"]
            )

            # Verify both channels were called
            assert mock_telegram.called
            assert mock_ws.called

            # Check results
            assert results["telegram"] == telegram_result
            assert results["websocket"] == ws_result
            assert results["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_partial_delivery_failure(self):
        """Test handling when some channels fail."""
        # Mock Telegram fails, WebSocket succeeds
        with patch('app.engine.delivery.telegram.TelegramDelivery.send_snapshot') as mock_telegram, \
             patch('app.engine.delivery.websocket.WebSocketDelivery.notify_snapshot') as mock_ws:

            mock_telegram.side_effect = Exception("Network error")
            mock_ws.return_value = {"success": True}

            from app.engine.delivery.orchestrator import DeliveryOrchestrator

            orchestrator = DeliveryOrchestrator()
            results = await orchestrator.deliver_snapshot(
                signal_event=None,
                snapshot_data=b"test",
                channels=["telegram", "websocket"]
            )

            # Should show partial success
            assert results["success"] is False
            assert results["telegram"]["success"] is False
            assert results["websocket"]["success"] is True
            assert "error" in results["telegram"]


class TestSnapshotStorage:
    """Test snapshot storage and retrieval."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip("Requires aiobotocore installation")
    async def test_snapshot_storage_to_s3(self):
        """Test storing snapshots to S3-compatible storage."""
        with patch('aiobotocore.session.AioSession') as mock_session:
            # Mock S3 client
            mock_client = AsyncMock()
            mock_client.put_object = AsyncMock(return_value={
                'ETag': '"abc123"',
                'VersionId': 'v1'
            })

            mock_session.return_value.create_client.return_value.__aenter__.return_value = mock_client

            from app.engine.delivery.storage import S3SnapshotStorage

            storage = S3SnapshotStorage(
                bucket="trading-snapshots",
                prefix="signals/",
                region="us-east-1"
            )

            # Store snapshot
            signal_id = "signal_12345"
            image_data = b"test_image_data"

            url = await storage.store_snapshot(signal_id, image_data)

            # Verify S3 call
            mock_client.put_object.assert_called_once()
            call_args = mock_client.put_object.call_args[1]

            assert call_args['Bucket'] == "trading-snapshots"
            assert call_args['Key'] == f"signals/{signal_id}.png"
            assert call_args['Body'] == image_data
            assert call_args['ContentType'] == "image/png"

            # Check returned URL
            assert signal_id in url
            assert url.startswith("https://")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_snapshot_cdn_url_generation(self):
        """Test generating CDN URLs for stored snapshots."""
        from app.engine.delivery.storage import SnapshotStorage

        storage = SnapshotStorage(
            cdn_url="https://cdn.trading.com",
            bucket="snapshots"
        )

        # Generate CDN URL
        signal_id = "signal_abc123"
        url = storage.get_snapshot_url(signal_id)

        assert url == "https://cdn.trading.com/snapshots/signal_abc123.png"

        # Test with custom TTL for signed URLs
        signed_url = storage.get_snapshot_url(signal_id, ttl=3600, signed=True)
        assert "?expires=" in signed_url


class TestDeliveryMetrics:
    """Test metrics collection for delivery operations."""

    def test_delivery_metrics_tracking(self):
        """Test that delivery metrics are properly tracked."""
        # Get initial metrics
        initial_metrics = get_metrics().decode('utf-8')

        # Record some delivery events
        from app.engine.monitoring.metrics import record_snapshot_delivery

        # Successful deliveries
        for _ in range(5):
            record_snapshot_delivery("telegram")

        for _ in range(3):
            record_snapshot_delivery("ui")

        # Get updated metrics
        final_metrics = get_metrics().decode('utf-8')

        # Verify counters increased
        assert 'snapshot_delivery_success_total{channel="telegram"} 5' in final_metrics
        assert 'snapshot_delivery_success_total{channel="ui"} 3' in final_metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])