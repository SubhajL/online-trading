"""
Telegram delivery service for chart snapshots and trading signals.
"""

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import FormData

from app.engine.models import RetestSignal, RetestSignalEvent
from app.engine.monitoring.metrics import record_snapshot_delivery

logger = logging.getLogger(__name__)


class TelegramDelivery:
    """Handles delivery of trading signals and chart snapshots to Telegram."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Telegram delivery service.

        Args:
            config: Configuration including bot_token, chat_id, etc.
        """
        self.bot_token = config.get("bot_token", "")
        self.chat_id = config.get("chat_id", "")
        self.api_url = config.get("api_url", "https://api.telegram.org")
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)

    def _format_signal_caption(self, signal: RetestSignal) -> str:
        """Format signal into Telegram caption with markdown.

        Args:
            signal: The retest signal to format

        Returns:
            Formatted caption string
        """
        # Determine signal direction
        retest_map = {
            "support_retest": ("🔵", "Support Retest", "BUY"),
            "resistance_retest": ("🔴", "Resistance Retest", "SELL"),
            "zone_retest": ("🟢", "Zone Retest", "NEUTRAL"),
        }

        emoji, retest_display, direction = retest_map.get(
            signal.retest_type,
            ("⚪", signal.retest_type, "UNKNOWN"),
        )

        # Basic info
        lines = [
            f"{emoji} *{retest_display} Signal*",
            f"📊 *{signal.symbol}* - {signal.timeframe.value}",
            "",
            f"💰 *Level Price:* ${signal.level_price:,.0f}",
            "",
            f"📈 *Success Probability:* {signal.success_probability * 100:.0f}%",
        ]

        # Volume confirmation
        volume_status = (
            "✅ Confirmed" if signal.volume_confirmation else "⚠️ Not Confirmed"
        )
        lines.append(f"📊 *Volume:* {volume_status}")

        # Confluence factors
        if signal.confluence_factors:
            lines.append("\n*Confluence Factors:*")
            reason_map = {
                "BOS": "Break of Structure",
                "EMA_support": "EMA Support",
                "RSI_oversold": "RSI Oversold",
                "CHOCH": "Change of Character",
                "demand_zone": "Demand Zone",
                "supply_zone": "Supply Zone",
                "trend_alignment": "Trend Alignment",
                "volume_spike": "Volume Spike",
            }

            for factor in signal.confluence_factors:
                display_factor = reason_map.get(factor, factor)
                lines.append(f"✓ {display_factor}")

        # Timestamp
        lines.extend(
            [
                "",
                f"🕐 {signal.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            ]
        )

        return "\n".join(lines)

    async def send_snapshot(
        self,
        image_data: bytes,
        caption: str,
        signal_event: RetestSignalEvent | None = None,
    ) -> dict[str, Any]:
        """Send chart snapshot to Telegram.

        Args:
            image_data: PNG image data
            caption: Caption text for the image
            signal_event: Optional signal event for additional context

        Returns:
            Dict with success status and message_id or error
        """
        url = f"{self.api_url}/bot{self.bot_token}/sendPhoto"

        # Prepare multipart form data
        form = FormData()
        form.add_field("chat_id", str(self.chat_id))
        form.add_field(
            "photo", image_data, filename="chart.png", content_type="image/png"
        )
        form.add_field("caption", caption)
        form.add_field("parse_mode", "Markdown")

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as response:
                        result = await response.json()

                        if response.status == 200 and result.get("ok"):
                            # Success
                            record_snapshot_delivery("telegram")
                            return {
                                "success": True,
                                "message_id": result["result"]["message_id"],
                            }

                        # Handle specific errors
                        error_code = result.get("error_code", 0)
                        error_desc = result.get("description", "Unknown error")

                        if error_code == 429:  # Rate limited
                            retry_after = result.get("parameters", {}).get(
                                "retry_after", 60
                            )
                            logger.warning(
                                f"Telegram rate limit, retry after {retry_after}s"
                            )
                            await asyncio.sleep(min(retry_after, 60))
                            continue

                        if error_code == 400:
                            if "chat not found" in error_desc:
                                return {"success": False, "error": "Chat not found"}
                            if "message is too long" in error_desc:
                                # Truncate caption and retry
                                caption = caption[:1000] + "..."
                                continue

                        elif error_code == 401:
                            return {"success": False, "error": "Invalid bot token"}

                        elif error_code == 413:
                            return {"success": False, "error": "Image too large"}

                        # Other errors - retry
                        logger.error(f"Telegram API error: {error_code} - {error_desc}")

            except TimeoutError:
                logger.error(f"Telegram timeout on attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                logger.error(f"Network error on attempt {attempt + 1}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")

            # Wait before retry
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2**attempt)  # Exponential backoff

        return {"success": False, "error": "Max retries exceeded"}

    async def send_text_alert(self, message: str) -> dict[str, Any]:
        """Send text-only alert to Telegram.

        Args:
            message: Alert message text

        Returns:
            Dict with success status
        """
        url = f"{self.api_url}/bot{self.bot_token}/sendMessage"

        data = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_notification": False,
        }

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response,
            ):
                result = await response.json()

                if response.status == 200 and result.get("ok"):
                    return {"success": True}

                return {
                    "success": False,
                    "error": result.get("description", "Unknown error"),
                }

        except Exception as e:
            logger.error(f"Failed to send text alert: {e}")
            return {"success": False, "error": str(e)}
