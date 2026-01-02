"""LINE alert adapter for sending trading notifications."""

import asyncio
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import aiohttp

from .alert_deduplicator import AlertDeduplicator
from .alert_formatter import AlertFormatter

logger = logging.getLogger(__name__)

# LINE message length limit
LINE_MESSAGE_LIMIT = 5000
_HTTP_OK = 200


class LineAlertAdapter:
    """Send trading alerts to LINE Messaging API."""

    def __init__(
        self,
        access_token: str,
        user_id: str,  # LINE user ID to send messages to
        rate_limit_per_minute: int = 60,
    ) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self.rate_limit_per_minute = rate_limit_per_minute

        self.base_url = "https://api.line.me/v2/bot"
        self.session: aiohttp.ClientSession | None = None
        self.formatter = AlertFormatter()
        self.deduplicator = AlertDeduplicator()

        # Rate limiting
        self._message_times: list[datetime] = []

    async def start(self) -> None:
        """Initialize HTTP session for sending LINE alerts.

        Subscription to events is handled elsewhere (e.g. AlertSubscriber).
        """
        self.session = aiohttp.ClientSession()
        logger.info("LINE alert adapter started")

    async def stop(self) -> None:
        """Clean up resources."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("LINE alert adapter stopped")

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

            # Format and send
            message = self.formatter.format_decision(event)
            success = await self._send_alert(message)

            if success:
                self.deduplicator.add(key)

        except Exception:
            logger.exception("Error handling decision event")

    async def _handle_order_update(self, event: dict[str, Any]) -> None:
        """Handle order update events."""
        try:
            # Only alert on important status changes
            important_statuses = {"filled", "cancelled", "rejected"}
            if event.get("status") not in important_statuses:
                return

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

    async def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now(tz=UTC)
        cutoff = now - timedelta(minutes=1)

        # Remove old messages
        self._message_times = [t for t in self._message_times if t > cutoff]

        # Check limit
        if len(self._message_times) >= self.rate_limit_per_minute:
            logger.warning("LINE rate limit reached")
            return False

        self._message_times.append(now)
        return True

    def _split_message(self, message: str) -> list[str]:
        """Split long messages to fit LINE's limit."""
        if len(message) <= LINE_MESSAGE_LIMIT:
            return [message]

        lines = message.split("\n")
        chunks: list[str] = []
        current = ""

        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= LINE_MESSAGE_LIMIT:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(line) <= LINE_MESSAGE_LIMIT:
                current = line
                continue

            segments = [
                line[i : i + LINE_MESSAGE_LIMIT]
                for i in range(0, len(line), LINE_MESSAGE_LIMIT)
            ]
            chunks.extend(segments[:-1])
            current = segments[-1]

        if current:
            chunks.append(current)

        return chunks

    async def _send_alert(self, message: str) -> bool:
        """Send a message to LINE."""
        if not await self._check_rate_limit():
            return False

        if not self.session:
            logger.error("LineAlertAdapter session not initialized")
            return False

        # Split message if too long
        chunks = self._split_message(message)
        success = True

        for chunk in chunks:
            url = f"{self.base_url}/message/push"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "to": self.user_id,
                "messages": [
                    {
                        "type": "text",
                        "text": chunk,
                    },
                ],
            }

            try:
                async with self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status != _HTTP_OK:
                        text = await response.text()
                        logger.error(
                            "LINE API error %s: %s",
                            response.status,
                            text,
                        )
                        success = False
                    else:
                        logger.debug("LINE alert sent successfully")
            except Exception:
                logger.exception("Error sending LINE alert")
                success = False

            # Small delay between chunks
            if len(chunks) > 1:
                await asyncio.sleep(0.5)

        return success
