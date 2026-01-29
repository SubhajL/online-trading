"""
Orchestrates delivery of trading signals and snapshots to multiple channels.
"""

import asyncio
from datetime import datetime
import logging
from typing import Any

from app.engine.models import RetestSignalEvent

from .storage import SnapshotStorage
from .telegram import TelegramDelivery
from .websocket import WebSocketDelivery

logger = logging.getLogger(__name__)


class DeliveryOrchestrator:
    """Coordinates delivery of signals and snapshots across multiple channels."""

    def __init__(self):
        """Initialize delivery orchestrator."""
        self.channels: dict[str, Any] = {}
        self.storage: SnapshotStorage | None = None
        self._initialize_channels()

    def _initialize_channels(self):
        """Initialize delivery channels based on configuration."""
        # Initialize based on environment variables
        import os

        # Telegram
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_token:
            telegram_config = {
                "bot_token": telegram_token,
                "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
                "api_url": os.getenv("TELEGRAM_API_URL", "https://api.telegram.org"),
                "timeout": int(os.getenv("TELEGRAM_TIMEOUT", "30")),
                "max_retries": int(os.getenv("TELEGRAM_MAX_RETRIES", "3")),
            }
            self.channels["telegram"] = TelegramDelivery(telegram_config)
            logger.info("Telegram delivery channel initialized")

        # WebSocket
        ws_url = os.getenv("WEBSOCKET_SERVER_URL")
        if ws_url:
            self.channels["websocket"] = WebSocketDelivery(ws_url)
            logger.info("WebSocket delivery channel initialized")

        # Storage
        storage_type = os.getenv("SNAPSHOT_STORAGE_TYPE", "local")
        if storage_type == "s3":
            from .storage import S3SnapshotStorage

            self.storage = S3SnapshotStorage(
                bucket=os.getenv("S3_BUCKET", "trading-snapshots"),
                prefix=os.getenv("S3_PREFIX", "signals/"),
                region=os.getenv("AWS_REGION", "us-east-1"),
            )
        else:
            from .storage import LocalSnapshotStorage

            self.storage = LocalSnapshotStorage(
                base_path=os.getenv("SNAPSHOT_PATH", "./snapshots"),
            )

    async def deliver_snapshot(
        self,
        signal_event: RetestSignalEvent,
        snapshot_data: bytes,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Deliver snapshot to specified channels.

        Args:
            signal_event: The signal event that triggered the snapshot
            snapshot_data: PNG image data
            channels: List of channel names to deliver to (None = all)

        Returns:
            Dict with delivery results for each channel
        """
        results = {}
        success_count = 0
        total_channels = 0

        # Store snapshot first if storage is configured
        snapshot_url = None
        if self.storage:
            try:
                signal_id = f"signal_{int(signal_event.signal.timestamp.timestamp())}"
                snapshot_url = await self.storage.store_snapshot(
                    signal_id,
                    snapshot_data,
                )
                logger.info(f"Stored snapshot: {snapshot_url}")
            except Exception as e:
                logger.error(f"Failed to store snapshot: {e}")

        # Determine target channels
        target_channels = channels or list(self.channels.keys())

        # Deliver to each channel concurrently
        tasks = []

        for channel_name in target_channels:
            if channel_name not in self.channels:
                results[channel_name] = {
                    "success": False,
                    "error": f"Channel {channel_name} not configured",
                }
                continue

            total_channels += 1
            channel = self.channels[channel_name]

            # Create delivery task based on channel type
            if channel_name == "telegram" and isinstance(channel, TelegramDelivery):
                caption = channel._format_signal_caption(signal_event.signal)
                task = asyncio.create_task(
                    self._deliver_to_telegram(
                        channel,
                        snapshot_data,
                        caption,
                        signal_event,
                    ),
                )
                tasks.append((channel_name, task))

            elif channel_name == "websocket" and isinstance(channel, WebSocketDelivery):
                # Prepare WebSocket notification data
                ws_data = {
                    "signal_id": f"signal_{int(signal_event.signal.timestamp.timestamp())}",
                    "symbol": signal_event.signal.symbol,
                    "timeframe": signal_event.signal.timeframe.value,
                    "retest_type": signal_event.signal.retest_type,
                    "snapshot": {
                        "url": snapshot_url or "/api/snapshots/latest",
                        "width": 1200,
                        "height": 600,
                    },
                    "signal_data": {
                        "level_price": float(signal_event.signal.level_price),
                        "success_probability": float(
                            signal_event.signal.success_probability,
                        ),
                        "volume_confirmation": signal_event.signal.volume_confirmation,
                        "confluence_factors": signal_event.signal.confluence_factors,
                    },
                }
                task = asyncio.create_task(
                    self._deliver_to_websocket(channel, ws_data),
                )
                tasks.append((channel_name, task))

        # Wait for all deliveries to complete
        if tasks:
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True,
            )

            # Process results
            for i, (channel_name, _) in enumerate(tasks):
                result = task_results[i]

                if isinstance(result, Exception):
                    results[channel_name] = {
                        "success": False,
                        "error": str(result),
                    }
                else:
                    results[channel_name] = result
                    if result.get("success"):
                        success_count += 1

        # Overall success if at least one channel succeeded
        overall_success = success_count > 0

        return {
            "success": overall_success,
            "delivered": success_count,
            "total": total_channels,
            "snapshot_url": snapshot_url,
            **results,
        }

    async def _deliver_to_telegram(
        self,
        channel: TelegramDelivery,
        image_data: bytes,
        caption: str,
        signal_event: RetestSignalEvent,
    ) -> dict[str, Any]:
        """Deliver to Telegram with error handling.

        Args:
            channel: Telegram delivery channel
            image_data: Image data
            caption: Formatted caption
            signal_event: Signal event

        Returns:
            Delivery result
        """
        try:
            return await channel.send_snapshot(image_data, caption, signal_event)
        except Exception as e:
            logger.error(f"Telegram delivery error: {e}")
            return {"success": False, "error": str(e)}

    async def _deliver_to_websocket(
        self,
        channel: WebSocketDelivery,
        notification_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Deliver to WebSocket with error handling.

        Args:
            channel: WebSocket delivery channel
            notification_data: Notification data

        Returns:
            Delivery result
        """
        try:
            # Ensure WebSocket is connected
            if not channel.connected:
                await channel.connect()

            return await channel.notify_snapshot(notification_data)
        except Exception as e:
            logger.error(f"WebSocket delivery error: {e}")
            return {"success": False, "error": str(e)}

    async def send_alert(
        self,
        message: str,
        priority: str = "normal",
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send text alert to specified channels.

        Args:
            message: Alert message
            priority: Alert priority (normal, high, critical)
            channels: Target channels

        Returns:
            Delivery results
        """
        results = {}
        target_channels = channels or list(self.channels.keys())

        # Format message based on priority
        if priority == "critical":
            message = f"🚨 *CRITICAL ALERT*\n\n{message}"
        elif priority == "high":
            message = f"⚠️ *Important*\n\n{message}"

        tasks = []

        for channel_name in target_channels:
            if channel_name not in self.channels:
                continue

            channel = self.channels[channel_name]

            if channel_name == "telegram" and hasattr(channel, "send_text_alert"):
                task = asyncio.create_task(channel.send_text_alert(message))
                tasks.append((channel_name, task))

            elif channel_name == "websocket" and hasattr(channel, "broadcast_alert"):
                alert_data = {
                    "message": message,
                    "priority": priority,
                    "timestamp": datetime.now().isoformat(),
                }
                task = asyncio.create_task(channel.broadcast_alert(alert_data))
                tasks.append((channel_name, task))

        # Wait for all alerts
        if tasks:
            task_results = await asyncio.gather(
                *[task for _, task in tasks],
                return_exceptions=True,
            )

            for i, (channel_name, _) in enumerate(tasks):
                result = task_results[i]
                if isinstance(result, Exception):
                    results[channel_name] = {"success": False, "error": str(result)}
                else:
                    results[channel_name] = result

        return results

    async def shutdown(self):
        """Shutdown all delivery channels gracefully."""
        logger.info("Shutting down delivery channels...")

        tasks = []
        for channel_name, channel in self.channels.items():
            if hasattr(channel, "disconnect"):
                tasks.append(channel.disconnect())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("All delivery channels shutdown complete")
