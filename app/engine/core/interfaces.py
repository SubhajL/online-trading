"""
Interfaces and protocols for event bus dependency injection.
Defines contracts for all major components.
"""

from typing import Any, Protocol

from app.engine.core.event_processor import (
    EventProcessingResult,
    EventProcessingStats,
)
from app.engine.core.subscription_manager import EventSubscription
from app.engine.models import BaseEvent, EventType


class SubscriptionManagerInterface(Protocol):
    """Protocol for subscription management components."""

    async def add_subscription(
        self,
        subscriber_id: str,
        handler: Any,
        event_types: list[EventType] | None = None,
        priority: int | None = None,
        max_retries: int | None = None,
    ) -> str:
        """Add a new subscription and return subscription ID."""
        ...

    async def remove_subscription(self, subscription_id: str) -> bool:
        """Remove subscription by ID. Returns True if found and removed."""
        ...

    async def get_subscriptions_for_event(
        self,
        event_type: EventType,
    ) -> list[EventSubscription]:
        """Get all active subscriptions for an event type."""
        ...

    async def get_subscription_count(self) -> int:
        """Get total number of subscriptions."""
        ...

    async def get_active_subscription_count(self) -> int:
        """Get number of active subscriptions."""
        ...

    async def record_subscription_failure(
        self,
        subscription_id: str,
        error_message: str,
    ) -> None:
        """Record a subscription failure."""
        ...

    async def record_subscription_success(self, subscription_id: str) -> None:
        """Record a subscription success."""
        ...


class EventProcessorInterface(Protocol):
    """Protocol for event processing components."""

    async def process_event(
        self,
        event: BaseEvent,
        subscriptions: list[EventSubscription],
    ) -> EventProcessingResult:
        """Process an event with given subscriptions."""
        ...

    async def get_stats(self) -> EventProcessingStats:
        """Get processing statistics."""
        ...

    async def reset_stats(self) -> None:
        """Reset processing statistics."""
        ...


class EventBusInterface(Protocol):
    """Protocol for event bus implementations."""

    async def start(self, num_workers: int | None = None) -> None:
        """Start the event bus workers."""
        ...

    async def stop(self) -> None:
        """Stop the event bus workers."""
        ...

    async def subscribe(
        self,
        subscriber_id: str,
        handler: Any,
        event_types: list[EventType] | None = None,
        priority: int = 0,
        max_retries: int = 3,
    ) -> str:
        """Subscribe to events and return subscription ID."""
        ...

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        ...

    async def publish(self, event: BaseEvent, priority: int = 0) -> bool:
        """Publish an event to the bus."""
        ...

    async def publish_many(self, events: list[BaseEvent]) -> int:
        """Publish multiple events."""
        ...

    async def get_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics from all components."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Get health status of the event bus."""
        ...

    async def reset_metrics(self) -> None:
        """Reset all metrics."""
        ...


class ClockInterface(Protocol):
    """Protocol for clock implementations."""

    def now(self) -> Any:
        """Get current time."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Sleep for given seconds."""
        ...


class CircuitBreakerInterface(Protocol):
    """Protocol for circuit breaker implementations."""

    async def should_allow_request(self) -> bool:
        """Check if request should be allowed."""
        ...

    async def record_success(self) -> None:
        """Record a successful operation."""
        ...

    async def record_failure(self) -> None:
        """Record a failed operation."""
        ...

    async def get_state(self) -> Any:
        """Get current circuit breaker state."""
        ...

    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        ...
