import asyncio
import pytest

from app.engine.core.keyed_executor import KeyedExecutor


@pytest.mark.asyncio
async def test_keyed_executor_serializes_same_key_in_order() -> None:
    executor = KeyedExecutor()
    events: list[str] = []
    start = asyncio.Event()

    async def first() -> str:
        events.append("first-start")
        start.set()
        await asyncio.sleep(0.02)
        events.append("first-end")
        return "first"

    async def second() -> str:
        await start.wait()
        events.append("second")
        return "second"

    t1 = asyncio.create_task(executor.run("BTCUSDT:15m", first))
    t2 = asyncio.create_task(executor.run("BTCUSDT:15m", second))

    assert await t1 == "first"
    assert await t2 == "second"
    assert events == ["first-start", "first-end", "second"]


@pytest.mark.asyncio
async def test_keyed_executor_allows_parallel_different_keys() -> None:
    executor = KeyedExecutor()
    started = asyncio.Event()
    allow_finish = asyncio.Event()

    async def slow() -> str:
        started.set()
        await allow_finish.wait()
        return "slow"

    async def fast() -> str:
        await started.wait()
        return "fast"

    slow_task = asyncio.create_task(executor.run("BTCUSDT:15m", slow))
    fast_task = asyncio.create_task(executor.run("ETHUSDT:15m", fast))

    assert await fast_task == "fast"
    allow_finish.set()
    assert await slow_task == "slow"

