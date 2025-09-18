"""
Thread-safe circuit breaker implementation with dependency injection.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from app.engine.core.clock import Clock, SystemClock


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60
    half_open_max_requests: int = 3


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    consecutive_failures: int
    consecutive_successes: int
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None


class CircuitBreaker:
    """
    Thread-safe circuit breaker with configurable thresholds.

    Uses async locks to ensure thread safety for all state mutations.
    """

    def __init__(
        self,
        config: Optional[CircuitBreakerConfig] = None,
        clock: Optional[Clock] = None
    ):
        """Initialize with optional config and clock."""
        self._config = config or CircuitBreakerConfig()
        self._clock = clock or SystemClock()

        # State management
        self._state = CircuitBreakerState.CLOSED
        self._lock = asyncio.Lock()

        # Counters
        self._failure_count = 0
        self._success_count = 0
        self._consecutive_failures = 0
        self._consecutive_successes = 0

        # Timing
        self._last_failure_time: Optional[datetime] = None
        self._last_success_time: Optional[datetime] = None
        self._last_state_change_time: Optional[datetime] = None

        # Half-open state tracking
        self._half_open_requests = 0

    async def should_allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns True if request can proceed, False if circuit is blocking.
        """
        async with self._lock:
            # Update state based on timeout if needed
            self._check_timeout()

            if self._state == CircuitBreakerState.CLOSED:
                return True

            if self._state == CircuitBreakerState.OPEN:
                # Check if we should transition to half-open
                self._check_timeout()
                return self._state == CircuitBreakerState.HALF_OPEN

            if self._state == CircuitBreakerState.HALF_OPEN:
                # Allow limited requests in half-open
                if self._half_open_requests < self._config.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False

            return False

    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            self._success_count += 1
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            self._last_success_time = self._clock.now()

            # Handle state transitions
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._consecutive_successes >= self._config.success_threshold:
                    self._transition_to_closed()

    async def record_failure(self) -> None:
        """Record a failed request."""
        async with self._lock:
            self._failure_count += 1
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            self._last_failure_time = self._clock.now()

            # Handle state transitions
            if self._state == CircuitBreakerState.CLOSED:
                if self._consecutive_failures >= self._config.failure_threshold:
                    self._transition_to_open()
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open returns to open
                self._transition_to_open()

    async def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        async with self._lock:
            self._check_timeout()
            return self._state

    async def get_stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        async with self._lock:
            return CircuitBreakerStats(
                state=self._state,
                failure_count=self._failure_count,
                success_count=self._success_count,
                consecutive_failures=self._consecutive_failures,
                consecutive_successes=self._consecutive_successes,
                last_failure_time=self._last_failure_time,
                last_success_time=self._last_success_time
            )

    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._last_failure_time = None
            self._last_success_time = None
            self._last_state_change_time = None
            self._half_open_requests = 0

    def _check_timeout(self) -> None:
        """
        Check if timeout has elapsed and transition to half-open if needed.

        Must be called within lock.
        """
        if self._state == CircuitBreakerState.OPEN:
            if self._last_state_change_time:
                elapsed = (self._clock.now() - self._last_state_change_time).total_seconds()
                if elapsed >= self._config.timeout_seconds:
                    self._transition_to_half_open()

    def _transition_to_closed(self) -> None:
        """
        Transition to closed state.

        Must be called within lock.
        """
        self._state = CircuitBreakerState.CLOSED
        self._last_state_change_time = self._clock.now()
        self._consecutive_failures = 0
        self._half_open_requests = 0

    def _transition_to_open(self) -> None:
        """
        Transition to open state.

        Must be called within lock.
        """
        self._state = CircuitBreakerState.OPEN
        self._last_state_change_time = self._clock.now()
        self._half_open_requests = 0

    def _transition_to_half_open(self) -> None:
        """
        Transition to half-open state.

        Must be called within lock.
        """
        self._state = CircuitBreakerState.HALF_OPEN
        self._last_state_change_time = self._clock.now()
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._half_open_requests = 0