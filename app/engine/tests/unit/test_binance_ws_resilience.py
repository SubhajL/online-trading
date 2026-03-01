"""
Unit tests for BinanceWebSocketClient resilience features.
TDD: Written first, implementation follows.

Tests exponential backoff, circuit breaker integration, and max retry limits.
"""
# ruff: noqa: PLR2004, SLF001, EM101, TRY003, ARG001, ARG002

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.core.clock import FakeClock
from app.engine.ingest.binance_ws import BinanceWebSocketClient
from app.engine.resilience.backoff import BackoffConfig
from app.engine.resilience.thread_safe_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
)


class TestWebSocketResilience:
    """Tests for WebSocket connection resilience."""

    @pytest.fixture
    def mock_event_bus(self) -> MagicMock:
        bus = MagicMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def clock(self) -> FakeClock:
        return FakeClock()

    @pytest.fixture
    def circuit_breaker(self, clock: FakeClock) -> CircuitBreaker:
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=1,
            timeout_seconds=60,
        )
        return CircuitBreaker(config=config, clock=clock)

    @pytest.fixture
    def backoff_config(self) -> BackoffConfig:
        return BackoffConfig(
            base_delay_s=1.0,
            max_delay_s=10.0,
            multiplier=2.0,
            jitter_pct=0.0,
        )

    @pytest.mark.asyncio
    async def test_client_accepts_circuit_breaker(
        self, circuit_breaker: CircuitBreaker, mock_event_bus: MagicMock,
    ) -> None:
        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            event_bus=mock_event_bus,
        )

        assert client._circuit_breaker is circuit_breaker

    @pytest.mark.asyncio
    async def test_client_accepts_max_reconnect_attempts(
        self, mock_event_bus: MagicMock,
    ) -> None:
        client = BinanceWebSocketClient(
            max_reconnect_attempts=25,
            event_bus=mock_event_bus,
        )

        assert client._max_reconnect_attempts == 25

    @pytest.mark.asyncio
    async def test_client_accepts_backoff_config(
        self, backoff_config: BackoffConfig, mock_event_bus: MagicMock,
    ) -> None:
        client = BinanceWebSocketClient(
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )

        assert client._backoff._config.base_delay_s == 1.0
        assert client._backoff._config.max_delay_s == 10.0

    @pytest.mark.asyncio
    async def test_default_max_reconnect_attempts_is_50(
        self, mock_event_bus: MagicMock,
    ) -> None:
        client = BinanceWebSocketClient(event_bus=mock_event_bus)

        assert client._max_reconnect_attempts == 50

    @pytest.mark.asyncio
    async def test_reconnect_delay_increases_exponentially(
        self, backoff_config: BackoffConfig, mock_event_bus: MagicMock,
    ) -> None:
        """Verify sleep durations grow on consecutive failures."""
        client = BinanceWebSocketClient(
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )
        sleep_calls: list[float] = []

        async def mock_connect_and_listen() -> None:
            raise ConnectionError("Test failure")

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)
            if len(sleep_calls) >= 4:
                client._running = False

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", mock_sleep),
        ):
            client._running = True
            await client._connection_manager()

        # Expect exponential delays: 1, 2, 4, 8
        assert sleep_calls == [1.0, 2.0, 4.0, 8.0]

    @pytest.mark.asyncio
    async def test_stops_after_max_consecutive_failures(
        self, backoff_config: BackoffConfig, mock_event_bus: MagicMock,
    ) -> None:
        """Verify loop exits after N consecutive failures."""
        client = BinanceWebSocketClient(
            max_reconnect_attempts=3,
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )
        attempt_count = 0

        async def mock_connect_and_listen() -> None:
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionError("Test failure")

        async def mock_sleep(delay: float) -> None:
            pass

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", mock_sleep),
        ):
            client._running = True
            await client._connection_manager()

        assert attempt_count == 3
        assert client._running is False

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_failure_count(
        self, backoff_config: BackoffConfig, mock_event_bus: MagicMock,
    ) -> None:
        """Verify failure count resets after successful connection."""
        client = BinanceWebSocketClient(
            max_reconnect_attempts=10,
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )
        call_count = 0
        sleep_calls: list[float] = []

        async def mock_connect_and_listen() -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ConnectionError("Test failure")
            if call_count == 3:
                # Simulate successful connection that runs for a bit
                await client._on_connection_success()
                return
            if call_count == 4:
                # Then fail again - should restart from base delay
                raise ConnectionError("Test failure after success")
            client._running = False

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", mock_sleep),
        ):
            client._running = True
            await client._connection_manager()

        # First two failures: 1, 2
        # After success, next failure should reset to base: 1
        assert sleep_calls[:2] == [1.0, 2.0]
        # After success (no sleep), the 4th call fails and sleeps at base again
        assert sleep_calls[2] == 1.0

    @pytest.mark.asyncio
    async def test_circuit_open_skips_connect_attempt(
        self,
        circuit_breaker: CircuitBreaker,
        clock: FakeClock,
        backoff_config: BackoffConfig,
        mock_event_bus: MagicMock,
    ) -> None:
        """Verify no connect attempt when circuit is OPEN."""
        # Open the circuit
        for _ in range(3):
            await circuit_breaker.record_failure()

        assert await circuit_breaker.get_state() == CircuitBreakerState.OPEN

        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            backoff_config=backoff_config,
            max_reconnect_attempts=5,
            event_bus=mock_event_bus,
        )
        connect_attempts = 0
        sleep_count = 0

        async def mock_connect_and_listen() -> None:
            nonlocal connect_attempts
            connect_attempts += 1
            raise ConnectionError("Should not reach here while OPEN")

        async def mock_sleep(delay: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 3:
                client._running = False

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", mock_sleep),
        ):
            client._running = True
            await client._connection_manager()

        # Should not have attempted any connections while circuit is OPEN
        assert connect_attempts == 0

    @pytest.mark.asyncio
    async def test_circuit_half_open_allows_one_probe(
        self,
        circuit_breaker: CircuitBreaker,
        clock: FakeClock,
        backoff_config: BackoffConfig,
        mock_event_bus: MagicMock,
    ) -> None:
        """Verify connect is attempted in HALF_OPEN state."""
        # Open the circuit
        for _ in range(3):
            await circuit_breaker.record_failure()

        # Move to half-open
        clock.advance(seconds=61)
        assert await circuit_breaker.get_state() == CircuitBreakerState.HALF_OPEN

        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            backoff_config=backoff_config,
            max_reconnect_attempts=5,
            event_bus=mock_event_bus,
        )
        connect_attempts = 0

        async def mock_connect_and_listen() -> None:
            nonlocal connect_attempts
            connect_attempts += 1
            client._running = False  # Stop after one attempt

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", AsyncMock()),
        ):
            client._running = True
            await client._connection_manager()

        # Should have attempted one connection in HALF_OPEN
        assert connect_attempts == 1

    @pytest.mark.asyncio
    async def test_failure_records_to_circuit_breaker(
        self,
        circuit_breaker: CircuitBreaker,
        backoff_config: BackoffConfig,
        mock_event_bus: MagicMock,
    ) -> None:
        """Verify record_failure() is called on connection error."""
        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            backoff_config=backoff_config,
            max_reconnect_attempts=2,
            event_bus=mock_event_bus,
        )

        async def mock_connect_and_listen() -> None:
            raise ConnectionError("Test failure")

        with (
            patch.object(client, "_connect_and_listen", mock_connect_and_listen),
            patch("asyncio.sleep", AsyncMock()),
        ):
            client._running = True
            await client._connection_manager()

        stats = await circuit_breaker.get_stats()
        assert stats.failure_count == 2

    @pytest.mark.asyncio
    async def test_success_records_to_circuit_breaker(
        self,
        circuit_breaker: CircuitBreaker,
        clock: FakeClock,
        backoff_config: BackoffConfig,
        mock_event_bus: MagicMock,
    ) -> None:
        """Verify record_success() is called on successful connection."""
        # First open the circuit
        for _ in range(3):
            await circuit_breaker.record_failure()

        # Advance time to move to HALF_OPEN state
        clock.advance(seconds=61)

        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )
        call_count = 0

        async def mock_connect_and_listen() -> None:
            nonlocal call_count
            call_count += 1
            # First call simulates successful connection
            await client._on_connection_success()
            client._running = False

        with (
            patch.object(
                client, "_connect_and_listen", side_effect=mock_connect_and_listen,
            ),
            patch("asyncio.sleep", AsyncMock()),
        ):
            client._running = True
            await client._connection_manager()

        stats = await circuit_breaker.get_stats()
        assert stats.success_count >= 1

    @pytest.mark.asyncio
    async def test_health_check_includes_resilience_info(
        self,
        circuit_breaker: CircuitBreaker,
        backoff_config: BackoffConfig,
        mock_event_bus: MagicMock,
    ) -> None:
        """Verify health endpoint shows attempt count and circuit state."""
        client = BinanceWebSocketClient(
            circuit_breaker=circuit_breaker,
            backoff_config=backoff_config,
            event_bus=mock_event_bus,
        )

        # Simulate some failures
        client._consecutive_failures = 3
        client._backoff.next_delay()
        client._backoff.next_delay()

        health = await client.health_check()

        assert "consecutive_failures" in health
        assert health["consecutive_failures"] == 3
        assert "circuit_state" in health
        assert health["circuit_state"] == "CLOSED"
        assert "backoff_attempt" in health
        assert health["backoff_attempt"] == 2
