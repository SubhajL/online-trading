"""Unit tests for Telegram alert adapter."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.adapters.alert.telegram import TelegramAlertAdapter


class _FakeAuditAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def insert_outbound_alert_audit(self, **kwargs: object) -> None:  # noqa: D401
        self.calls.append(kwargs)


class _BlockingAuditAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[dict[str, object]] = []

    async def insert_outbound_alert_audit(self, **kwargs: object) -> None:  # noqa: D401
        self.calls.append(kwargs)
        self.started.set()
        await self.release.wait()


@pytest.fixture
def telegram_adapter():
    """Create a Telegram adapter instance for testing."""
    audit_adapter = _FakeAuditAdapter()
    adapter = TelegramAlertAdapter(
        bot_token="test-bot-token",
        chat_id="test-chat-id",
        rate_limit_per_minute=30,
        db_adapter=audit_adapter,
    )
    # Unit tests must not rely on real Redis dedup state.
    adapter.deduplicator.redis_client = None
    adapter.error_deduplicator.redis_client = None
    adapter.startup_deduplicator.redis_client = None
    adapter._test_audit_adapter = audit_adapter  # type: ignore[attr-defined]
    return adapter


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
async def test_send_alert_persists_successful_text_audit(telegram_adapter):
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True, "result": {"message_id": 321}})

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)
    telegram_adapter.session = mock_session

    success = await telegram_adapter._send_alert(
        "Test outbound message",
        alert_type="order_update",
        payload={"symbol": "BTCUSDT", "event_type": "order_update.v1"},
    )
    await asyncio.sleep(0)

    assert success is True
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["channel"] == "telegram"
    assert call["alert_type"] == "order_update"
    assert call["delivery_method"] == "text"
    assert call["status"] == "sent"
    assert call["chat_id"] == "test-chat-id"
    assert call["telegram_message_id"] == 321
    assert call["message_text"] == "Test outbound message"
    assert call["payload"] == {"symbol": "BTCUSDT", "event_type": "order_update.v1"}


@pytest.mark.asyncio
async def test_send_alert_persists_http_failure_audit(telegram_adapter):
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Server error")

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)
    telegram_adapter.session = mock_session

    with patch("asyncio.sleep", new_callable=AsyncMock):
        success = await telegram_adapter._send_alert(
            "Failure outbound message",
            alert_type="error",
            payload={"component": "pipeline_health"},
        )
    await asyncio.sleep(0)

    assert success is False
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["alert_type"] == "error"
    assert call["status"] == "failed"
    assert call["response_status"] == 500
    assert call["response_body"] == "Server error"


@pytest.mark.asyncio
async def test_handle_decision_persists_dedup_skip_audit(telegram_adapter):
    telegram_adapter.deduplicator.reserve = MagicMock(return_value=False)
    telegram_adapter.session = MagicMock()

    event = {
        "symbol": "BTCUSDT",
        "side": "long",
        "timestamp": "2025-01-26T10:00:00Z",
        "signal_id": "test-signal-123",
        "entry_price": Decimal(50000),
        "stop_loss": Decimal(49000),
        "take_profit": Decimal(52000),
        "quantity": Decimal("0.01"),
        "confidence": 0.85,
        "reasons": ["SMC Break", "Trend Alignment"],
    }

    await telegram_adapter._handle_decision(event)
    await asyncio.sleep(0)

    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["alert_type"] == "decision"
    assert call["status"] == "skipped"
    assert call["reason"] == "deduplicated"
    assert call["dedup_key"] == "decision:BTCUSDT:long:2025-01-26T10:00:00Z"


@pytest.mark.asyncio
async def test_send_alert_persists_rate_limit_skip_audit(telegram_adapter):
    telegram_adapter._message_times = [datetime.now(UTC)] * telegram_adapter.rate_limit_per_minute
    telegram_adapter.session = MagicMock()

    success = await telegram_adapter._send_alert(
        "Rate limited outbound message",
        alert_type="startup",
        payload={"phase": "backfill_complete"},
    )
    await asyncio.sleep(0)

    assert success is False
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["alert_type"] == "startup"
    assert call["status"] == "skipped"
    assert call["reason"] == "rate_limited"


@pytest.mark.asyncio
async def test_send_photo_alert_persists_failure_audit(telegram_adapter):
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Photo upload failed")

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)
    telegram_adapter.session = mock_session

    success = await telegram_adapter._send_photo_alert(
        b"image-bytes",
        "Photo caption",
        alert_type="decision",
        payload={"signal_id": "sig-1"},
        dedup_key="decision:BTCUSDT:long:now",
    )
    await asyncio.sleep(0)

    assert success is False
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["delivery_method"] == "photo"
    assert call["status"] == "failed"
    assert call["reason"] == "http_error"
    assert call["response_status"] == 500
    assert call["response_body"] == "Photo upload failed"


@pytest.mark.asyncio
async def test_send_error_alert_persists_dedup_skip_audit(telegram_adapter):
    telegram_adapter.error_deduplicator.reserve = MagicMock(return_value=False)
    telegram_adapter.session = MagicMock()

    success = await telegram_adapter.send_error_alert(
        "Pipeline failure",
        dedup_key="error:pipeline_health:websocket_stale",
    )
    await asyncio.sleep(0)

    assert success is False
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["alert_type"] == "error"
    assert call["status"] == "skipped"
    assert call["reason"] == "deduplicated"
    assert call["dedup_key"] == "error:pipeline_health:websocket_stale"


@pytest.mark.asyncio
async def test_send_alert_does_not_block_on_audit_write():
    audit_adapter = _BlockingAuditAdapter()
    adapter = TelegramAlertAdapter(
        bot_token="test-bot-token",
        chat_id="test-chat-id",
        rate_limit_per_minute=30,
        db_adapter=audit_adapter,
    )
    adapter.deduplicator.redis_client = None
    adapter.error_deduplicator.redis_client = None
    adapter.startup_deduplicator.redis_client = None

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True, "result": {"message_id": 123}})

    mock_context = AsyncMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_context)
    adapter.session = mock_session

    success = await asyncio.wait_for(
        adapter._send_alert("Test outbound message", alert_type="order_update"),
        timeout=0.05,
    )

    assert success is True
    await asyncio.wait_for(audit_adapter.started.wait(), timeout=0.05)
    audit_adapter.release.set()
    await asyncio.sleep(0)
    assert len(audit_adapter.calls) == 1


@pytest.mark.asyncio
async def test_handle_decision_dedup_skip_does_not_block_on_audit_write():
    audit_adapter = _BlockingAuditAdapter()
    adapter = TelegramAlertAdapter(
        bot_token="test-bot-token",
        chat_id="test-chat-id",
        rate_limit_per_minute=30,
        db_adapter=audit_adapter,
    )
    adapter.deduplicator.redis_client = None
    adapter.error_deduplicator.redis_client = None
    adapter.startup_deduplicator.redis_client = None
    adapter.deduplicator.reserve = MagicMock(return_value=False)
    adapter.session = MagicMock()

    event = {
        "symbol": "BTCUSDT",
        "side": "long",
        "timestamp": "2025-01-26T10:00:00Z",
        "signal_id": "test-signal-123",
        "entry_price": Decimal(50000),
        "stop_loss": Decimal(49000),
        "take_profit": Decimal(52000),
        "quantity": Decimal("0.01"),
        "confidence": 0.85,
        "reasons": ["SMC Break", "Trend Alignment"],
    }

    await asyncio.wait_for(adapter._handle_decision(event), timeout=0.05)

    await asyncio.wait_for(audit_adapter.started.wait(), timeout=0.05)
    audit_adapter.release.set()
    await asyncio.sleep(0)
    assert len(audit_adapter.calls) == 1


@pytest.mark.asyncio
async def test_stop_waits_for_pending_audit_tasks() -> None:
    audit_adapter = _BlockingAuditAdapter()
    adapter = TelegramAlertAdapter(
        bot_token="test-bot-token",
        chat_id="test-chat-id",
        rate_limit_per_minute=30,
        db_adapter=audit_adapter,
    )
    session = MagicMock()
    session.close = AsyncMock()
    adapter.session = session

    adapter._schedule_audit_record(
        alert_type="error",
        delivery_method="text",
        status="failed",
        reason="test",
    )
    await asyncio.wait_for(audit_adapter.started.wait(), timeout=0.05)

    stop_task = asyncio.create_task(adapter.stop())
    await asyncio.sleep(0)
    assert not stop_task.done()
    session.close.assert_not_awaited()

    audit_adapter.release.set()
    await asyncio.wait_for(stop_task, timeout=0.05)

    session.close.assert_awaited_once()


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
        "os.environ",
        {"BFF_URL": "http://bff:3000", "INTERNAL_ALERTS_TOKEN": "test-key"},
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
    await asyncio.sleep(0)

    assert success is True
    audit_calls = telegram_adapter._test_audit_adapter.calls  # type: ignore[attr-defined]
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["delivery_method"] == "photo"
    assert call["status"] == "sent"
    assert call["message_text"] == "Test caption"

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


def _response_context(status: int, *, json_body: dict | None = None, text: str = "") -> AsyncMock:
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=json_body if json_body is not None else {})
    response.text = AsyncMock(return_value=text or str(json_body))
    context = AsyncMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


def _session_with_responses(*contexts: AsyncMock) -> MagicMock:
    session = MagicMock()
    session.post = MagicMock(side_effect=list(contexts))
    return session


class TestSendAlertRetries:
    """Transient send failures retry with backoff; permanent ones do not."""

    @pytest.mark.asyncio
    async def test_retries_on_500_then_succeeds(self, telegram_adapter) -> None:
        telegram_adapter.session = _session_with_responses(
            _response_context(500, text="Server error"),
            _response_context(200, json_body={"ok": True, "result": {"message_id": 7}}),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
            success = await telegram_adapter._send_alert("msg", alert_type="error")
        await asyncio.sleep(0)

        assert success is True
        assert telegram_adapter.session.post.call_count == 2
        assert sleep_mock.await_count == 1
        audit_calls = telegram_adapter._test_audit_adapter.calls
        assert len(audit_calls) == 1
        assert audit_calls[0]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_429_honors_retry_after(self, telegram_adapter) -> None:
        telegram_adapter.session = _session_with_responses(
            _response_context(
                429,
                json_body={"ok": False, "error_code": 429, "parameters": {"retry_after": 2}},
                text='{"ok":false,"error_code":429}',
            ),
            _response_context(200, json_body={"ok": True, "result": {"message_id": 8}}),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
            success = await telegram_adapter._send_alert("msg")
        await asyncio.sleep(0)

        assert success is True
        sleep_mock.assert_awaited_once_with(2)

    @pytest.mark.asyncio
    async def test_does_not_retry_client_4xx(self, telegram_adapter) -> None:
        telegram_adapter.session = _session_with_responses(
            _response_context(400, text="Bad Request: chat not found"),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock:
            success = await telegram_adapter._send_alert("msg")
        await asyncio.sleep(0)

        assert success is False
        assert telegram_adapter.session.post.call_count == 1
        assert sleep_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_retries_on_network_error_then_succeeds(self, telegram_adapter) -> None:
        import aiohttp

        ok_context = _response_context(200, json_body={"ok": True, "result": {"message_id": 9}})
        session = MagicMock()
        session.post = MagicMock(
            side_effect=[aiohttp.ClientConnectionError("dns failure"), ok_context],
        )
        telegram_adapter.session = session

        with patch("asyncio.sleep", new_callable=AsyncMock):
            success = await telegram_adapter._send_alert("msg")
        await asyncio.sleep(0)

        assert success is True
        assert session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_gives_up_after_max_attempts_with_single_audit(self, telegram_adapter) -> None:
        telegram_adapter.session = _session_with_responses(
            _response_context(500, text="Server error"),
            _response_context(502, text="Bad gateway"),
            _response_context(503, text="Unavailable"),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            success = await telegram_adapter._send_alert("msg", alert_type="error")
        await asyncio.sleep(0)

        assert success is False
        assert telegram_adapter.session.post.call_count == 3
        audit_calls = telegram_adapter._test_audit_adapter.calls
        assert len(audit_calls) == 1
        assert audit_calls[0]["status"] == "failed"
        assert audit_calls[0]["response_status"] == 503

    @pytest.mark.asyncio
    async def test_retried_send_consumes_single_rate_limit_slot(self, telegram_adapter) -> None:
        telegram_adapter.session = _session_with_responses(
            _response_context(500, text="Server error"),
            _response_context(200, json_body={"ok": True, "result": {"message_id": 10}}),
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            success = await telegram_adapter._send_alert("msg")
        await asyncio.sleep(0)

        assert success is True
        assert len(telegram_adapter._message_times) == 1
