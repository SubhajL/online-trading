"""
Minimal in-process event bus that records published events for draining.

Installed as the process-global bus (via set_event_bus) before constructing
SMCEngine so backtests capture BOS/CHOCH and zone events synchronously.
Swapping the global bus is process-wide state: run simulations sequentially.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.models import BaseEvent


class CapturingEventBus:
    def __init__(self) -> None:
        self._events: list[BaseEvent] = []

    async def publish(self, event: BaseEvent, priority: int = 0) -> bool:
        self._events.append(event)
        return True

    def drain(self) -> list[BaseEvent]:
        events = self._events
        self._events = []
        return events

    async def subscribe(self, *args: Any, **kwargs: Any) -> str:
        return ""

    async def unsubscribe(self, subscription_id: str) -> bool:
        return True
