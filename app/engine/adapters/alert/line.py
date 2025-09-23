"""LINE alert adapter for sending trading notifications."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import aiohttp

from .alert_formatter import AlertFormatter
from .alert_deduplicator import AlertDeduplicator


logger = logging.getLogger(__name__)

# LINE message length limit
LINE_MESSAGE_LIMIT = 5000


class LineAlertAdapter:
    """Send trading alerts to LINE Messaging API."""

    def __init__(
        self,
        access_token: str,
        user_id: str,  # LINE user ID to send messages to
        event_bus: Any,
        rate_limit_per_minute: int = 60,
    ) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self.event_bus = event_bus
        self.rate_limit_per_minute = rate_limit_per_minute

        self.base_url = "https://api.line.me/v2/bot"
        self.session: Optional[aiohttp.ClientSession] = None
        self.formatter = AlertFormatter()
        self.deduplicator = AlertDeduplicator()

        # Rate limiting
        self._message_times: List[datetime] = []

    async def start(self) -> None:
        """Initialize the adapter and subscribe to events."""
        self.session = aiohttp.ClientSession()

        # Subscribe to relevant events
        await self.event_bus.subscribe("decision.v1", self._handle_decision)
        await self.event_bus.subscribe("order_update.v1", self._handle_order_update)
        await self.event_bus.subscribe("guard_alert.v1", self._handle_guard_alert)

        logger.info("LINE alert adapter started")

    async def stop(self) -> None:
        """Clean up resources."""
        if self.session:
            await self.session.close()
        logger.info("LINE alert adapter stopped")

    async def _handle_decision(self, event: Dict[str, Any]) -> None:
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

    async def _handle_order_update(self, event: Dict[str, Any]) -> None:
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

    async def _handle_guard_alert(self, event: Dict[str, Any]) -> None:
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
            logger.warning("LINE rate limit reached")
            return False

        self._message_times.append(now)
        return True

    def _split_message(self, message: str) -> List[str]:
        """Split long messages to fit LINE's limit."""
        if len(message) <= LINE_MESSAGE_LIMIT:
            return [message]

        # Split by lines first
        lines = message.split('\n')
        chunks = []
        current_chunk = []
        current_length = 0

        for line in lines:
            line_length = len(line) + 1  # +1 for newline
            
            if current_length + line_length > LINE_MESSAGE_LIMIT:
                # Start new chunk
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_length = line_length
            else:
                current_chunk.append(line)
                current_length += line_length

        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    async def _send_alert(self, message: str) -> bool:
        """Send a message to LINE."""
        if not await self._check_rate_limit():
            return False

        try:
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
                        }
                    ],
                }

                async with self.session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        logger.debug("LINE alert sent successfully")
                    else:
                        text = await response.text()
                        logger.error(f"LINE API error {response.status}: {text}")
                        success = False

                # Small delay between chunks
                if len(chunks) > 1:
                    await asyncio.sleep(0.5)

            return success

        except Exception as e:
            logger.error(f"Error sending LINE alert: {e}", exc_info=True)
            return False