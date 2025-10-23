import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


async def await_until(
    condition: Callable[[], Awaitable[bool] | bool],
    timeout: float = 2.0,
    poll_interval: float = 0.05,
) -> None:
    """Poll condition until True or timeout.

    - condition may be sync or async and should return a bool.
    - raises TimeoutError if not satisfied within timeout.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        result = condition()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError("Condition not met within timeout")
        await asyncio.sleep(poll_interval)


async def await_until_events(
    get_events: Callable[[], list[Any]],
    min_count: int,
    timeout: float = 2.0,
    poll_interval: float = 0.05,
) -> list[Any]:
    """Wait until get_events() returns at least min_count items.

    Returns the events list when the condition is satisfied.
    """
    events: list[Any] = []
    async def _cond() -> bool:
        nonlocal events
        events = get_events() or []
        return len(events) >= min_count

    await await_until(_cond, timeout=timeout, poll_interval=poll_interval)
    return events
