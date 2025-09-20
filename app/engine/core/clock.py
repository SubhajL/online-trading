"""
Clock abstraction for testable time-dependent code.
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Awaitable, Callable, List, Optional, Tuple


class Clock(ABC):
    """Abstract clock interface for dependency injection."""

    @abstractmethod
    def now(self) -> datetime:
        """Get current datetime."""
        pass

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Async sleep for specified seconds."""
        pass

    @abstractmethod
    def monotonic(self) -> float:
        """Get monotonic time for duration measurements."""
        pass


class SystemClock(Clock):
    """Real system clock implementation."""

    def now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.utcnow()

    async def sleep(self, seconds: float) -> None:
        """Sleep using asyncio."""
        await asyncio.sleep(seconds)

    def monotonic(self) -> float:
        """Get monotonic time from event loop."""
        return asyncio.get_event_loop().time()


@dataclass
class ScheduledCallback:
    """A callback scheduled to run at a specific time."""

    when: datetime
    callback: Callable[[], None]


class FakeClock(Clock):
    """Fake clock for testing with controllable time."""

    def __init__(self, initial_time: Optional[datetime] = None):
        """Initialize with optional starting time."""
        self._current_time = initial_time or datetime.utcnow()
        self._monotonic_start = 0.0
        self._monotonic_current = 0.0
        self._scheduled: List[ScheduledCallback] = []
        self._sleepers: List[Tuple[datetime, asyncio.Future]] = []

    def now(self) -> datetime:
        """Get current fake time."""
        return self._current_time

    async def sleep(self, seconds: float) -> None:
        """Fake sleep that advances time without waiting."""
        wake_time = self._current_time + timedelta(seconds=seconds)
        future = asyncio.Future()
        self._sleepers.append((wake_time, future))

        # If we're already past the wake time, wake immediately
        if wake_time <= self._current_time:
            future.set_result(None)

        # Advance time to the wake time
        self.advance(seconds=seconds)

        # Wake up any sleepers that should wake
        self._wake_sleepers()

        await future

    def monotonic(self) -> float:
        """Get fake monotonic time."""
        return self._monotonic_current

    def advance(self, seconds: float) -> None:
        """Advance fake time by specified seconds."""
        self._current_time += timedelta(seconds=seconds)
        self._monotonic_current += seconds

        # Execute any scheduled callbacks
        self._execute_scheduled_callbacks()

        # Wake up any sleepers
        self._wake_sleepers()

    async def wait_until(self, target_time: datetime) -> None:
        """Advance time until target is reached."""
        if target_time > self._current_time:
            delta = (target_time - self._current_time).total_seconds()
            self.advance(seconds=delta)

    def schedule_at(self, when: datetime, callback: Callable[[], None]) -> None:
        """Schedule a callback to run at a specific time."""
        self._scheduled.append(ScheduledCallback(when=when, callback=callback))
        self._scheduled.sort(key=lambda x: x.when)

        # Execute immediately if already past the time
        self._execute_scheduled_callbacks()

    def _execute_scheduled_callbacks(self) -> None:
        """Execute any callbacks whose time has come."""
        while self._scheduled and self._scheduled[0].when <= self._current_time:
            scheduled = self._scheduled.pop(0)
            scheduled.callback()

    def _wake_sleepers(self) -> None:
        """Wake up any sleepers whose time has come."""
        still_sleeping = []

        for wake_time, future in self._sleepers:
            if wake_time <= self._current_time and not future.done():
                future.set_result(None)
            elif not future.done():
                still_sleeping.append((wake_time, future))

        self._sleepers = still_sleeping
