"""
Refactored Event Bus System with Dependency Injection

A high-performance async event bus for handling real-time trading events.
Uses dependency injection for subscription management and event processing.
"""

import asyncio
from datetime import datetime
import logging
from typing import Any

from .core.error_handling import (
    ErrorCategory,
    ErrorSeverity,
    ProcessingError,
    QueueError,
    create_error_context,
    error_boundary,
    handle_error,
)
from .core.event_bus_factory import EventBusConfig
from .core.interfaces import (
    EventProcessorInterface,
    SubscriptionManagerInterface,
)
from .models import BaseEvent, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """
    Refactored event bus using dependency injection for better testability.

    Uses injected SubscriptionManager and EventProcessor components
    for separation of concerns and improved maintainability.
    """

    def __init__(
        self,
        subscription_manager: SubscriptionManagerInterface,
        event_processor: EventProcessorInterface,
        config: EventBusConfig,
    ):
        """
        Initialize EventBus with injected dependencies.

        Args:
            subscription_manager: Component for managing subscriptions
            event_processor: Component for processing events
            config: Configuration for the event bus
        """
        self._subscription_manager = subscription_manager
        self._event_processor = event_processor
        self._config = config
        self._use_priority_queue: bool = getattr(config, "use_priority_queue", True)
        self._dlq_on_any_failure: bool = getattr(config, "dlq_on_any_failure", False)

        # Event processing queue (priority or FIFO)
        if self._use_priority_queue:
            self._event_queue: asyncio.PriorityQueue[Any] = asyncio.PriorityQueue(
                maxsize=config.max_queue_size,
            )
        else:
            self._event_queue = asyncio.Queue(maxsize=config.max_queue_size)  # type: ignore[assignment]

        # Dead-letter queue
        self._dead_letter_queue: asyncio.Queue[Any] = asyncio.Queue(
            maxsize=config.dead_letter_queue_size,
        )

        # Worker management
        self._running = False
        self._worker_tasks: list[asyncio.Task[Any]] = []
        self._lock = asyncio.Lock()

        logger.info(f"EventBus initialized with {config.num_workers} workers")

    @error_boundary(
        "EventBus",
        "start",
        ErrorCategory.CONFIGURATION,
        ErrorSeverity.HIGH,
    )
    async def start(self, num_workers: int | None = None) -> None:
        """Start the event bus workers."""
        if self._running:
            logger.warning("EventBus is already running")
            return

        worker_count = num_workers or self._config.num_workers
        self._running = True

        # Start worker tasks
        for i in range(worker_count):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)

        logger.info(f"EventBus started with {worker_count} workers")

    async def stop(self) -> None:
        """Stop the event bus workers."""
        if not self._running:
            return

        self._running = False

        # Cancel all worker tasks
        for task in self._worker_tasks:
            task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        logger.info("EventBus stopped")

    async def subscribe(
        self,
        subscriber_id: str,
        handler: Any,
        event_types: list[EventType] | None = None,
        priority: int = 0,
        max_retries: int = 3,
    ) -> str:
        """
        Subscribe to events.

        Args:
            subscriber_id: Unique identifier for the subscriber
            handler: Function to handle events
            event_types: List[Any] of event types to subscribe to (None for all)
            priority: Priority level (higher = processed first)
            max_retries: Maximum retry attempts on failure

        Returns:
            Subscription ID
        """
        return await self._subscription_manager.add_subscription(
            subscriber_id=subscriber_id,
            handler=handler,
            event_types=event_types,
            priority=priority,
            max_retries=max_retries,
        )

    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from events.

        Args:
            subscription_id: The subscription ID to remove

        Returns:
            True if subscription was found and removed
        """
        return await self._subscription_manager.remove_subscription(subscription_id)

    async def publish(self, event: BaseEvent, priority: int = 0) -> bool:
        """
        Publish an event to the bus.

        Args:
            event: The event to publish
            priority: Event priority (higher = processed first)

        Returns:
            True if event was queued successfully
        """
        if not self._running:
            logger.warning("EventBus not running, dropping event")
            return False

        try:
            # Add priority to event metadata
            event.metadata["priority"] = priority
            event.metadata["published_at"] = asyncio.get_event_loop().time()

            # Add to processing queue respecting queue mode
            if self._use_priority_queue:
                await self._event_queue.put(
                    (-priority, asyncio.get_event_loop().time(), event)
                )
            else:
                await self._event_queue.put(event)
            logger.debug(f"Published event {event.event_type} for {event.symbol}")
            return True

        except asyncio.QueueFull:
            context = create_error_context(
                category=ErrorCategory.QUEUE,
                severity=ErrorSeverity.HIGH,
                component="EventBus",
                operation="publish",
                event_id=str(event.event_id),
                queue_size=self._event_queue.qsize(),
            )
            error = QueueError(
                f"Event queue full, dropping event {event.event_id}",
                queue_size=self._event_queue.qsize(),
                context=context,
            )
            await handle_error(error)
            return False
        except Exception as e:
            context = create_error_context(
                category=ErrorCategory.PROCESSING,
                severity=ErrorSeverity.MEDIUM,
                component="EventBus",
                operation="publish",
                event_id=str(event.event_id),
            )
            error = ProcessingError(
                f"Error publishing event: {e}",
                event_id=event.event_id,
                context=context,
                cause=e,
            )
            await handle_error(error)
            return False

    async def publish_many(self, events: list[BaseEvent]) -> int:
        """
        Publish multiple events.

        Args:
            events: List[Any] of events to publish

        Returns:
            Number of events successfully queued
        """
        successful = 0
        for event in events:
            if await self.publish(event):
                successful += 1
        return successful

    async def get_metrics(self) -> dict[str, Any]:
        """
        Get aggregated metrics from all components.

        Returns:
            Dictionary containing aggregated metrics
        """
        # Get subscription manager metrics
        subscription_count = await self._subscription_manager.get_subscription_count()
        active_subscription_count = (
            await self._subscription_manager.get_active_subscription_count()
        )

        # Get event processor metrics
        processor_stats = await self._event_processor.get_stats()

        return {
            "subscription_count": subscription_count,
            "active_subscription_count": active_subscription_count,
            "events_processed": processor_stats.events_processed,
            "events_failed": processor_stats.events_failed,
            "successful_handlers": processor_stats.successful_handlers,
            "failed_handlers": processor_stats.failed_handlers,
            "average_processing_time": processor_stats.average_processing_time,
            "queue_size": self._event_queue.qsize(),
            "queue_max_size": self._event_queue.maxsize,
            "worker_count": len(self._worker_tasks),
            "is_running": self._running,
        }

    async def health_check(self) -> dict[str, Any]:
        """
        Get health status of the event bus.

        Returns:
            Dictionary containing health information
        """
        subscription_count = await self._subscription_manager.get_subscription_count()
        active_subscription_count = (
            await self._subscription_manager.get_active_subscription_count()
        )
        processor_stats = await self._event_processor.get_stats()

        return {
            "status": "running" if self._running else "stopped",
            "worker_count": len(self._worker_tasks),
            "queue_usage": f"{self._event_queue.qsize()}/{self._event_queue.maxsize}",
            "subscription_count": subscription_count,
            "active_subscription_count": active_subscription_count,
            "events_processed": processor_stats.events_processed,
        }

    async def reset_metrics(self) -> None:
        """Reset all metrics."""
        await self._event_processor.reset_stats()

    async def _worker_loop(self, worker_name: str) -> None:
        """
        Main worker loop for processing events.

        Args:
            worker_name: Name of the worker for logging
        """
        logger.info(f"Worker {worker_name} started")

        while self._running:
            try:
                # Get event from queue with timeout
                if self._use_priority_queue:
                    _prio, _ts, event = await asyncio.wait_for(
                        self._event_queue.get(), timeout=1.0
                    )
                else:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                # Measure per-event processing time
                start = asyncio.get_event_loop().time()
                result = await self._process_event_with_subscriptions(event)
                # DLQ policy
                try:
                    if result is not None and result.failed_handlers > 0:
                        if self._dlq_on_any_failure or result.successful_handlers == 0:
                            await self._maybe_enqueue_dead_letter(
                                event,
                                reason=(
                                    "any_handler_failed"
                                    if self._dlq_on_any_failure
                                    else "all_handlers_failed"
                                ),
                            )
                except Exception as e:  # noqa: BLE001
                    logger.error(f"DLQ enqueue error: {e}")
                elapsed = (asyncio.get_event_loop().time() - start) * 1000.0

                # Warn if processing exceeds configured threshold
                try:
                    threshold_ms = getattr(
                        self._config, "slow_event_warning_threshold_ms", 100
                    )
                except Exception:
                    threshold_ms = 100
                if elapsed > threshold_ms:
                    logger.warning(
                        f"Slow event processing: {elapsed:.2f}ms (threshold {threshold_ms}ms)",
                    )

            except TimeoutError:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(0.1)

        logger.info(f"Worker {worker_name} stopped")

    @error_boundary(
        "EventBus",
        "process_event",
        ErrorCategory.PROCESSING,
        ErrorSeverity.MEDIUM,
    )
    async def _process_event_with_subscriptions(self, event: BaseEvent) -> Any:
        """
        Process an event by getting subscriptions and delegating to processor.

        Args:
            event: The event to process
        """
        # Get relevant subscriptions from subscription manager
        subscriptions = await self._subscription_manager.get_subscriptions_for_event(
            event.event_type,
        )

        # Process event with subscriptions using event processor
        result = await self._event_processor.process_event(event, subscriptions)

        # Update subscription manager with success/failure tracking
        for error in result.errors:
            await self._subscription_manager.record_subscription_failure(
                error.subscription_id,
                error.error_message,
            )

        # Record successes (any subscription not in errors)
        failed_subscription_ids = {error.subscription_id for error in result.errors}
        for subscription in subscriptions:
            if subscription.subscription_id not in failed_subscription_ids:
                await self._subscription_manager.record_subscription_success(
                    subscription.subscription_id,
                )
        return result

    async def _maybe_enqueue_dead_letter(self, event: BaseEvent, reason: str) -> None:
        """Enqueue event into dead letter queue with reason."""
        try:
            event.metadata["dead_letter_reason"] = reason
            event.metadata["dead_letter_timestamp"] = datetime.utcnow().isoformat()
            await self._dead_letter_queue.put(event)
        except asyncio.QueueFull:
            logger.error("Dead letter queue full, dropping event")

    async def get_dead_letter_events(self, limit: int = 100) -> list[BaseEvent]:
        """Return up to limit events from DLQ without draining it."""
        events: list[BaseEvent] = []
        size = self._dead_letter_queue.qsize()
        tmp: list[BaseEvent] = []
        for _ in range(size):
            try:
                ev = self._dead_letter_queue.get_nowait()
                tmp.append(ev)
            except asyncio.QueueEmpty:
                break
        for ev in tmp:
            await self._dead_letter_queue.put(ev)
            if len(events) < limit:
                events.append(ev)
        return events

    async def get_subscription_status(
        self, subscription_id: str
    ) -> dict[str, Any] | None:
        """Get subscription status including circuit breaker state."""
        sub = await self._subscription_manager.get_subscription_by_id(subscription_id)
        if not sub:
            return None
        cb_state = await self._event_processor.get_circuit_breaker_state(
            sub.subscriber_id
        )
        return {
            "subscription_id": subscription_id,
            "subscriber_id": sub.subscriber_id,
            "is_active": sub.is_active,
            "retry_count": sub.retry_count,
            "circuit_breaker_state": cb_state,
        }

    async def __aenter__(self) -> None:
        """Async context manager entry."""
        await self.start()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()


# Global event bus factory function for convenience
def create_event_bus() -> EventBus:
    """
    Create a new EventBus instance with default configuration.

    For production use, prefer using EventBusFactory directly.
    """
    from .core.event_bus_factory import EventBusFactory

    factory = EventBusFactory()
    return factory.create_event_bus()


# Global event bus instance management
_global_event_bus: EventBus | None = None


def set_event_bus(bus: EventBus) -> None:
    """
    Set[Any] the global event bus instance.

    Args:
        bus: The EventBus instance to set[Any] as global
    """
    global _global_event_bus
    _global_event_bus = bus


def get_event_bus() -> EventBus:
    """
    Get the global event bus instance.

    Returns:
        The global EventBus instance

    Raises:
        RuntimeError: If no event bus has been set[Any]
    """
    if _global_event_bus is None:
        raise RuntimeError(
            "No event bus has been set[Any]. Call set_event_bus() first."
        )
    return _global_event_bus


async def publish_event(topic: str, data: dict[str, Any]) -> bool:
    """
    Simplified interface to publish an event to the global event bus.

    Args:
        topic: The event topic (e.g., "candles.v1")
        data: The event data dictionary

    Returns:
        True if published successfully

    Raises:
        RuntimeError: If no event bus has been set[Any]
    """
    bus = get_event_bus()
    event = BaseEvent(
        event_type=(
            EventType.CANDLE_UPDATE
            if topic == "candles.v1"
            else EventType.CANDLE_UPDATE
        ),
        timestamp=data.get("timestamp", datetime.utcnow()),
        data=data,
    )
    return await bus.publish(event)
