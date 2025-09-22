"""Telegram alert adapter for sending trading notifications."""

import asyncio
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

import aiohttp

from .alert_formatter import AlertFormatter
from .alert_deduplicator import AlertDeduplicator


logger = logging.getLogger(__name__)


class TelegramAlertAdapter:
    """Send trading alerts to Telegram chat."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        event_bus: Any,
        rate_limit_per_minute: int = 30,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.event_bus = event_bus
        self.rate_limit_per_minute = rate_limit_per_minute

        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.formatter = AlertFormatter()
        self.deduplicator = AlertDeduplicator()

        # Rate limiting
        self._message_times: list[datetime] = []

    async def start(self):
        """Initialize the adapter and subscribe to events."""
        self.session = aiohttp.ClientSession()

        # Subscribe to relevant events
        await self.event_bus.subscribe("decision.v1", self._handle_decision)
        await self.event_bus.subscribe("order_update.v1", self._handle_order_update)
        await self.event_bus.subscribe("guard_alert.v1", self._handle_guard_alert)

        logger.info("Telegram alert adapter started")

    async def stop(self):
        """Clean up resources."""
        if self.session:
            await self.session.close()
        logger.info("Telegram alert adapter stopped")

    async def _handle_decision(self, event: Dict[str, Any]):
        """Handle trading decision events."""
        try:
            # Check for duplicate
            key = f"decision:{event['symbol']}:{event['side']}:{event.get('timestamp', '')}"
            if self.deduplicator.is_duplicate(key):
                logger.debug(f"Skipping duplicate decision alert: {key}")
                return

            # Format and send
            message = self.formatter.format_decision(event)
            success = await self._send_alert(message)

            if success:
                self.deduplicator.add(key)

        except Exception as e:
            logger.error(f"Error handling decision event: {e}", exc_info=True)

    async def _handle_order_update(self, event: Dict[str, Any]):
        """Handle order update events."""
        try:
            # Only alert on important status changes
            important_statuses = {"filled", "cancelled", "rejected"}
            if event.get("status") not in important_statuses:
                return

            message = self.formatter.format_order_update(event)
            await self._send_alert(message)

        except Exception as e:
            logger.error(f"Error handling order update: {e}", exc_info=True)

    async def _handle_guard_alert(self, event: Dict[str, Any]):
        """Handle risk guard alerts."""
        try:
            message = self.formatter.format_guard_alert(event)
            await self._send_alert(message)

        except Exception as e:
            logger.error(f"Error handling guard alert: {e}", exc_info=True)

    async def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now()
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
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }

            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("ok"):
                        logger.debug("Telegram alert sent successfully")
                        return True
                    else:
                        logger.error(f"Telegram API error: {data}")
                else:
                    text = await response.text()
                    logger.error(f"Telegram HTTP error {response.status}: {text}")

            return False

        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}", exc_info=True)
            return False