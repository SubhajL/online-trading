"""Redis bridge for forwarding event bus events to Redis pub/sub."""

from collections.abc import Awaitable, Callable
import logging
from typing import Protocol, runtime_checkable

from app.engine.models import BaseEvent, EventType

logger = logging.getLogger(__name__)

# Type alias for async event handler callbacks
EventHandler = Callable[[BaseEvent], Awaitable[None]]


@runtime_checkable
class RedisPublisher(Protocol):
    """Protocol for Redis publish capability."""

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a channel."""
        ...


@runtime_checkable
class EventBusSubscriber(Protocol):
    """Protocol for EventBus subscription capability."""

    async def subscribe(
        self,
        subscriber_id: str,
        handler: EventHandler,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str:
        """Subscribe to events."""
        ...

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        ...


class RedisBridge:
    """Forward event bus events to Redis pub/sub channels.

    Subscribes to all events from the event bus and publishes them
    to Redis channels in the format: engine:{event_type}
    """

    def __init__(
        self,
        redis_adapter: RedisPublisher,
        event_bus: EventBusSubscriber,
    ) -> None:
        self._redis = redis_adapter
        self._bus = event_bus
        self._subscription_id: str | None = None

    @property
    def is_running(self) -> bool:
        """Return True if bridge is actively subscribed."""
        return self._subscription_id is not None

    async def start(self) -> None:
        """Subscribe to all event types and forward to Redis.

        Idempotent: if already started, unsubscribes first.
        """
        if self._subscription_id:
            await self.stop()

        self._subscription_id = await self._bus.subscribe(
            subscriber_id="redis_bridge",
            handler=self.forward_to_redis,
            event_types=None,
            priority=0,
        )
        logger.info("RedisBridge started, subscribed to all events")

    async def forward_to_redis(self, event: BaseEvent) -> None:
        """Forward event to Redis channel engine:{event_type}."""
        channel = f"engine:{event.event_type.value}"
        payload = event.model_dump_json()
        try:
            await self._redis.publish(channel, payload)
        except Exception:
            logger.exception("Failed to publish event to Redis channel %s", channel)

    async def stop(self) -> None:
        """Unsubscribe from event bus."""
        if self._subscription_id:
            subscription_id = self._subscription_id
            success = await self._bus.unsubscribe(subscription_id)
            if success:
                self._subscription_id = None
                logger.info("RedisBridge stopped")
            else:
                logger.warning(
                    "Failed to unsubscribe RedisBridge: %s",
                    subscription_id,
                )
