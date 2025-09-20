"""
Refactored Event Bus with dependency injection and improved architecture.
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Set
from uuid import UUID, uuid4

from app.engine.config import EventBusConfig
from app.engine.models import BaseEvent, ErrorEvent, EventType


logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class PublishResult:
    """Result of publishing an event."""

    is_success: bool
    event_id: UUID
    error: Optional[str] = None


@dataclass
class SubscriptionStatus:
    """Status of a subscription."""

    subscription_id: str
    is_active: bool
    circuit_breaker_state: CircuitBreakerState
    processed_count: int
    failed_count: int
    last_error: Optional[str]


class PersistenceBackend(Protocol):
    """Protocol for event persistence backends."""

    async def persist_event(self, event: BaseEvent) -> None:
        """Persist an event."""
        ...

    async def get_events(self, limit: int) -> List[BaseEvent]:
        """Retrieve persisted events."""
        ...


class MetricsBackend(Protocol):
    """Protocol for metrics backends."""

    def record_event_published(self, event_type: str) -> None:
        """Record event publication."""
        ...

    def record_event_processed(self, duration: float, subscriber: str) -> None:
        """Record event processing."""
        ...

    def record_event_failed(self, error_type: str, subscriber: str) -> None:
        """Record event failure."""
        ...


class InMemoryPersistence:
    """In-memory persistence implementation."""

    def __init__(self, max_size: int = 10000):
        self._events = deque(maxlen=max_size)

    async def persist_event(self, event: BaseEvent) -> None:
        self._events.append(event)

    async def get_events(self, limit: int) -> List[BaseEvent]:
        return list(self._events)[-limit:]


class InMemoryMetrics:
    """In-memory metrics implementation."""

    def __init__(self):
        self.events_published = 0
        self.events_processed = 0
        self.events_failed = 0
        self.processing_times: deque = deque(maxlen=1000)
        self.error_counts: Dict[str, int] = defaultdict(int)

    def record_event_published(self, event_type: str) -> None:
        self.events_published += 1

    def record_event_processed(self, duration: float, subscriber: str) -> None:
        self.events_processed += 1
        self.processing_times.append(duration)

    def record_event_failed(self, error_type: str, subscriber: str) -> None:
        self.events_failed += 1
        self.error_counts[error_type] += 1


class CircuitBreaker:
    """Circuit breaker for fault tolerance."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED

    def record_success(self) -> None:
        """Record successful execution."""
        self.failure_count = 0
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN

    def is_open(self) -> bool:
        """Check if circuit breaker is open."""
        if self.state == CircuitBreakerState.CLOSED:
            return False

        if self.state == CircuitBreakerState.OPEN:
            if self.last_failure_time:
                elapsed = asyncio.get_event_loop().time() - self.last_failure_time
                if elapsed > self.reset_timeout:
                    self.state = CircuitBreakerState.HALF_OPEN
                    return False
            return True

        return False


class EventSubscription:
    """Enhanced event subscription with circuit breaker."""

    def __init__(
        self,
        subscriber_id: str,
        handler: Callable[[BaseEvent], Any],
        event_types: Optional[Set[EventType]] = None,
        priority: int = 0,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
        circuit_breaker_threshold: int = 5,
    ):
        self.subscription_id = str(uuid4())
        self.subscriber_id = subscriber_id
        self.handler = handler
        self.event_types = event_types or set()
        self.priority = priority
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.retry_count = 0
        self.last_error: Optional[str] = None
        self.is_active = True
        self.created_at = datetime.utcnow()
        self.processed_count = 0
        self.failed_count = 0
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=circuit_breaker_threshold
        )


class EventBus:
    """
    Refactored Event Bus with dependency injection and improved patterns.
    """

    def __init__(
        self,
        config: EventBusConfig,
        persistence_backend: Optional[PersistenceBackend] = None,
        metrics_backend: Optional[MetricsBackend] = None,
    ):
        self._config = config
        self._max_queue_size = config.max_queue_size
        self._num_workers = config.num_workers
        self._enable_persistence = config.enable_persistence

        self._persistence_backend = persistence_backend or InMemoryPersistence()
        self._metrics_backend = metrics_backend or InMemoryMetrics()

        self._subscriptions: Dict[EventType, List[EventSubscription]] = defaultdict(
            list
        )
        self._all_subscriptions: List[EventSubscription] = []
        self._subscription_map: Dict[str, EventSubscription] = {}

        self._event_queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=config.max_queue_size
        )
        self._dead_letter_queue: asyncio.Queue = asyncio.Queue(
            maxsize=config.dead_letter_queue_size
        )

        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._lock = asyncio.Lock()

        logger.info(f"EventBus initialized with config: {config}")

    async def start(self) -> None:
        """Start the event bus workers."""
        if self._running:
            logger.warning("EventBus is already running")
            return

        self._running = True

        for i in range(self._num_workers):
            task = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(task)

        logger.info(f"EventBus started with {self._num_workers} workers")

    async def stop(self) -> None:
        """Stop the event bus workers."""
        if not self._running:
            return

        self._running = False

        for task in self._worker_tasks:
            task.cancel()

        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        logger.info("EventBus stopped")

    async def subscribe(
        self,
        subscriber_id: str,
        handler: Callable[[BaseEvent], Any],
        event_types: Optional[List[EventType]] = None,
        priority: int = 0,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
        circuit_breaker_threshold: int = 5,
    ) -> str:
        """Subscribe to events with enhanced options."""
        async with self._lock:
            event_type_set = set(event_types) if event_types else set()
            subscription = EventSubscription(
                subscriber_id=subscriber_id,
                handler=handler,
                event_types=event_type_set,
                priority=priority,
                max_retries=max_retries,
                retry_delay_ms=retry_delay_ms,
                circuit_breaker_threshold=circuit_breaker_threshold,
            )

            if event_types:
                for event_type in event_types:
                    self._subscriptions[event_type].append(subscription)
                    self._subscriptions[event_type].sort(
                        key=lambda s: s.priority, reverse=True
                    )
            else:
                self._all_subscriptions.append(subscription)
                self._all_subscriptions.sort(key=lambda s: s.priority, reverse=True)

            self._subscription_map[subscription.subscription_id] = subscription

            logger.info(
                f"Subscriber '{subscriber_id}' subscribed with ID {subscription.subscription_id}"
            )
            return subscription.subscription_id

    async def publish(self, event: BaseEvent, priority: int = 0) -> PublishResult:
        """Publish an event with improved result handling."""
        try:
            event.metadata["priority"] = priority
            event.metadata["published_at"] = datetime.utcnow().isoformat()

            if self._enable_persistence:
                await self._persistence_backend.persist_event(event)

            # Use priority queue with negative priority for max-heap behavior
            await self._event_queue.put((-priority, datetime.utcnow(), event))
            self._metrics_backend.record_event_published(event.event_type.value)

            return PublishResult(is_success=True, event_id=event.event_id)

        except asyncio.QueueFull:
            error_msg = f"Event queue full, dropping event {event.event_id}"
            logger.error(error_msg)
            return PublishResult(
                is_success=False, event_id=event.event_id, error=error_msg
            )

        except Exception as e:
            error_msg = f"Error publishing event: {e}"
            logger.error(error_msg)
            return PublishResult(
                is_success=False, event_id=event.event_id, error=str(e)
            )

    async def get_subscription_status(
        self, subscription_id: str
    ) -> Optional[SubscriptionStatus]:
        """Get status of a subscription."""
        subscription = self._subscription_map.get(subscription_id)
        if not subscription:
            return None

        return SubscriptionStatus(
            subscription_id=subscription_id,
            is_active=subscription.is_active,
            circuit_breaker_state=subscription.circuit_breaker.state,
            processed_count=subscription.processed_count,
            failed_count=subscription.failed_count,
            last_error=subscription.last_error,
        )

    async def _worker_loop(self, worker_name: str) -> None:
        """Worker loop for processing events."""
        logger.info(f"Worker {worker_name} started")

        while self._running:
            try:
                priority, timestamp, event = await asyncio.wait_for(
                    self._event_queue.get(), timeout=1.0
                )
                await self._process_event(event, worker_name)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(0.1)

        logger.info(f"Worker {worker_name} stopped")

    async def _process_event(self, event: BaseEvent, worker_name: str) -> None:
        """Process a single event with circuit breaker support."""
        start_time = asyncio.get_event_loop().time()

        subscriptions = []
        if event.event_type in self._subscriptions:
            subscriptions.extend(self._subscriptions[event.event_type])
        subscriptions.extend(self._all_subscriptions)

        unique_subscriptions = {sub.subscription_id: sub for sub in subscriptions}
        sorted_subscriptions = sorted(
            unique_subscriptions.values(), key=lambda s: s.priority, reverse=True
        )

        for subscription in sorted_subscriptions:
            if not subscription.is_active or subscription.circuit_breaker.is_open():
                continue

            try:
                await self._handle_subscription_with_retry(event, subscription)
                processing_time = asyncio.get_event_loop().time() - start_time
                self._metrics_backend.record_event_processed(
                    processing_time, subscription.subscriber_id
                )
                subscription.processed_count += 1
                subscription.circuit_breaker.record_success()

            except Exception as e:
                await self._handle_subscription_error(event, subscription, e)

    async def _handle_subscription_with_retry(
        self, event: BaseEvent, subscription: EventSubscription
    ) -> None:
        """Handle subscription with retry logic."""
        attempt = 0
        last_error = None

        while attempt <= subscription.max_retries:
            try:
                if asyncio.iscoroutinefunction(subscription.handler):
                    await subscription.handler(event)
                else:
                    subscription.handler(event)
                return

            except Exception as e:
                attempt += 1
                last_error = e
                if attempt <= subscription.max_retries:
                    await asyncio.sleep(subscription.retry_delay_ms / 1000.0)

        if last_error:
            raise last_error

    async def _handle_subscription_error(
        self, event: BaseEvent, subscription: EventSubscription, error: Exception
    ) -> None:
        """Handle subscription processing error."""
        subscription.failed_count += 1
        subscription.last_error = str(error)
        subscription.circuit_breaker.record_failure()

        error_type = type(error).__name__
        self._metrics_backend.record_event_failed(
            error_type, subscription.subscriber_id
        )

        logger.error(f"Error in subscription {subscription.subscription_id}: {error}")

        if subscription.circuit_breaker.is_open():
            logger.error(
                f"Circuit breaker opened for subscription {subscription.subscription_id}"
            )

        # If we got here, it means _handle_subscription_with_retry exhausted all retries
        # and raised an exception, so send to dead letter queue
        await self._send_to_dead_letter_queue(event, str(error))

    async def _send_to_dead_letter_queue(
        self, event: BaseEvent, error_msg: str
    ) -> None:
        """Send event to dead letter queue."""
        try:
            event.metadata["dead_letter_reason"] = error_msg
            event.metadata["dead_letter_timestamp"] = datetime.utcnow().isoformat()
            await self._dead_letter_queue.put(event)
        except asyncio.QueueFull:
            logger.error("Dead letter queue full, dropping event")

    async def get_dead_letter_events(self, limit: int = 100) -> List[BaseEvent]:
        """Get events from dead letter queue."""
        events = []
        queue_size = self._dead_letter_queue.qsize()

        # Get all events from the queue
        temp_events = []
        for _ in range(queue_size):
            try:
                event = self._dead_letter_queue.get_nowait()
                temp_events.append(event)
            except asyncio.QueueEmpty:
                break

        # Put them back and return up to limit
        for event in temp_events:
            await self._dead_letter_queue.put(event)
            if len(events) < limit:
                events.append(event)

        return events

    async def get_metrics(self) -> Dict[str, Any]:
        """Get event bus metrics."""
        metrics = self._metrics_backend
        if isinstance(metrics, InMemoryMetrics):
            return {
                "events_published": metrics.events_published,
                "events_processed": metrics.events_processed,
                "events_failed": metrics.events_failed,
                "queue_size": self._event_queue.qsize(),
                "dead_letter_queue_size": self._dead_letter_queue.qsize(),
            }
        return {}


def create_event_bus(
    config: EventBusConfig,
    persistence_backend: Optional[PersistenceBackend] = None,
    metrics_backend: Optional[MetricsBackend] = None,
) -> EventBus:
    """Factory function to create configured EventBus instance."""
    return EventBus(
        config=config,
        persistence_backend=persistence_backend,
        metrics_backend=metrics_backend,
    )


# Export all public classes and functions
__all__ = [
    "EventBus",
    "EventBusConfig",
    "CircuitBreakerState",
    "PublishResult",
    "SubscriptionStatus",
    "PersistenceBackend",
    "MetricsBackend",
    "InMemoryPersistence",
    "InMemoryMetrics",
    "CircuitBreaker",
    "EventSubscription",
    "create_event_bus",
]
