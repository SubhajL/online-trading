"""Tests for cooldown-based subscriber reactivation.

A subscriber that exceeds max_retries must not be silently and permanently
deactivated: a brief downstream outage would otherwise kill a pipeline stage
until process restart. Deactivation now carries a cooldown after which the
dispatch-time lookup reactivates the subscription with reset retry state.
"""

from __future__ import annotations

import pytest

from app.engine.core.clock import FakeClock
from app.engine.core.subscription_manager import SubscriptionConfig, SubscriptionManager
from app.engine.models import EventType

COOLDOWN_SECONDS = 60.0
MAX_RETRIES = 3


async def _handler(event: object) -> None:
    del event


async def _make_deactivated_subscription(
    manager: SubscriptionManager,
) -> str:
    sub_id = await manager.add_subscription(
        subscriber_id="features",
        handler=_handler,
        event_types=[EventType.CANDLE_UPDATE],
        max_retries=MAX_RETRIES,
    )
    for _ in range(MAX_RETRIES + 1):
        await manager.record_subscription_failure(sub_id, "db down")
    return sub_id


class TestCooldownReactivation:
    @pytest.mark.asyncio
    async def test_deactivation_sets_cooldown_and_warns(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        clock = FakeClock()
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=COOLDOWN_SECONDS),
            clock=clock,
        )

        with caplog.at_level("WARNING", logger="app.engine.core.subscription_manager"):
            sub_id = await _make_deactivated_subscription(manager)

        subscription = manager._subscriptions_by_id[sub_id]
        assert subscription.is_active is False
        assert subscription.deactivated_until == clock.monotonic() + COOLDOWN_SECONDS
        assert any("deactivat" in r.getMessage().lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_dispatch_lookup_reactivates_after_cooldown(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        clock = FakeClock()
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=COOLDOWN_SECONDS),
            clock=clock,
        )
        sub_id = await _make_deactivated_subscription(manager)

        clock.advance(seconds=COOLDOWN_SECONDS + 1)
        with caplog.at_level("WARNING", logger="app.engine.core.subscription_manager"):
            subs = await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)

        assert [s.subscription_id for s in subs] == [sub_id]
        subscription = manager._subscriptions_by_id[sub_id]
        assert subscription.is_active is True
        assert subscription.retry_count == 0
        assert subscription.deactivated_until is None
        assert any("reactivat" in r.getMessage().lower() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_stays_deactivated_within_cooldown(self) -> None:
        clock = FakeClock()
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=COOLDOWN_SECONDS),
            clock=clock,
        )
        await _make_deactivated_subscription(manager)

        clock.advance(seconds=COOLDOWN_SECONDS - 1)
        subs = await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)

        assert subs == []

    @pytest.mark.asyncio
    async def test_manual_deactivation_without_cooldown_never_reactivates(self) -> None:
        clock = FakeClock()
        manager = SubscriptionManager(SubscriptionConfig(), clock=clock)
        sub_id = await manager.add_subscription(
            subscriber_id="features",
            handler=_handler,
            event_types=[EventType.CANDLE_UPDATE],
        )
        manager._subscriptions_by_id[sub_id].is_active = False

        clock.advance(seconds=COOLDOWN_SECONDS * 100)
        subs = await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)

        assert subs == []

    @pytest.mark.asyncio
    async def test_success_clears_cooldown_state(self) -> None:
        clock = FakeClock()
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=COOLDOWN_SECONDS),
            clock=clock,
        )
        sub_id = await _make_deactivated_subscription(manager)
        clock.advance(seconds=COOLDOWN_SECONDS + 1)
        await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)

        await manager.record_subscription_success(sub_id)

        subscription = manager._subscriptions_by_id[sub_id]
        assert subscription.retry_count == 0
        assert subscription.deactivated_until is None

    @pytest.mark.asyncio
    async def test_stale_success_does_not_clear_cooldown_on_inactive_sub(self) -> None:
        """A success racing a deactivation (multi-worker dispatch snapshot)
        must not erase the cooldown deadline — that would deactivate the
        subscription permanently, the exact defect this module fixes."""
        clock = FakeClock()
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=COOLDOWN_SECONDS),
            clock=clock,
        )
        sub_id = await _make_deactivated_subscription(manager)

        await manager.record_subscription_success(sub_id)

        subscription = manager._subscriptions_by_id[sub_id]
        assert subscription.is_active is False
        assert subscription.deactivated_until is not None

        clock.advance(seconds=COOLDOWN_SECONDS + 1)
        subs = await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)
        assert [s.subscription_id for s in subs] == [sub_id]

    @pytest.mark.asyncio
    async def test_cooldown_is_configurable(self) -> None:
        clock = FakeClock()
        short_cooldown = 5.0
        manager = SubscriptionManager(
            SubscriptionConfig(reactivation_cooldown_seconds=short_cooldown),
            clock=clock,
        )
        sub_id = await _make_deactivated_subscription(manager)

        clock.advance(seconds=short_cooldown + 1)
        subs = await manager.get_subscriptions_for_event(EventType.CANDLE_UPDATE)

        assert [s.subscription_id for s in subs] == [sub_id]
