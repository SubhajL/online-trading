"""
Unit tests for subscription manager component.
Written first following TDD principles.
"""

import pytest
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Set

from app.engine.core.subscription_manager import (
    SubscriptionManager,
    EventSubscription,
    SubscriptionConfig,
)
from app.engine.models import EventType, BaseEvent


@dataclass
class TestEvent(BaseEvent):
    """Test event for subscription tests."""

    test_data: str


class TestSubscriptionManager:
    def test_subscription_config_defaults(self):
        config = SubscriptionConfig()

        assert config.max_subscriptions == 1000
        assert config.default_priority == 0
        assert config.default_max_retries == 3

    def test_subscription_config_custom_values(self):
        config = SubscriptionConfig(
            max_subscriptions=500, default_priority=5, default_max_retries=2
        )

        assert config.max_subscriptions == 500
        assert config.default_priority == 5
        assert config.default_max_retries == 2

    @pytest.mark.asyncio
    async def test_subscription_manager_initialization(self):
        config = SubscriptionConfig()
        manager = SubscriptionManager(config)

        assert await manager.get_subscription_count() == 0
        assert await manager.get_active_subscription_count() == 0

    @pytest.mark.asyncio
    async def test_add_specific_event_subscription(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
        )

        assert subscription_id is not None
        assert await manager.get_subscription_count() == 1
        assert await manager.get_active_subscription_count() == 1

    @pytest.mark.asyncio
    async def test_add_all_events_subscription(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=None,  # Subscribe to all events
        )

        assert subscription_id is not None
        assert await manager.get_subscription_count() == 1

    @pytest.mark.asyncio
    async def test_remove_subscription_success(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
        )

        removed = await manager.remove_subscription(subscription_id)

        assert removed is True
        assert await manager.get_subscription_count() == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_subscription(self):
        manager = SubscriptionManager()

        removed = await manager.remove_subscription("nonexistent_id")

        assert removed is False

    @pytest.mark.asyncio
    async def test_get_subscriptions_for_event_type(self):
        manager = SubscriptionManager()

        async def handler1(event: BaseEvent) -> None:
            pass

        async def handler2(event: BaseEvent) -> None:
            pass

        # Add subscription for PRICE_UPDATE
        await manager.add_subscription(
            subscriber_id="subscriber1",
            handler=handler1,
            event_types=[EventType.CANDLE_UPDATE],
        )

        # Add subscription for ORDER_FILLED
        await manager.add_subscription(
            subscriber_id="subscriber2",
            handler=handler2,
            event_types=[EventType.ORDER_FILLED],
        )

        candle_subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )
        order_subscriptions = await manager.get_subscriptions_for_event(
            EventType.ORDER_FILLED
        )

        assert len(candle_subscriptions) == 1
        assert len(order_subscriptions) == 1
        assert candle_subscriptions[0].subscriber_id == "subscriber1"
        assert order_subscriptions[0].subscriber_id == "subscriber2"

    @pytest.mark.asyncio
    async def test_get_subscriptions_includes_all_events_subscribers(self):
        manager = SubscriptionManager()

        async def specific_handler(event: BaseEvent) -> None:
            pass

        async def all_handler(event: BaseEvent) -> None:
            pass

        # Add specific subscription
        await manager.add_subscription(
            subscriber_id="specific_subscriber",
            handler=specific_handler,
            event_types=[EventType.CANDLE_UPDATE],
        )

        # Add all-events subscription
        await manager.add_subscription(
            subscriber_id="all_subscriber", handler=all_handler, event_types=None
        )

        subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )

        # Should include both specific and all-events subscriptions
        assert len(subscriptions) == 2
        subscriber_ids = {sub.subscriber_id for sub in subscriptions}
        assert "specific_subscriber" in subscriber_ids
        assert "all_subscriber" in subscriber_ids

    @pytest.mark.asyncio
    async def test_subscriptions_sorted_by_priority(self):
        manager = SubscriptionManager()

        async def handler1(event: BaseEvent) -> None:
            pass

        async def handler2(event: BaseEvent) -> None:
            pass

        async def handler3(event: BaseEvent) -> None:
            pass

        # Add subscriptions with different priorities
        await manager.add_subscription(
            subscriber_id="low_priority",
            handler=handler1,
            event_types=[EventType.CANDLE_UPDATE],
            priority=1,
        )

        await manager.add_subscription(
            subscriber_id="high_priority",
            handler=handler2,
            event_types=[EventType.CANDLE_UPDATE],
            priority=10,
        )

        await manager.add_subscription(
            subscriber_id="medium_priority",
            handler=handler3,
            event_types=[EventType.CANDLE_UPDATE],
            priority=5,
        )

        subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )

        # Should be sorted by priority (descending)
        assert len(subscriptions) == 3
        assert subscriptions[0].subscriber_id == "high_priority"
        assert subscriptions[1].subscriber_id == "medium_priority"
        assert subscriptions[2].subscriber_id == "low_priority"

    @pytest.mark.asyncio
    async def test_max_subscriptions_limit_enforced(self):
        config = SubscriptionConfig(max_subscriptions=2)
        manager = SubscriptionManager(config)

        async def handler(event: BaseEvent) -> None:
            pass

        # Add two subscriptions - should succeed
        await manager.add_subscription(
            subscriber_id="subscriber1",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
        )

        await manager.add_subscription(
            subscriber_id="subscriber2",
            handler=handler,
            event_types=[EventType.ORDER_FILLED],
        )

        # Third subscription should fail
        with pytest.raises(Exception) as exc_info:
            await manager.add_subscription(
                subscriber_id="subscriber3",
                handler=handler,
                event_types=[EventType.TRADING_DECISION],
            )

        assert "maximum number of subscriptions" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_subscription_retry_tracking(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
            max_retries=3,
        )

        # Get subscription to check retry tracking
        subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )
        subscription = subscriptions[0]

        assert subscription.retry_count == 0
        assert subscription.max_retries == 3
        assert subscription.is_active is True

        # Simulate failure
        await manager.record_subscription_failure(subscription_id, "Test error")

        # Check retry count increased
        subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )
        subscription = subscriptions[0]
        assert subscription.retry_count == 1
        assert subscription.last_error == "Test error"
        assert subscription.is_active is True

    @pytest.mark.asyncio
    async def test_subscription_disabled_after_max_retries(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
            max_retries=2,
        )

        # Simulate failures up to max retries
        await manager.record_subscription_failure(subscription_id, "Error 1")
        await manager.record_subscription_failure(subscription_id, "Error 2")

        # Subscription should still be active
        assert await manager.get_active_subscription_count() == 1

        # One more failure should disable it
        await manager.record_subscription_failure(subscription_id, "Error 3")

        assert await manager.get_active_subscription_count() == 0

    @pytest.mark.asyncio
    async def test_subscription_success_resets_retry_count(self):
        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        subscription_id = await manager.add_subscription(
            subscriber_id="test_subscriber",
            handler=handler,
            event_types=[EventType.CANDLE_UPDATE],
        )

        # Record failure then success
        await manager.record_subscription_failure(subscription_id, "Test error")
        await manager.record_subscription_success(subscription_id)

        subscriptions = await manager.get_subscriptions_for_event(
            EventType.CANDLE_UPDATE
        )
        subscription = subscriptions[0]

        assert subscription.retry_count == 0
        assert subscription.last_error is None

    @pytest.mark.asyncio
    async def test_concurrent_subscription_operations_thread_safe(self):
        import asyncio

        manager = SubscriptionManager()

        async def handler(event: BaseEvent) -> None:
            pass

        # Add subscriptions concurrently
        tasks = []
        for i in range(50):
            task = manager.add_subscription(
                subscriber_id=f"subscriber_{i}",
                handler=handler,
                event_types=[EventType.CANDLE_UPDATE],
            )
            tasks.append(task)

        subscription_ids = await asyncio.gather(*tasks)

        # All should be unique and successful
        assert len(subscription_ids) == 50
        assert len(set(subscription_ids)) == 50  # All unique
        assert await manager.get_subscription_count() == 50
