"""
Unit tests for thread-safe circuit breaker.
Written first following TDD principles.
"""

import asyncio
import pytest
from datetime import timedelta

from app.engine.core.clock import FakeClock
from app.engine.resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerConfig,
)


class TestCircuitBreakerConfig:
    def test_default_values(self):
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout_seconds == 60
        assert config.half_open_max_requests == 3

    def test_custom_values(self):
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout_seconds=30,
            half_open_max_requests=5,
        )

        assert config.failure_threshold == 3
        assert config.success_threshold == 1
        assert config.timeout_seconds == 30
        assert config.half_open_max_requests == 5


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self):
        clock = FakeClock()
        breaker = CircuitBreaker(clock=clock)

        assert await breaker.get_state() == CircuitBreakerState.CLOSED
        assert await breaker.should_allow_request() is True

    @pytest.mark.asyncio
    async def test_concurrent_failures_open_circuit(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config=config, clock=clock)

        # Simulate concurrent failures
        tasks = []
        for _ in range(5):
            tasks.append(breaker.record_failure())

        await asyncio.gather(*tasks)

        # Circuit should be open after threshold
        assert await breaker.get_state() == CircuitBreakerState.OPEN
        assert await breaker.should_allow_request() is False

    @pytest.mark.asyncio
    async def test_state_transitions_are_atomic(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config=config, clock=clock)

        # Track all state changes
        states_seen = []

        async def record_state_changes():
            for _ in range(10):
                state = await breaker.get_state()
                states_seen.append(state)
                await asyncio.sleep(0)

        async def cause_failures():
            for _ in range(3):
                await breaker.record_failure()
                await asyncio.sleep(0)

        # Run concurrently
        await asyncio.gather(record_state_changes(), cause_failures())

        # Should transition directly from CLOSED to OPEN
        assert CircuitBreakerState.CLOSED in states_seen
        assert CircuitBreakerState.OPEN in states_seen

    @pytest.mark.asyncio
    async def test_timeout_resets_to_half_open(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=30)
        breaker = CircuitBreaker(config=config, clock=clock)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()
        assert await breaker.get_state() == CircuitBreakerState.OPEN

        # Advance time but not enough
        clock.advance(seconds=29)
        assert await breaker.get_state() == CircuitBreakerState.OPEN

        # Advance past timeout
        clock.advance(seconds=2)
        assert await breaker.get_state() == CircuitBreakerState.HALF_OPEN
        assert await breaker.should_allow_request() is True

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout_seconds=10
        )
        breaker = CircuitBreaker(config=config, clock=clock)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()

        # Move to half-open
        clock.advance(seconds=11)
        assert await breaker.get_state() == CircuitBreakerState.HALF_OPEN

        # Record successes
        await breaker.record_success()
        assert await breaker.get_state() == CircuitBreakerState.HALF_OPEN

        await breaker.record_success()
        assert await breaker.get_state() == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_opens(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(failure_threshold=2, timeout_seconds=10)
        breaker = CircuitBreaker(config=config, clock=clock)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()

        # Move to half-open
        clock.advance(seconds=11)
        assert await breaker.get_state() == CircuitBreakerState.HALF_OPEN

        # Single failure reopens
        await breaker.record_failure()
        assert await breaker.get_state() == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_limits_concurrent_requests(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(
            failure_threshold=2, timeout_seconds=10, half_open_max_requests=3
        )
        breaker = CircuitBreaker(config=config, clock=clock)

        # Open the circuit
        await breaker.record_failure()
        await breaker.record_failure()

        # Move to half-open
        clock.advance(seconds=11)

        # Should allow limited requests
        results = []
        for _ in range(5):
            allowed = await breaker.should_allow_request()
            results.append(allowed)

        # Only first 3 should be allowed
        assert results[:3] == [True, True, True]
        assert results[3:] == [False, False]

    @pytest.mark.asyncio
    async def test_get_stats_returns_metrics(self):
        clock = FakeClock()
        breaker = CircuitBreaker(clock=clock)

        await breaker.record_failure()
        await breaker.record_success()
        await breaker.record_failure()

        stats = await breaker.get_stats()

        assert stats.failure_count == 2
        assert stats.success_count == 1
        assert stats.consecutive_failures == 1
        assert stats.consecutive_successes == 0
        assert stats.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_reset_clears_counts(self):
        clock = FakeClock()
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config=config, clock=clock)

        # Record some failures
        await breaker.record_failure()
        await breaker.record_failure()

        # Reset
        await breaker.reset()

        # Should be back to initial state
        assert await breaker.get_state() == CircuitBreakerState.CLOSED
        stats = await breaker.get_stats()
        assert stats.failure_count == 0
        assert stats.success_count == 0

    @pytest.mark.asyncio
    async def test_concurrent_state_queries_consistent(self):
        clock = FakeClock()
        breaker = CircuitBreaker(clock=clock)

        # Query state concurrently many times
        tasks = []
        for _ in range(100):
            tasks.append(breaker.get_state())

        states = await asyncio.gather(*tasks)

        # All should return the same state
        assert all(s == CircuitBreakerState.CLOSED for s in states)
