"""
Refactored Event Bus System with Dependency Injection

A high-performance async event bus for handling real-time trading events.
Uses dependency injection for subscription management and event processing.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from .models import BaseEvent, EventType
from .core.interfaces import (
    EventBusInterface,
    SubscriptionManagerInterface,
    EventProcessorInterface,
)
from .core.event_bus_factory import EventBusConfig
from .core.error_handling import (
    ErrorCategory,
    ErrorSeverity,
    QueueError,
    ProcessingError,
    error_boundary,
    create_error_context,
    handle_error,
)


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

        # Event processing queue
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)

        # Worker management
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()

        logger.info(f"EventBus initialized with {config.num_workers} workers")

    @error_boundary(
        "EventBus", "start", ErrorCategory.CONFIGURATION, ErrorSeverity.HIGH
    )
    async def start(self, num_workers: Optional[int] = None) -> None:
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
        event_types: Optional[List[EventType]] = None,
        priority: int = 0,
        max_retries: int = 3,
    ) -> str:
        """
        Subscribe to events.

        Args:
            subscriber_id: Unique identifier for the subscriber
            handler: Function to handle events
            event_types: List of event types to subscribe to (None for all)
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

            # Add to processing queue
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

    async def publish_many(self, events: List[BaseEvent]) -> int:
        """
        Publish multiple events.

        Args:
            events: List of events to publish

        Returns:
            Number of events successfully queued
        """
        successful = 0
        for event in events:
            if await self.publish(event):
                successful += 1
        return successful

    async def get_metrics(self) -> Dict[str, Any]:
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

    async def health_check(self) -> Dict[str, Any]:
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
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                await self._process_event_with_subscriptions(event)

            except asyncio.TimeoutError:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(0.1)

        logger.info(f"Worker {worker_name} stopped")

    @error_boundary(
        "EventBus", "process_event", ErrorCategory.PROCESSING, ErrorSeverity.MEDIUM
    )
    async def _process_event_with_subscriptions(self, event: BaseEvent) -> None:
        """
        Process an event by getting subscriptions and delegating to processor.

        Args:
            event: The event to process
        """
        # Get relevant subscriptions from subscription manager
        subscriptions = await self._subscription_manager.get_subscriptions_for_event(
            event.event_type
        )

        # Process event with subscriptions using event processor
        result = await self._event_processor.process_event(event, subscriptions)

        # Update subscription manager with success/failure tracking
        for error in result.errors:
            await self._subscription_manager.record_subscription_failure(
                error.subscription_id, error.error_message
            )

        # Record successes (any subscription not in errors)
        failed_subscription_ids = {error.subscription_id for error in result.errors}
        for subscription in subscriptions:
            if subscription.subscription_id not in failed_subscription_ids:
                await self._subscription_manager.record_subscription_success(
                    subscription.subscription_id
                )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
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
_global_event_bus: Optional[EventBus] = None


def set_event_bus(bus: EventBus) -> None:
    """
    Set the global event bus instance.

    Args:
        bus: The EventBus instance to set as global
    """
    global _global_event_bus
    _global_event_bus = bus


def get_event_bus() -> EventBus:
    """
    Get the global event bus instance.

    Returns:
        The global EventBus instance

    Raises:
        RuntimeError: If no event bus has been set
    """
    if _global_event_bus is None:
        raise RuntimeError("No event bus has been set. Call set_event_bus() first.")
    return _global_event_bus


async def publish_event(topic: str, data: Dict[str, Any]) -> bool:
    """
    Simplified interface to publish an event to the global event bus.

    Args:
        topic: The event topic (e.g., "candles.v1")
        data: The event data dictionary

    Returns:
        True if published successfully

    Raises:
        RuntimeError: If no event bus has been set
    """
    bus = get_event_bus()
    event = BaseEvent(
        event_type=EventType.CANDLE_UPDATE if topic == "candles.v1" else EventType.CANDLE_UPDATE,
        timestamp=data.get("timestamp", datetime.utcnow()),
        data=data
    )
    return await bus.publish(event)
