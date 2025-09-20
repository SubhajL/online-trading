"""
Subscription manager for event bus system.
Handles subscription lifecycle and filtering.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.engine.models import BaseEvent, EventType
from .error_handling import (
    SubscriptionError,
    ErrorCategory,
    ErrorSeverity,
    error_boundary,
    create_error_context,
    handle_error
)


@dataclass
class SubscriptionConfig:
    """Configuration for subscription manager."""
    max_subscriptions: int = 1000
    default_priority: int = 0
    default_max_retries: int = 3


@dataclass
class EventSubscription:
    """Event subscription with metadata and retry tracking."""
    subscription_id: str
    subscriber_id: str
    handler: Callable[[BaseEvent], Any]
    event_types: Optional[Set[EventType]]
    priority: int
    max_retries: int
    retry_count: int = 0
    last_error: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __lt__(self, other: 'EventSubscription') -> bool:
        """Compare by priority for sorting (higher priority first)."""
        return self.priority > other.priority


# Note: Using new error handling framework
# SubscriptionTooManyError -> SubscriptionError with RESOURCE category
# SubscriptionNotFoundError -> SubscriptionError with VALIDATION category


class SubscriptionManager:
    """
    Thread-safe subscription manager for event bus.

    Handles subscription registration, removal, and filtering
    with proper priority ordering and retry tracking.
    """

    def __init__(self, config: Optional[SubscriptionConfig] = None):
        """Initialize subscription manager with optional config."""
        self._config = config or SubscriptionConfig()

        # Subscriptions by event type
        self._specific_subscriptions: Dict[EventType, List[EventSubscription]] = defaultdict(list)

        # Subscriptions for all events
        self._all_event_subscriptions: List[EventSubscription] = []

        # All subscriptions by ID for fast lookup
        self._subscriptions_by_id: Dict[str, EventSubscription] = {}

        # Thread safety
        self._lock = asyncio.Lock()

    async def add_subscription(
        self,
        subscriber_id: str,
        handler: Callable[[BaseEvent], Any],
        event_types: Optional[List[EventType]] = None,
        priority: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> str:
        """
        Add a new subscription.

        Args:
            subscriber_id: Unique identifier for the subscriber
            handler: Function to handle events
            event_types: List of event types to subscribe to (None for all)
            priority: Priority level (higher = processed first)
            max_retries: Maximum retry attempts on failure

        Returns:
            Subscription ID

        Raises:
            SubscriptionTooManyError: If max subscriptions exceeded
        """
        async with self._lock:
            # Check subscription limit
            if len(self._subscriptions_by_id) >= self._config.max_subscriptions:
                context = create_error_context(
                    category=ErrorCategory.RESOURCE,
                    severity=ErrorSeverity.HIGH,
                    component="SubscriptionManager",
                    operation="add_subscription",
                    max_subscriptions=self._config.max_subscriptions,
                    current_subscriptions=len(self._subscriptions_by_id)
                )
                # Override the default SUBSCRIPTION category for resource limits
                error = SubscriptionError(
                    f"Maximum number of subscriptions ({self._config.max_subscriptions}) exceeded",
                    subscription_id=None,
                    context=context
                )
                error.context.category = ErrorCategory.RESOURCE
                await handle_error(error)
                raise error

            # Create subscription
            subscription_id = str(uuid4())
            event_type_set = set(event_types) if event_types else None

            subscription = EventSubscription(
                subscription_id=subscription_id,
                subscriber_id=subscriber_id,
                handler=handler,
                event_types=event_type_set,
                priority=priority if priority is not None else self._config.default_priority,
                max_retries=max_retries if max_retries is not None else self._config.default_max_retries
            )

            # Store subscription
            self._subscriptions_by_id[subscription_id] = subscription

            if event_types:
                # Add to specific event type subscriptions
                for event_type in event_types:
                    self._specific_subscriptions[event_type].append(subscription)
                    # Keep sorted by priority (descending)
                    self._specific_subscriptions[event_type].sort(reverse=True)
            else:
                # Add to all-events subscriptions
                self._all_event_subscriptions.append(subscription)
                # Keep sorted by priority (descending)
                self._all_event_subscriptions.sort(reverse=True)

            return subscription_id

    async def remove_subscription(self, subscription_id: str) -> bool:
        """
        Remove a subscription.

        Args:
            subscription_id: The subscription ID to remove

        Returns:
            True if subscription was found and removed
        """
        async with self._lock:
            subscription = self._subscriptions_by_id.get(subscription_id)
            if not subscription:
                return False

            # Remove from main lookup
            del self._subscriptions_by_id[subscription_id]

            # Remove from specific event type subscriptions
            if subscription.event_types:
                for event_type in subscription.event_types:
                    subscriptions = self._specific_subscriptions[event_type]
                    try:
                        subscriptions.remove(subscription)
                    except ValueError:
                        pass  # Already removed
            else:
                # Remove from all-events subscriptions
                try:
                    self._all_event_subscriptions.remove(subscription)
                except ValueError:
                    pass  # Already removed

            return True

    async def get_subscriptions_for_event(self, event_type: EventType) -> List[EventSubscription]:
        """
        Get all active subscriptions for an event type.

        Args:
            event_type: The event type to get subscriptions for

        Returns:
            List of active subscriptions sorted by priority (descending)
        """
        async with self._lock:
            subscriptions = []

            # Add specific event type subscriptions
            if event_type in self._specific_subscriptions:
                subscriptions.extend([
                    sub for sub in self._specific_subscriptions[event_type]
                    if sub.is_active
                ])

            # Add all-events subscriptions
            subscriptions.extend([
                sub for sub in self._all_event_subscriptions
                if sub.is_active
            ])

            # Remove duplicates and sort by priority
            unique_subscriptions = {sub.subscription_id: sub for sub in subscriptions}
            sorted_subscriptions = sorted(
                unique_subscriptions.values(),
                key=lambda s: s.priority,
                reverse=True
            )

            return sorted_subscriptions

    async def get_subscription_count(self) -> int:
        """Get total number of subscriptions."""
        async with self._lock:
            return len(self._subscriptions_by_id)

    async def get_active_subscription_count(self) -> int:
        """Get number of active subscriptions."""
        async with self._lock:
            return sum(1 for sub in self._subscriptions_by_id.values() if sub.is_active)

    async def record_subscription_failure(self, subscription_id: str, error_message: str) -> None:
        """
        Record a subscription failure and update retry tracking.

        Args:
            subscription_id: The subscription that failed
            error_message: The error message

        Raises:
            SubscriptionError: If subscription not found
        """
        async with self._lock:
            subscription = self._subscriptions_by_id.get(subscription_id)
            if not subscription:
                context = create_error_context(
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.MEDIUM,
                    component="SubscriptionManager",
                    operation="record_subscription_failure",
                    subscription_id=subscription_id
                )
                error = SubscriptionError(
                    f"Subscription {subscription_id} not found",
                    subscription_id=subscription_id,
                    context=context
                )
                await handle_error(error)
                raise error

            subscription.retry_count += 1
            subscription.last_error = error_message

            # Disable if max retries exceeded
            if subscription.retry_count > subscription.max_retries:
                subscription.is_active = False

    async def record_subscription_success(self, subscription_id: str) -> None:
        """
        Record a subscription success and reset retry tracking.

        Args:
            subscription_id: The subscription that succeeded

        Raises:
            SubscriptionError: If subscription not found
        """
        async with self._lock:
            subscription = self._subscriptions_by_id.get(subscription_id)
            if not subscription:
                context = create_error_context(
                    category=ErrorCategory.VALIDATION,
                    severity=ErrorSeverity.MEDIUM,
                    component="SubscriptionManager",
                    operation="record_subscription_success",
                    subscription_id=subscription_id
                )
                error = SubscriptionError(
                    f"Subscription {subscription_id} not found",
                    subscription_id=subscription_id,
                    context=context
                )
                await handle_error(error)
                raise error

            subscription.retry_count = 0
            subscription.last_error = None