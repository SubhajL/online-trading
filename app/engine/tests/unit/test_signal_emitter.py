"""Unit tests for signal emitter."""

import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
import pytest
from datetime import datetime
import uuid

from app.engine.adapters.alert.signal_emitter import SignalEmitter, MockBffClient


@pytest.fixture
def mock_event_bus():
    """Mock event bus fixture."""
    return Mock(
        publish=AsyncMock()
    )


@pytest.fixture
def mock_bff_client():
    """Mock BFF client fixture."""
    return Mock(
        post=AsyncMock(return_value={
            'success': True,
            'signalId': 'test-signal-123',
            'imageUrl': '/snapshots/test-signal-123.png'
        })
    )


@pytest.fixture
def signal_emitter(mock_event_bus, mock_bff_client):
    """Create a signal emitter instance for testing."""
    return SignalEmitter(mock_event_bus, mock_bff_client)


@pytest.mark.asyncio
async def test_emit_signal_basic(signal_emitter, mock_event_bus, mock_bff_client):
    """Test basic signal emission."""
    signal_id = await signal_emitter.emit_signal(
        symbol="BTCUSDT",
        venue="SPOT",
        side="long",
        entry=50000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.85,
        reasons=["SMC Break", "Trend Alignment"],
        timeframe="15m"
    )

    # Check signal ID was generated
    assert signal_id.startswith("sig_")
    assert len(signal_id) == 16  # sig_ + 12 hex chars

    # Check event was published
    mock_event_bus.publish.assert_called_once()
    call_args = mock_event_bus.publish.call_args
    assert call_args[0][0] == 'decision.v1'

    # Check event content
    event = call_args[0][1]
    assert event['signal_id'] == signal_id
    assert event['symbol'] == "BTCUSDT"
    assert event['venue'] == "SPOT"
    assert event['side'] == "long"
    assert event['entry_price'] == 50000
    assert event['stop_loss'] == 49000
    assert event['take_profit'] == 52000
    assert event['confidence'] == 0.85
    assert event['reasons'] == ["SMC Break", "Trend Alignment"]
    assert event['timeframe'] == "15m"

    # Check BFF was notified
    mock_bff_client.post.assert_called_once_with(
        '/api/signals/alert',
        {
            'signalId': signal_id,
            'symbol': 'BTCUSDT',
            'venue': 'SPOT',
            'side': 'BUY',
            'entry': 50000,
            'stopLoss': 49000,
            'takeProfit': 52000,
            'confidence': 0.85,
            'reasons': ["SMC Break", "Trend Alignment"],
            'timeframe': '15m',
            'signalTime': event['decision_time'],
        }
    )


@pytest.mark.asyncio
async def test_emit_signal_short_side(signal_emitter, mock_event_bus, mock_bff_client):
    """Test signal emission with short side."""
    signal_id = await signal_emitter.emit_signal(
        symbol="ETHUSDT",
        venue="USD_M",
        side="short",
        entry=3000,
        stop_loss=3100,
        take_profit=2800,
        confidence=0.75,
        reasons=["Resistance"],
    )

    # Check BFF notification has SELL side
    mock_bff_client.post.assert_called_once()
    call_args = mock_bff_client.post.call_args
    payload = call_args[0][1]
    assert payload['side'] == 'SELL'


@pytest.mark.asyncio
async def test_emit_signal_with_custom_time(signal_emitter, mock_event_bus):
    """Test signal emission with custom decision time."""
    custom_time = datetime(2025, 1, 26, 10, 30, 0)

    signal_id = await signal_emitter.emit_signal(
        symbol="BTCUSDT",
        venue="SPOT",
        side="long",
        entry=50000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.85,
        reasons=["Test"],
        decision_time=custom_time
    )

    # Check event has custom time
    call_args = mock_event_bus.publish.call_args
    event = call_args[0][1]
    assert event['timestamp'] == custom_time.isoformat()
    assert event['decision_time'] == custom_time.isoformat()


@pytest.mark.asyncio
async def test_emit_signal_error_handling(signal_emitter, mock_event_bus):
    """Test error handling during signal emission."""
    # Make publish raise an error
    mock_event_bus.publish.side_effect = Exception("Event bus error")

    with pytest.raises(Exception) as exc_info:
        await signal_emitter.emit_signal(
            symbol="BTCUSDT",
            venue="SPOT",
            side="long",
            entry=50000,
            stop_loss=49000,
            take_profit=52000,
            confidence=0.85,
            reasons=["Test"]
        )

    assert "Event bus error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_notify_snapshot_error_handling(signal_emitter, mock_event_bus, mock_bff_client):
    """Test that snapshot errors don't block signal emission."""
    # Make BFF client raise an error
    mock_bff_client.post.side_effect = Exception("BFF error")

    # Should not raise - snapshot is best effort
    signal_id = await signal_emitter.emit_signal(
        symbol="BTCUSDT",
        venue="SPOT",
        side="long",
        entry=50000,
        stop_loss=49000,
        take_profit=52000,
        confidence=0.85,
        reasons=["Test"]
    )

    # Signal should still be emitted
    assert signal_id.startswith("sig_")
    mock_event_bus.publish.assert_called_once()


@pytest.mark.asyncio
async def test_mock_bff_client():
    """Test the mock BFF client."""
    client = MockBffClient("http://localhost:3000", "test-key")

    # Test posting a signal
    response = await client.post("/api/signals/alert", {
        'signalId': 'test-123',
        'symbol': 'BTCUSDT'
    })

    assert response['success'] is True
    assert response['signalId'] == 'test-123'
    assert response['imageUrl'] == '/snapshots/test-123.png'

    # Check signal was recorded
    assert len(client.posted_signals) == 1
    posted = client.posted_signals[0]
    assert posted['endpoint'] == '/api/signals/alert'
    assert posted['payload']['signalId'] == 'test-123'


@pytest.mark.asyncio
async def test_emit_test_signal():
    """Test the emit_test_signal function."""
    from app.engine.adapters.alert.signal_emitter import emit_test_signal

    # Run without errors
    await emit_test_signal()
    # If it doesn't raise, test passes