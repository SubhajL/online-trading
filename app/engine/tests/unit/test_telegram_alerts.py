"""Unit tests for Telegram alert adapter."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.adapters.alert.telegram import TelegramAlertAdapter


@pytest.fixture
def telegram_adapter():
    """Create a Telegram adapter instance for testing."""
    return TelegramAlertAdapter(
        bot_token="test-bot-token", chat_id="test-chat-id", rate_limit_per_minute=30,
    )


@pytest.mark.asyncio
async def test_handle_decision_with_snapshot(telegram_adapter):
    """Test handling decision events with snapshot."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True})

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    # Mock helper methods
    telegram_adapter._get_snapshot_url = AsyncMock(
        return_value="http://example.com/snapshot.png",
    )
    telegram_adapter._download_snapshot = AsyncMock(return_value=b"fake-image-data")

    # Test event with signal_id - using correct field names
    event = {
        "symbol": "BTCUSDT",
        "side": "long",  # changed from 'BUY' to 'long'
        "timestamp": "2025-01-26T10:00:00Z",
        "signal_id": "test-signal-123",
        "entry_price": Decimal(50000),  # changed from 'entry' to 'entry_price'
        "stop_loss": Decimal(49000),
        "take_profit": Decimal(52000),
        "quantity": Decimal("0.01"),
        "confidence": 0.85,
        "reasons": ["SMC Break", "Trend Alignment"],
    }

    await telegram_adapter._handle_decision(event)

    # Verify snapshot was fetched
    telegram_adapter._get_snapshot_url.assert_called_once_with("test-signal-123")
    telegram_adapter._download_snapshot.assert_called_once_with(
        "http://example.com/snapshot.png",
    )

    # Verify photo was sent
    mock_session.post.assert_called()
    call_args = mock_session.post.call_args
    assert "sendPhoto" in call_args[0][0]  # URL contains sendPhoto


@pytest.mark.asyncio
async def test_handle_decision_without_snapshot(telegram_adapter):
    """Test handling decision events without snapshot."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True})

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    # Test event without signal_id
    event = {
        "symbol": "BTCUSDT",
        "side": "short",  # changed from 'SELL' to 'short'
        "timestamp": "2025-01-26T10:00:00Z",
        "entry_price": Decimal(50000),
        "stop_loss": Decimal(51000),
        "take_profit": Decimal(48000),
        "quantity": Decimal("0.01"),
        "confidence": 0.75,
        "reasons": ["Resistance Hit"],
    }

    await telegram_adapter._handle_decision(event)

    # Verify text message was sent
    mock_session.post.assert_called()
    call_args = mock_session.post.call_args
    assert "sendMessage" in call_args[0][0]  # URL contains sendMessage


@pytest.mark.asyncio
async def test_get_snapshot_url_success(telegram_adapter):
    """Test successful snapshot URL fetch."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={"imageUrl": "http://example.com/snap.png"},
    )

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    with patch.dict(
        "os.environ", {"BFF_URL": "http://bff:3000", "INTERNAL_API_KEY": "test-key"},
    ):
        url = await telegram_adapter._get_snapshot_url("signal-123")

    assert url == "http://example.com/snap.png"
    mock_session.get.assert_called_with(
        "http://bff:3000/api/signals/signal-123/snapshot",
        headers={"Authorization": "Bearer test-key"},
    )


@pytest.mark.asyncio
async def test_get_snapshot_url_failure(telegram_adapter):
    """Test failed snapshot URL fetch."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 404

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    url = await telegram_adapter._get_snapshot_url("signal-123")

    assert url is None


@pytest.mark.asyncio
async def test_download_snapshot_success(telegram_adapter):
    """Test successful snapshot download."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"image-data")

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    data = await telegram_adapter._download_snapshot("http://example.com/image.png")

    assert data == b"image-data"


@pytest.mark.asyncio
async def test_download_snapshot_failure(telegram_adapter):
    """Test failed snapshot download."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 500

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    data = await telegram_adapter._download_snapshot("http://example.com/image.png")

    assert data is None


@pytest.mark.asyncio
async def test_send_photo_alert(telegram_adapter):
    """Test sending photo alert."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True})

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    success = await telegram_adapter._send_photo_alert(b"image-data", "Test caption")

    assert success is True

    # Check FormData was used
    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args
    assert "data" in call_args[1]  # FormData is passed as data parameter


@pytest.mark.asyncio
async def test_get_snapshot_url_defaults_to_port_3001(telegram_adapter):
    """Test that BFF_URL defaults to port 3001 when not set."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"imageUrl": "/snapshots/test.png"})

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    # Clear BFF_URL env var to test default
    with patch.dict("os.environ", {}, clear=True):
        await telegram_adapter._get_snapshot_url("signal-123")

    # Verify port 3001 was used
    call_args = mock_session.get.call_args
    assert ":3001/" in call_args[0][0]


@pytest.mark.asyncio
async def test_normalize_image_url_joins_relative_path(telegram_adapter):
    """Test that relative imageUrl is joined with BFF_URL."""
    relative_url = "/snapshots/abc123.png"
    bff_url = "http://localhost:3001"

    result = telegram_adapter._normalize_image_url(relative_url, bff_url)

    assert result == "http://localhost:3001/snapshots/abc123.png"


@pytest.mark.asyncio
async def test_normalize_image_url_preserves_absolute_url(telegram_adapter):
    """Test that absolute imageUrl is preserved."""
    absolute_url = "https://cdn.example.com/snapshots/abc123.png"
    bff_url = "http://localhost:3001"

    result = telegram_adapter._normalize_image_url(absolute_url, bff_url)

    assert result == absolute_url


@pytest.mark.asyncio
async def test_get_snapshot_url_normalizes_relative_response(telegram_adapter):
    """Test that _get_snapshot_url normalizes relative URLs from BFF."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"imageUrl": "/snapshots/test.png"})

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    with patch.dict("os.environ", {"BFF_URL": "http://bff:3001"}):
        url = await telegram_adapter._get_snapshot_url("signal-123")

    assert url == "http://bff:3001/snapshots/test.png"


@pytest.mark.asyncio
async def test_get_snapshot_url_retries_on_404(telegram_adapter):
    """Test that _get_snapshot_url retries when snapshot not ready."""
    # First two calls return 404, third returns success
    call_count = 0

    def create_mock_context(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_response = MagicMock()
        if call_count < 3:
            mock_response.status = 404
        else:
            mock_response.status = 200
            mock_response.json = AsyncMock(
                return_value={"imageUrl": "/snapshots/test.png"},
            )
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        return mock_context

    mock_session = MagicMock()
    mock_session.get = MagicMock(side_effect=create_mock_context)

    telegram_adapter.session = mock_session

    with patch.dict("os.environ", {"BFF_URL": "http://bff:3001"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            url = await telegram_adapter._get_snapshot_url("signal-123")

    assert url == "http://bff:3001/snapshots/test.png"
    assert call_count == 3


@pytest.mark.asyncio
async def test_get_snapshot_url_gives_up_after_max_retries(telegram_adapter):
    """Test that _get_snapshot_url returns None after max retries."""
    mock_response = MagicMock()
    mock_response.status = 404

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session

    with patch.dict("os.environ", {"BFF_URL": "http://bff:3001"}):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            url = await telegram_adapter._get_snapshot_url("signal-123")

    assert url is None
    # Should have tried 3 times (default max retries)
    assert mock_session.get.call_count == 3


@pytest.mark.asyncio
async def test_rate_limiting(telegram_adapter):
    """Test rate limiting functionality."""
    # Create a proper mock response context manager
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True})

    # Create a context manager that returns the response
    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)

    telegram_adapter.session = mock_session
    telegram_adapter.rate_limit_per_minute = 2  # Low limit for testing

    # Send messages up to the limit
    for _ in range(2):
        success = await telegram_adapter._send_alert("Test message")
        assert success is True

    # Next message should be rate limited
    success = await telegram_adapter._send_alert("Test message")
    assert success is False
