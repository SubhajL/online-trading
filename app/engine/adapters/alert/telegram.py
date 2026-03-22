"""Telegram alert adapter for sending trading notifications."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import logging
import os
from typing import Any

import aiohttp

from .alert_deduplicator import AlertDeduplicator
from .alert_formatter import AlertFormatter

logger = logging.getLogger(__name__)

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404


class TelegramAlertAdapter:
    """Send trading alerts to Telegram chat."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        rate_limit_per_minute: int = 30,
        db_adapter: Any | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.rate_limit_per_minute = rate_limit_per_minute
        self.db_adapter = db_adapter

        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session: aiohttp.ClientSession | None = None
        self.formatter = AlertFormatter()
        self.deduplicator = AlertDeduplicator()
        self.error_deduplicator = AlertDeduplicator(
            ttl_seconds=int(os.getenv("TELEGRAM_ERROR_DEDUP_TTL_SECONDS", "300")),
        )
        self.startup_deduplicator = AlertDeduplicator(
            ttl_seconds=int(os.getenv("TELEGRAM_STARTUP_DEDUP_TTL_SECONDS", "3600")),
            key_prefix="alert:dedup:startup",
        )
        self._audit_tasks: set[asyncio.Task[None]] = set()

        # Rate limiting
        self._message_times: list[datetime] = []

    def _json_safe(self, value: Any) -> Any:
        """Convert audit payloads to JSON-safe primitives."""
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        if isinstance(value, dict):
            return {str(k): self._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        return value

    async def _record_audit(  # noqa: PLR0913
        self,
        *,
        alert_type: str,
        delivery_method: str,
        status: str,
        reason: str | None = None,
        dedup_key: str | None = None,
        telegram_message_id: int | None = None,
        message_text: str | None = None,
        response_status: int | None = None,
        response_body: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist one outbound alert audit row when a DB adapter is available."""
        insert = getattr(self.db_adapter, "insert_outbound_alert_audit", None)
        if not callable(insert):
            return

        try:
            await insert(
                channel="telegram",
                alert_type=alert_type,
                delivery_method=delivery_method,
                status=status,
                reason=reason,
                chat_id=self.chat_id,
                dedup_key=dedup_key,
                telegram_message_id=telegram_message_id,
                message_text=message_text,
                response_status=response_status,
                response_body=response_body,
                payload=self._json_safe(payload) if payload is not None else None,
                attempted_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception("Failed to persist outbound alert audit")

    def _schedule_audit_record(self, **kwargs: Any) -> None:
        task = asyncio.create_task(self._record_audit(**kwargs))
        self._audit_tasks.add(task)

        def _finalize(done: asyncio.Task[None]) -> None:
            self._audit_tasks.discard(done)
            if done.cancelled():
                return
            try:
                done.result()
            except Exception:
                logger.exception("Background outbound alert audit task failed")

        task.add_done_callback(_finalize)

    async def start(self) -> None:
        """Initialize HTTP session for sending Telegram alerts.

        Subscription to events is handled elsewhere (e.g. AlertSubscriber).
        """
        self.session = aiohttp.ClientSession()
        logger.info("Telegram alert adapter started")

    async def stop(self) -> None:
        """Clean up resources."""
        if self._audit_tasks:
            await asyncio.gather(*self._audit_tasks, return_exceptions=True)
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Telegram alert adapter stopped")

    def _normalize_image_url(self, image_url: str, bff_url: str) -> str:
        """Normalize image URL - join relative URLs with BFF base URL."""
        if image_url.startswith("/"):
            return f"{bff_url.rstrip('/')}{image_url}"
        return image_url

    async def _get_snapshot_url(
        self,
        signal_id: str,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ) -> str | None:
        """Fetch snapshot URL from BFF API with retry logic."""
        if not self.session:
            logger.error("TelegramAlertAdapter session not initialized")
            return None

        # Get BFF URL from environment - default to port 3001 (BFF port)
        bff_url = os.getenv("BFF_URL", "http://localhost:3001")
        api_key = os.getenv("INTERNAL_ALERTS_TOKEN", "")

        url = f"{bff_url}/api/signals/{signal_id}/snapshot"
        headers = {"Authorization": f"Bearer {api_key}"}

        for attempt in range(max_retries):
            try:
                async with self.session.get(url, headers=headers) as response:
                    if response.status == _HTTP_OK:
                        data = await response.json()
                        image_url = data.get("imageUrl")
                        if image_url:
                            return self._normalize_image_url(image_url, bff_url)
                        return None

                    # Retry on 404 (snapshot not ready yet)
                    if response.status == _HTTP_NOT_FOUND and attempt < max_retries - 1:
                        logger.debug(
                            "Snapshot not ready, retry %d/%d",
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue

                    logger.warning("Failed to get snapshot URL: %s", response.status)
                    return None

            except (aiohttp.ClientError, TimeoutError):
                if attempt < max_retries - 1:
                    logger.debug(
                        "Snapshot fetch error, retry %d/%d",
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                logger.exception("Error fetching snapshot URL")
                return None

        return None

    async def _download_snapshot(self, snapshot_url: str) -> bytes | None:
        """Download snapshot image data."""
        try:
            if not self.session:
                logger.error("TelegramAlertAdapter session not initialized")
                return None

            async with self.session.get(snapshot_url) as response:
                if response.status == _HTTP_OK:
                    return await response.read()
                logger.warning("Failed to download snapshot: %s", response.status)
                return None

        except (aiohttp.ClientError, TimeoutError):
            logger.exception("Error downloading snapshot")
            return None

    async def _handle_decision(self, event: dict[str, Any]) -> None:
        """Handle trading decision events."""
        try:
            # Reserve dedup key (atomic) to prevent concurrent duplicates
            symbol = event.get("symbol")
            side = event.get("side")
            timestamp = event.get("timestamp", "")
            key = f"decision:{symbol}:{side}:{timestamp}"
            if not self.deduplicator.reserve(key):
                logger.debug("Skipping duplicate decision alert: %s", key)
                self._schedule_audit_record(
                    alert_type="decision",
                    delivery_method="text",
                    status="skipped",
                    reason="deduplicated",
                    dedup_key=key,
                    payload=event,
                )
                return

            # Format message
            message = self.formatter.format_decision(event)

            # Check if there's a snapshot available
            signal_id = event.get("signal_id")
            snapshot_sent = False

            if signal_id:
                # Try to fetch snapshot from BFF API
                snapshot_url = await self._get_snapshot_url(signal_id)
                if snapshot_url:
                    # Download snapshot
                    image_data = await self._download_snapshot(snapshot_url)
                    if image_data:
                        # Send as photo with caption
                        snapshot_sent = await self._send_photo_alert(
                            image_data,
                            message,
                            alert_type="decision",
                            payload=event,
                            dedup_key=key,
                        )

            # If no snapshot or photo send failed, send text message
            if not snapshot_sent:
                success = await self._send_alert(
                    message,
                    alert_type="decision",
                    payload=event,
                    dedup_key=key,
                )
            else:
                success = snapshot_sent

            if not success:
                self.deduplicator.clear(key)

        except Exception:
            logger.exception("Error handling decision event")

    async def _handle_order_update(self, event: dict[str, Any]) -> None:
        """Handle order update events."""
        try:
            # Only alert on important status changes
            status = event.get("status")
            normalized_status = (
                status.lower() if isinstance(status, str) else str(status).lower()
            ).replace("cancelled", "canceled")

            important_statuses = {"new", "filled", "canceled", "rejected"}
            if normalized_status not in important_statuses:
                return
            event["status"] = normalized_status

            message = self.formatter.format_order_update(event)
            await self._send_alert(
                message,
                alert_type="order_update",
                payload=event,
            )

        except Exception:
            logger.exception("Error handling order update")

    async def _handle_guard_alert(self, event: dict[str, Any]) -> None:
        """Handle risk guard alerts."""
        try:
            message = self.formatter.format_guard_alert(event)
            await self._send_alert(
                message,
                alert_type="guard",
                payload=event,
            )

        except Exception:
            logger.exception("Error handling guard alert")

    async def send_startup_alert(self, startup_data: dict[str, Any]) -> bool:
        """Send a startup/warmup complete alert to Telegram.

        Args:
            startup_data: Dict with phase, symbols, timeframes, candle_counts, duration_seconds

        Returns:
            True if message was sent successfully, False otherwise.
        """
        try:
            phase = startup_data.get("phase")
            symbols = startup_data.get("symbols")
            timeframes = startup_data.get("timeframes")
            key: str | None = None
            if (
                isinstance(phase, str)
                and isinstance(symbols, list)
                and isinstance(timeframes, list)
            ):
                key = f"{phase}:{','.join(sorted(map(str, symbols)))}:{','.join(sorted(map(str, timeframes)))}"
                if not self.startup_deduplicator.reserve(key):
                    self._schedule_audit_record(
                        alert_type="startup",
                        delivery_method="text",
                        status="skipped",
                        reason="deduplicated",
                        dedup_key=key,
                        payload=startup_data,
                    )
                    return False

            message = self.formatter.format_startup_alert(startup_data)
            sent = await self._send_alert(
                message,
                alert_type="startup",
                payload=startup_data,
                dedup_key=key,
            )
            if not sent and key is not None:
                self.startup_deduplicator.clear(key)
            return sent

        except Exception:
            logger.exception("Error sending startup alert")
            return False

    async def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now(tz=UTC)
        cutoff = now - timedelta(minutes=1)

        # Remove old messages
        self._message_times = [t for t in self._message_times if t > cutoff]

        # Check limit
        if len(self._message_times) >= self.rate_limit_per_minute:
            logger.warning("Telegram rate limit reached")
            return False

        self._message_times.append(now)
        return True

    async def _send_alert(
        self,
        message: str,
        *,
        alert_type: str = "generic",
        payload: dict[str, Any] | None = None,
        dedup_key: str | None = None,
    ) -> bool:
        """Send a message to Telegram."""
        if not await self._check_rate_limit():
            self._schedule_audit_record(
                alert_type=alert_type,
                delivery_method="text",
                status="skipped",
                reason="rate_limited",
                dedup_key=dedup_key,
                message_text=message,
                payload=payload,
            )
            return False

        try:
            if not self.session:
                logger.error("TelegramAlertAdapter session not initialized")
                return False

            url = f"{self.base_url}/sendMessage"
            request_payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            async with self.session.post(url, json=request_payload) as response:
                if response.status != _HTTP_OK:
                    text = await response.text()
                    logger.error(
                        "Telegram HTTP error %s: %s",
                        response.status,
                        text,
                    )
                    self._schedule_audit_record(
                        alert_type=alert_type,
                        delivery_method="text",
                        status="failed",
                        reason="http_error",
                        dedup_key=dedup_key,
                        message_text=message,
                        response_status=response.status,
                        response_body=text,
                        payload=payload,
                    )
                    return False

                data = await response.json()
                if data.get("ok"):
                    logger.debug("Telegram alert sent successfully")
                    result = data.get("result") or {}
                    message_id = result.get("message_id")
                    self._schedule_audit_record(
                        alert_type=alert_type,
                        delivery_method="text",
                        status="sent",
                        dedup_key=dedup_key,
                        telegram_message_id=message_id if isinstance(message_id, int) else None,
                        message_text=message,
                        response_status=response.status,
                        payload=payload,
                    )
                    return True

                logger.error("Telegram API error: %s", data)
                self._schedule_audit_record(
                    alert_type=alert_type,
                    delivery_method="text",
                    status="failed",
                    reason="api_error",
                    dedup_key=dedup_key,
                    message_text=message,
                    response_status=response.status,
                    response_body=str(data),
                    payload=payload,
                )
                return False

        except Exception:
            logger.exception("Error sending Telegram alert")
            self._schedule_audit_record(
                alert_type=alert_type,
                delivery_method="text",
                status="failed",
                reason="exception",
                dedup_key=dedup_key,
                message_text=message,
                payload=payload,
            )
            return False

    async def send_error_alert(self, message: str, *, dedup_key: str | None = None) -> bool:
        """Send an error alert with optional Redis-backed deduplication."""
        if dedup_key and not self.error_deduplicator.reserve(dedup_key):
            self._schedule_audit_record(
                alert_type="error",
                delivery_method="text",
                status="skipped",
                reason="deduplicated",
                dedup_key=dedup_key,
                message_text=message,
                payload={"dedup_key": dedup_key},
            )
            return False

        sent = await self._send_alert(
            message,
            alert_type="error",
            payload={"dedup_key": dedup_key} if dedup_key else None,
            dedup_key=dedup_key,
        )
        if not sent and dedup_key:
            self.error_deduplicator.clear(dedup_key)
        return sent

    async def _send_photo_alert(
        self,
        image_data: bytes,
        caption: str,
        *,
        alert_type: str = "generic",
        payload: dict[str, Any] | None = None,
        dedup_key: str | None = None,
    ) -> bool:
        """Send a photo with caption to Telegram."""
        if not await self._check_rate_limit():
            self._schedule_audit_record(
                alert_type=alert_type,
                delivery_method="photo",
                status="skipped",
                reason="rate_limited",
                dedup_key=dedup_key,
                message_text=caption,
                payload=payload,
            )
            return False

        try:
            if not self.session:
                logger.error("TelegramAlertAdapter session not initialized")
                return False

            url = f"{self.base_url}/sendPhoto"

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field("chat_id", self.chat_id)
            data.add_field("parse_mode", "HTML")
            data.add_field("caption", caption)
            data.add_field(
                "photo",
                image_data,
                filename="signal.png",
                content_type="image/png",
            )

            async with self.session.post(url, data=data) as response:
                if response.status != _HTTP_OK:
                    text = await response.text()
                    logger.error(
                        "Telegram HTTP error %s: %s",
                        response.status,
                        text,
                    )
                    self._schedule_audit_record(
                        alert_type=alert_type,
                        delivery_method="photo",
                        status="failed",
                        reason="http_error",
                        dedup_key=dedup_key,
                        message_text=caption,
                        response_status=response.status,
                        response_body=text,
                        payload=payload,
                    )
                    return False

                result = await response.json()
                if result.get("ok"):
                    logger.debug("Telegram photo alert sent successfully")
                    response_payload = result.get("result") or {}
                    message_id = response_payload.get("message_id")
                    self._schedule_audit_record(
                        alert_type=alert_type,
                        delivery_method="photo",
                        status="sent",
                        dedup_key=dedup_key,
                        telegram_message_id=message_id if isinstance(message_id, int) else None,
                        message_text=caption,
                        response_status=response.status,
                        payload=payload,
                    )
                    return True

                logger.error("Telegram API error: %s", result)
                self._schedule_audit_record(
                    alert_type=alert_type,
                    delivery_method="photo",
                    status="failed",
                    reason="api_error",
                    dedup_key=dedup_key,
                    message_text=caption,
                    response_status=response.status,
                    response_body=str(result),
                    payload=payload,
                )
                return False

        except Exception:
            logger.exception("Error sending Telegram photo alert")
            self._schedule_audit_record(
                alert_type=alert_type,
                delivery_method="photo",
                status="failed",
                reason="exception",
                dedup_key=dedup_key,
                message_text=caption,
                payload=payload,
            )
            return False
