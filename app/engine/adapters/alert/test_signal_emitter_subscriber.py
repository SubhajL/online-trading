"""Tests for SignalEmitterSubscriber - bridges SMC signals to SignalEmitter."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.engine.adapters.alert.signal_emitter_subscriber import (
    SignalEmitterSubscriber,
)
from app.engine.models import (
    EventType,
    OrderSide,
    SMCSignal,
    SMCSignalEvent,
    TimeFrame,
)

# Test constants
ENTRY_PRICE = 50000.0
STOP_LOSS_PRICE = 49000.0
TAKE_PROFIT_PRICE = 52000.0
CONFIDENCE_VALUE = 0.85


def make_smc_signal(  # noqa: PLR0913
    symbol: str = "BTCUSDT",
    entry: float = ENTRY_PRICE,
    stop_loss: float | None = STOP_LOSS_PRICE,
    take_profit: float | None = TAKE_PROFIT_PRICE,
    confidence: float = CONFIDENCE_VALUE,
    direction: OrderSide = OrderSide.BUY,
    reasoning: str = "SMC Breaker; Bullish OB Retest",
    timeframe: TimeFrame = TimeFrame.M15,
) -> SMCSignal:
    """Create a test SMC signal."""
    return SMCSignal(
        signal_id=uuid4(),
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime.now(UTC),
        signal_type="order_block_entry",
        direction=direction,
        entry_price=Decimal(str(entry)),
        stop_loss=Decimal(str(stop_loss)) if stop_loss is not None else None,
        take_profit=Decimal(str(take_profit)) if take_profit is not None else None,
        confidence=Decimal(str(confidence)),
        reasoning=reasoning,
    )


def make_smc_event(
    signal: SMCSignal | None = None,
    symbol: str = "BTCUSDT",
) -> SMCSignalEvent:
    """Create a test SMC signal event."""
    if signal is None:
        signal = make_smc_signal(symbol=symbol)
    return SMCSignalEvent(
        event_type=EventType.SMC_SIGNAL,
        timestamp=datetime.now(UTC),
        symbol=symbol,
        timeframe=TimeFrame.M15,
        signal=signal,
    )


class MockEventBus:
    """Mock event bus for testing."""

    def __init__(self) -> None:
        self.subscriptions: dict[str, tuple[Any, list[EventType]]] = {}
        self._next_id = 0

    async def subscribe(
        self,
        name: str,  # noqa: ARG002
        handler: Any,  # noqa: ANN401
        event_types: list[EventType] | None = None,
        priority: int = 0,  # noqa: ARG002
    ) -> str:
        """Record subscription."""
        sub_id = f"sub-{self._next_id}"
        self._next_id += 1
        self.subscriptions[sub_id] = (handler, event_types or [])
        return sub_id

    async def unsubscribe(self, sub_id: str) -> bool:
        """Remove subscription."""
        if sub_id in self.subscriptions:
            del self.subscriptions[sub_id]
            return True
        return False

    def get_handler(self) -> Callable[..., Any]:
        """Get the first registered handler."""
        return next(iter(self.subscriptions.values()))[0]


class TestSignalEmitterSubscriberInit:
    """Tests for SignalEmitterSubscriber initialization."""

    def test_init_stores_bus(self) -> None:
        """SignalEmitterSubscriber stores event bus reference."""
        bus = MockEventBus()
        emitter = MagicMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)
        assert subscriber._bus is bus  # noqa: SLF001

    def test_init_stores_signal_emitter(self) -> None:
        """SignalEmitterSubscriber stores signal emitter reference."""
        bus = MockEventBus()
        emitter = MagicMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)
        assert subscriber._signal_emitter is emitter  # noqa: SLF001


class TestSignalEmitterSubscriberLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_subscribes_to_smc_signal(self) -> None:
        """start() subscribes to SMC_SIGNAL event type."""
        bus = MockEventBus()
        emitter = MagicMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()

        assert len(bus.subscriptions) == 1
        _, event_types = next(iter(bus.subscriptions.values()))
        assert EventType.SMC_SIGNAL in event_types

    @pytest.mark.asyncio
    async def test_stop_unsubscribes(self) -> None:
        """stop() removes the subscription."""
        bus = MockEventBus()
        emitter = MagicMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        assert len(bus.subscriptions) == 1

        await subscriber.stop()
        assert len(bus.subscriptions) == 0

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        """stop() is safe to call without start()."""
        bus = MockEventBus()
        emitter = MagicMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)
        await subscriber.stop()  # Should not raise


class TestSignalEmitterSubscriberHandling:
    """Tests for SMC signal handling."""

    @pytest.mark.asyncio
    async def test_emits_decision_from_smc_signal_with_sl_tp(self) -> None:
        """SMC signal with SL/TP triggers emit_signal."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock(return_value="sig_123abc")
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(
            symbol="BTCUSDT",
            entry=ENTRY_PRICE,
            stop_loss=STOP_LOSS_PRICE,
            take_profit=TAKE_PROFIT_PRICE,
            confidence=CONFIDENCE_VALUE,
            direction=OrderSide.BUY,
        )
        event = make_smc_event(signal, symbol="BTCUSDT")

        await handler(event)

        emitter.emit_signal.assert_called_once()
        call_kwargs = emitter.emit_signal.call_args.kwargs
        assert call_kwargs["symbol"] == "BTCUSDT"
        assert call_kwargs["entry"] == ENTRY_PRICE
        assert call_kwargs["stop_loss"] == STOP_LOSS_PRICE
        assert call_kwargs["take_profit"] == TAKE_PROFIT_PRICE
        assert call_kwargs["confidence"] == CONFIDENCE_VALUE
        assert call_kwargs["side"] == "long"

    @pytest.mark.asyncio
    async def test_maps_sell_direction_to_short_side(self) -> None:
        """SELL direction is mapped to 'short' side."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock(return_value="sig_456def")
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(direction=OrderSide.SELL)
        event = make_smc_event(signal)

        await handler(event)

        call_kwargs = emitter.emit_signal.call_args.kwargs
        assert call_kwargs["side"] == "short"

    @pytest.mark.asyncio
    async def test_skips_smc_signal_missing_stop_loss(self) -> None:
        """No emit when stop_loss is missing."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(stop_loss=None)
        event = make_smc_event(signal)

        await handler(event)

        emitter.emit_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_smc_signal_missing_take_profit(self) -> None:
        """No emit when take_profit is missing."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock()
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(take_profit=None)
        event = make_smc_event(signal)

        await handler(event)

        emitter.emit_signal.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_reasoning_as_reasons_list(self) -> None:
        """reasoning is split into reasons list."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock(return_value="sig_789ghi")
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(reasoning="Reason A; Reason B; Reason C")
        event = make_smc_event(signal)

        await handler(event)

        call_kwargs = emitter.emit_signal.call_args.kwargs
        assert call_kwargs["reasons"] == ["Reason A", "Reason B", "Reason C"]

    @pytest.mark.asyncio
    async def test_passes_timeframe_from_signal(self) -> None:
        """Timeframe is extracted from signal."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock(return_value="sig_abc")
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal(timeframe=TimeFrame.H1)
        event = make_smc_event(signal)

        await handler(event)

        call_kwargs = emitter.emit_signal.call_args.kwargs
        assert call_kwargs["timeframe"] == "1h"

    @pytest.mark.asyncio
    async def test_handles_emitter_exception_gracefully(self) -> None:
        """Exception from emitter is caught and logged."""
        bus = MockEventBus()
        emitter = MagicMock()
        emitter.emit_signal = AsyncMock(side_effect=ValueError("test error"))
        subscriber = SignalEmitterSubscriber(bus=bus, signal_emitter=emitter)

        await subscriber.start()
        handler = bus.get_handler()

        signal = make_smc_signal()
        event = make_smc_event(signal)

        # Should not raise
        await handler(event)

        emitter.emit_signal.assert_called_once()
