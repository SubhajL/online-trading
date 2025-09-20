"""
Unit tests for Clock interface and implementations.
Following TDD - these tests are written before implementation.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock


class TestSystemClock:
    """Test real system clock implementation."""

    @pytest.mark.asyncio
    async def test_now_returns_current_datetime(self):
        from app.engine.core.clock import SystemClock

        clock = SystemClock()
        before = datetime.utcnow()
        result = clock.now()
        after = datetime.utcnow()

        assert before <= result <= after
        assert isinstance(result, datetime)

    @pytest.mark.asyncio
    async def test_sleep_delays_execution(self):
        from app.engine.core.clock import SystemClock

        clock = SystemClock()
        start = datetime.utcnow()
        await clock.sleep(0.05)  # 50ms
        end = datetime.utcnow()

        elapsed = (end - start).total_seconds()
        assert 0.04 < elapsed < 0.1  # Allow some variance

    def test_monotonic_increases(self):
        from app.engine.core.clock import SystemClock

        clock = SystemClock()
        t1 = clock.monotonic()
        t2 = clock.monotonic()

        assert t2 >= t1
        assert isinstance(t1, float)
        assert isinstance(t2, float)


class TestFakeClock:
    """Test fake clock for controlled time in tests."""

    def test_now_returns_fixed_time(self):
        from app.engine.core.clock import FakeClock

        fixed_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=fixed_time)

        assert clock.now() == fixed_time
        assert clock.now() == fixed_time  # Doesn't advance automatically

    def test_advance_moves_time_forward(self):
        from app.engine.core.clock import FakeClock

        start_time = datetime(2024, 1, 1, 12, 0, 0)
        clock = FakeClock(initial_time=start_time)

        clock.advance(seconds=60)

        expected = datetime(2024, 1, 1, 12, 1, 0)
        assert clock.now() == expected

    @pytest.mark.asyncio
    async def test_sleep_advances_time_without_waiting(self):
        from app.engine.core.clock import FakeClock

        clock = FakeClock()
        start_real_time = datetime.utcnow()
        start_fake_time = clock.now()

        await clock.sleep(60)  # Should not actually wait

        real_elapsed = (datetime.utcnow() - start_real_time).total_seconds()
        fake_elapsed = (clock.now() - start_fake_time).total_seconds()

        assert real_elapsed < 0.1  # Should be instant
        assert fake_elapsed == 60  # Fake time advanced

    def test_monotonic_advances_with_time(self):
        from app.engine.core.clock import FakeClock

        clock = FakeClock()
        t1 = clock.monotonic()
        clock.advance(seconds=5)
        t2 = clock.monotonic()

        assert t2 == t1 + 5

    @pytest.mark.asyncio
    async def test_wait_until_advances_to_target_time(self):
        from app.engine.core.clock import FakeClock

        clock = FakeClock()
        target = clock.now() + timedelta(hours=1)

        await clock.wait_until(target)

        assert clock.now() >= target

    def test_scheduled_callbacks_execute_at_right_time(self):
        from app.engine.core.clock import FakeClock

        clock = FakeClock()
        callback = MagicMock()

        clock.schedule_at(clock.now() + timedelta(seconds=30), callback)

        callback.assert_not_called()

        clock.advance(seconds=29)
        callback.assert_not_called()

        clock.advance(seconds=1)
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_sleeps_wake_in_order(self):
        from app.engine.core.clock import FakeClock

        clock = FakeClock()
        results = []

        async def sleeper(duration, name):
            await clock.sleep(duration)
            results.append(name)

        # Start multiple sleepers
        task1 = asyncio.create_task(sleeper(10, "short"))
        task2 = asyncio.create_task(sleeper(20, "medium"))
        task3 = asyncio.create_task(sleeper(30, "long"))

        # Advance time to wake them up in order
        clock.advance(seconds=35)
        await asyncio.gather(task1, task2, task3)

        assert results == ["short", "medium", "long"]
