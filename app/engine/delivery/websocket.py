"""
WebSocket delivery service for real-time UI notifications.
"""

import asyncio
from datetime import datetime
import json
import logging
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from app.engine.monitoring.metrics import record_snapshot_delivery

logger = logging.getLogger(__name__)


class WebSocketDelivery:
    """Handles delivery of real-time notifications to UI via WebSocket."""

    def __init__(self, server_url: str):
        """Initialize WebSocket delivery service.

        Args:
            server_url: WebSocket server URL (e.g., ws://localhost:8002/ws)
        """
        self.server_url = server_url
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.connected = False
        self.reconnect_delay = 5
        self.heartbeat_interval = 30
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None

    async def connect(self, auto_reconnect: bool = True) -> bool:
        """Connect to WebSocket server.

        Args:
            auto_reconnect: Enable automatic reconnection

        Returns:
            True if connected successfully
        """
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            logger.info(f"Connected to WebSocket server: {self.server_url}")

            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Start reconnection monitor if enabled
            if auto_reconnect:
                self._reconnect_task = asyncio.create_task(self._monitor_connection())

            return True

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            self.connected = False

            if auto_reconnect:
                asyncio.create_task(self._reconnect())

            return False

    async def disconnect(self):
        """Disconnect from WebSocket server."""
        self.connected = False

        # Cancel tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._reconnect_task:
            self._reconnect_task.cancel()

        # Close connection
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def notify_snapshot(self, snapshot_data: dict[str, Any]) -> dict[str, Any]:
        """Send snapshot notification to UI.

        Args:
            snapshot_data: Snapshot information including signal data

        Returns:
            Dict with success status
        """
        if not self.connected or not self.websocket:
            return {"success": False, "error": "Not connected"}

        try:
            # Prepare notification message
            message = {
                "type": "chart_snapshot",
                "timestamp": datetime.now().isoformat(),
                "data": snapshot_data,
            }

            # Send to WebSocket
            await self.websocket.send(json.dumps(message))

            # Record metric
            record_snapshot_delivery("ui")

            logger.info(
                f"Sent snapshot notification for {snapshot_data.get('signal_id')}",
            )
            return {"success": True}

        except ConnectionClosed:
            logger.error("WebSocket connection closed during send")
            self.connected = False
            asyncio.create_task(self._reconnect())
            return {"success": False, "error": "Connection lost"}

        except Exception as e:
            logger.error(f"Failed to send snapshot notification: {e}")
            return {"success": False, "error": str(e)}

    async def broadcast_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        """Broadcast general alert to UI.

        Args:
            alert: Alert data to broadcast

        Returns:
            Dict with success status and client count
        """
        if not self.connected or not self.websocket:
            return {"success": False, "error": "Not connected", "clients_notified": 0}

        try:
            message = {
                "type": "alert",
                "timestamp": datetime.now().isoformat(),
                "data": alert,
            }

            await self.websocket.send(json.dumps(message))

            return {"success": True, "clients_notified": 1}

        except Exception as e:
            logger.error(f"Failed to broadcast alert: {e}")
            return {"success": False, "error": str(e), "clients_notified": 0}

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        while self.connected:
            try:
                if self.websocket:
                    pong_waiter = await self.websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=10)
                await asyncio.sleep(self.heartbeat_interval)

            except TimeoutError:
                logger.warning("Heartbeat timeout")
                self.connected = False
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                self.connected = False
                break

    async def _monitor_connection(self):
        """Monitor connection and reconnect if needed."""
        while True:
            try:
                if self.websocket:
                    # Try to receive data (will fail if disconnected)
                    await asyncio.wait_for(self.websocket.recv(), timeout=0.1)
            except TimeoutError:
                # Normal timeout, connection still alive
                pass
            except (ConnectionClosed, WebSocketException):
                logger.warning("WebSocket connection lost")
                self.connected = False
                await self._reconnect()
            except Exception as e:
                logger.error(f"Connection monitor error: {e}")

            await asyncio.sleep(5)

    async def _reconnect(self):
        """Attempt to reconnect to WebSocket server."""
        retry_count = 0
        max_retries = 10

        while retry_count < max_retries:
            logger.info(f"Attempting to reconnect... (attempt {retry_count + 1})")
            await asyncio.sleep(self.reconnect_delay * (2**retry_count))

            if await self.connect(auto_reconnect=False):
                logger.info("Reconnected successfully")
                return

            retry_count += 1

        logger.error(f"Failed to reconnect after {max_retries} attempts")


class WebSocketManager:
    """Manages multiple WebSocket client connections."""

    def __init__(self):
        """Initialize WebSocket manager."""
        self.active_connections: list[Any] = []
        self.channel_subscriptions: dict[str, set[str]] = {}

    async def connect_client(self, websocket: Any, client_id: str):
        """Register new client connection.

        Args:
            websocket: Client WebSocket connection
            client_id: Unique client identifier
        """
        self.active_connections.append(websocket)
        logger.info(
            f"Client {client_id} connected. Total clients: {len(self.active_connections)}",
        )

    async def disconnect_client(self, websocket: Any, client_id: str):
        """Remove client connection.

        Args:
            websocket: Client WebSocket connection
            client_id: Client identifier
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # Remove from channel subscriptions
        for channel, subscribers in self.channel_subscriptions.items():
            subscribers.discard(client_id)

        logger.info(
            f"Client {client_id} disconnected. Total clients: {len(self.active_connections)}",
        )

    async def subscribe_to_channel(self, client_id: str, channel: str):
        """Subscribe client to a notification channel.

        Args:
            client_id: Client identifier
            channel: Channel name (e.g., "snapshots", "alerts")
        """
        if channel not in self.channel_subscriptions:
            self.channel_subscriptions[channel] = set()

        self.channel_subscriptions[channel].add(client_id)
        logger.info(f"Client {client_id} subscribed to channel: {channel}")

    async def broadcast(self, message: dict[str, Any], exclude: set[str] | None = None):
        """Broadcast message to all connected clients.

        Args:
            message: Message to broadcast
            exclude: Set of client IDs to exclude
        """
        exclude = exclude or set()
        disconnected = []

        for connection in self.active_connections:
            if hasattr(connection, "id") and connection.id in exclude:
                continue

            try:
                await connection.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.active_connections.remove(conn)

    async def broadcast_to_channel(self, channel: str, message: dict[str, Any]):
        """Broadcast message to channel subscribers.

        Args:
            channel: Channel name
            message: Message to broadcast
        """
        subscribers = self.channel_subscriptions.get(channel, set())
        logger.info(
            f"Broadcasting to {len(subscribers)} subscribers in channel: {channel}",
        )

        # Find connections for subscribers
        target_connections = [
            conn
            for conn in self.active_connections
            if hasattr(conn, "id") and conn.id in subscribers
        ]

        await self.broadcast(message, exclude=set())
