"""Telegram alert adapter for sending trading notifications."""

import asyncio
from datetime import UTC, datetime, timedelta
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
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.rate_limit_per_minute = rate_limit_per_minute

        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session: aiohttp.ClientSession | None = None
        self.formatter = AlertFormatter()
        self.deduplicator = AlertDeduplicator()

        # Rate limiting
        self._message_times: list[datetime] = []

    async def start(self) -> None:
        """Initialize HTTP session for sending Telegram alerts.

        Subscription to events is handled elsewhere (e.g. AlertSubscriber).
        """
        self.session = aiohttp.ClientSession()
        logger.info("Telegram alert adapter started")

    async def stop(self) -> None:
        """Clean up resources."""
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
            # Check for duplicate
            symbol = event.get("symbol")
            side = event.get("side")
            timestamp = event.get("timestamp", "")
            key = f"decision:{symbol}:{side}:{timestamp}"
            if self.deduplicator.is_duplicate(key):
                logger.debug("Skipping duplicate decision alert: %s", key)
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
                        )

            # If no snapshot or photo send failed, send text message
            if not snapshot_sent:
                success = await self._send_alert(message)
            else:
                success = snapshot_sent

            if success:
                self.deduplicator.add(key)

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
            await self._send_alert(message)

        except Exception:
            logger.exception("Error handling order update")

    async def _handle_guard_alert(self, event: dict[str, Any]) -> None:
        """Handle risk guard alerts."""
        try:
            message = self.formatter.format_guard_alert(event)
            await self._send_alert(message)

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
            message = self.formatter.format_startup_alert(startup_data)
            return await self._send_alert(message)

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

    async def _send_alert(self, message: str) -> bool:
        """Send a message to Telegram."""
        if not await self._check_rate_limit():
            return False

        try:
            if not self.session:
                logger.error("TelegramAlertAdapter session not initialized")
                return False

            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            async with self.session.post(url, json=payload) as response:
                if response.status != _HTTP_OK:
                    text = await response.text()
                    logger.error(
                        "Telegram HTTP error %s: %s",
                        response.status,
                        text,
                    )
                    return False

                data = await response.json()
                if data.get("ok"):
                    logger.debug("Telegram alert sent successfully")
                    return True

                logger.error("Telegram API error: %s", data)
                return False

        except Exception:
            logger.exception("Error sending Telegram alert")
            return False

    async def _send_photo_alert(self, image_data: bytes, caption: str) -> bool:
        """Send a photo with caption to Telegram."""
        if not await self._check_rate_limit():
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
                    return False

                result = await response.json()
                if result.get("ok"):
                    logger.debug("Telegram photo alert sent successfully")
                    return True

                logger.error("Telegram API error: %s", result)
                return False

        except Exception:
            logger.exception("Error sending Telegram photo alert")
            return False
