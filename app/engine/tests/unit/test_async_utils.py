import asyncio
import pytest

from app.engine.tests.utils.async import await_until, await_until_events


@pytest.mark.asyncio
async def test_await_until_succeeds_quickly():
    state = {"ready": False}

    async def flip():
        await asyncio.sleep(0.05)
        state["ready"] = True

    async def cond() -> bool:
        return state["ready"]

    task = asyncio.create_task(flip())
    await await_until(cond, timeout=1.0, poll_interval=0.01)
    await task


@pytest.mark.asyncio
async def test_await_until_events_reaches_minimum():
    buf: list[int] = []

    async def producer():
        for i in range(3):
            await asyncio.sleep(0.02)
            buf.append(i)

    def get_events() -> list[int]:
        return buf

    task = asyncio.create_task(producer())
    events = await await_until_events(get_events, min_count=3, timeout=1.0, poll_interval=0.01)
    await task

    assert events == [0, 1, 2]