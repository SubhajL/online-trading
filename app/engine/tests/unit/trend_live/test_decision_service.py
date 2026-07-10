"""
Unit tests for TrendDecisionService — the phase-3a desired-state diff loop.

Mirrors the simulator's `_apply_trend_target` semantics against live
PaperBroker state: warmup replays without orders, LONG targets place
zero-TP brackets, SHORT degrades to FLAT, sleeves are bracket-scoped per
(strategy × symbol), and sizing fails closed on missing equity or invalid
stops.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest

from app.engine.backtest.trend_signals import TrendTarget
from app.engine.models import Candle, RiskParameters, TimeFrame
from app.engine.paper.broker import (
    ClientOrderIDs,
    PaperPosition,
    PlaceBracketRequest,
    PlaceBracketResponse,
)
from app.engine.trend_live.config import (
    build_trend_risk_parameters,
    load_trend_live_config_from_env,
)
from app.engine.trend_live.decision_service import (
    OpenSleeve,
    TrendDecisionService,
    trend_client_order_id,
    trend_decision_id,
)

if TYPE_CHECKING:
    from app.engine.models import TradingDecision

# Accessing service internals (scripted engines) is intentional here.
# ruff: noqa: SLF001

SYMBOL = "BTCUSDT"
BASE_OPEN_TIME = datetime(2026, 1, 1, tzinfo=UTC)
EQUITY = Decimal(10_000)
# Rising closes with constant true range 3 → Wilder ATR is exactly 3,
# so a 2×ATR stop sits exactly 6 below the close.
ATR = Decimal(3)
WARMUP_BARS = 65


def _daily_candle(day_index: int, close: Decimal | None = None) -> Candle:
    close_price = close if close is not None else Decimal(100 + day_index)
    open_time = BASE_OPEN_TIME + timedelta(days=day_index)
    return Candle(
        venue="spot",
        symbol=SYMBOL,
        timeframe=TimeFrame.D1,
        open_time=open_time,
        close_time=open_time + timedelta(days=1),
        open_price=close_price - 1,
        high_price=close_price + 1,
        low_price=close_price - 2,
        close_price=close_price,
        volume=Decimal(100),
        quote_volume=Decimal(0),
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )


class FakeBroker:
    """In-memory stand-in for PaperBroker with instant entry fills."""

    def __init__(self) -> None:
        self.positions: dict[tuple[str, UUID], PaperPosition] = {}
        self.current_prices: dict[str, Decimal] = {}
        self.calls: list[tuple[str, object]] = []

    async def update_market_data(self, candle: Candle) -> None:
        self.calls.append(("update_market_data", candle.symbol))
        self.current_prices[candle.symbol] = candle.close_price

    async def place_bracket_order(self, request: PlaceBracketRequest) -> PlaceBracketResponse:
        self.calls.append(("place_bracket_order", request))
        bracket_id = uuid4()
        position = PaperPosition(request.symbol)
        position.net_quantity = request.quantity
        position.avg_entry_price = self.current_prices[request.symbol]
        self.positions[(request.symbol, bracket_id)] = position
        return PlaceBracketResponse(
            bracket_order_id=str(bracket_id),
            client_order_ids=request.client_order_ids
            or ClientOrderIDs(main="fake-main", take_profits=[], stop_loss="fake-sl"),
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            created_at=datetime.now(UTC),
        )

    async def close_position(
        self,
        symbol: str,
        bracket_id: UUID,
        client_order_id: str | None = None,
    ) -> dict[str, str]:
        self.calls.append(("close_position", (symbol, bracket_id, client_order_id)))
        position = self.positions.get((symbol, bracket_id))
        if position is not None:
            position.net_quantity = Decimal(0)
        return {"status": "success"}

    def placed_requests(self) -> list[PlaceBracketRequest]:
        return [
            cast("PlaceBracketRequest", call[1])
            for call in self.calls
            if call[0] == "place_bracket_order"
        ]

    def close_calls(self) -> list[tuple[str, UUID, str | None]]:
        return [
            cast("tuple[str, UUID, str | None]", call[1])
            for call in self.calls
            if call[0] == "close_position"
        ]


class ScriptedEngine:
    """Engine stub emitting pre-scripted targets, newest first."""

    def __init__(self, targets: list[TrendTarget]) -> None:
        self._targets = list(targets)

    def on_bar(self, candle: Candle) -> TrendTarget:
        return self._targets.pop(0)


def _make_service(
    broker: FakeBroker,
    *,
    equity: Decimal | None = EQUITY,
    symbols: str = SYMBOL,
    recorder_sink: list | None = None,
) -> TrendDecisionService:
    config = load_trend_live_config_from_env({"TREND_LIVE_SYMBOLS": symbols})

    async def equity_provider() -> Decimal | None:
        return equity

    async def recorder(decision: TradingDecision) -> bool:
        if recorder_sink is not None:
            recorder_sink.append(decision)
        return True

    return TrendDecisionService(
        config=config,
        broker=broker,
        equity_provider=equity_provider,
        risk=build_trend_risk_parameters(config),
        decision_recorder=recorder if recorder_sink is not None else None,
    )


def _warmup_candles() -> list[Candle]:
    return [_daily_candle(i) for i in range(WARMUP_BARS)]


def _seed_open_sleeve(
    broker: FakeBroker,
    service: TrendDecisionService,
    strategy_id: str,
    quantity: Decimal = Decimal(1),
) -> UUID:
    bracket_id = uuid4()
    position = PaperPosition(SYMBOL)
    position.net_quantity = quantity
    position.avg_entry_price = Decimal(150)
    broker.positions[(SYMBOL, bracket_id)] = position
    service.restore_open_sleeves(
        [OpenSleeve(strategy_id=strategy_id, symbol=SYMBOL, bracket_id=bracket_id, side="LONG")],
    )
    return bracket_id


def _script_engines(service: TrendDecisionService, targets: dict[str, list[TrendTarget]]) -> None:
    for (strategy_id, symbol), sleeve in service._sleeves.items():
        if symbol == SYMBOL and strategy_id in targets:
            sleeve.engine = ScriptedEngine(targets[strategy_id])  # type: ignore[assignment]


LONG_TARGET = TrendTarget(
    desired="LONG",
    entry=Decimal(165),
    stop_loss=Decimal(159),
    ready=True,
)
SHORT_TARGET = TrendTarget(
    desired="SHORT",
    entry=Decimal(165),
    stop_loss=Decimal(171),
    ready=True,
)
FLAT_TARGET = TrendTarget(desired="FLAT", ready=True)


@pytest.mark.asyncio
async def test_warmup_replays_history_without_orders() -> None:
    """Warmup feeds engines but never touches the broker."""
    broker = FakeBroker()
    service = _make_service(broker)

    service.warmup(SYMBOL, _warmup_candles())

    assert broker.calls == []


@pytest.mark.asyncio
async def test_long_targets_place_stop_only_brackets_for_both_strategies() -> None:
    """A rising tape puts both co-primaries LONG: two zero-TP brackets."""
    broker = FakeBroker()
    service = _make_service(broker)
    service.warmup(SYMBOL, _warmup_candles())
    live = _daily_candle(WARMUP_BARS)  # close=165, open_time=2026-03-07

    await service.on_daily_candle(live)

    requests = broker.placed_requests()
    expected_quantity = EQUITY * Decimal("0.25") / Decimal(165)
    assert [
        (
            r.side,
            r.quantity,
            r.take_profit_prices,
            r.stop_loss_price,
            r.order_type,
            r.client_order_ids.main if r.client_order_ids else None,
            r.client_order_ids.take_profits if r.client_order_ids else None,
        )
        for r in requests
    ] == [
        (
            "BUY",
            expected_quantity,
            [],
            Decimal(165) - 2 * ATR,
            "MARKET",
            f"trend-{strategy_id}-BTCUSDT-1d-20260307-long",
            [],
        )
        for strategy_id in ("tsmom28", "sma65")
    ]


@pytest.mark.asyncio
async def test_non_daily_candle_is_ignored() -> None:
    """The trend path only consumes closed D1 candles."""
    broker = FakeBroker()
    service = _make_service(broker)
    candle = _daily_candle(0).model_copy(update={"timeframe": TimeFrame.H4})

    await service.on_daily_candle(candle)

    assert broker.calls == []


@pytest.mark.asyncio
async def test_market_data_update_precedes_orders() -> None:
    """PaperBroker sees the candle (stop fills) before any diff-driven order."""
    broker = FakeBroker()
    service = _make_service(broker)
    _script_engines(service, {"tsmom28": [LONG_TARGET], "sma65": [FLAT_TARGET]})

    await service.on_daily_candle(_daily_candle(0, close=Decimal(165)))

    assert (broker.calls[0][0], broker.calls[1][0]) == (
        "update_market_data",
        "place_bracket_order",
    )


@pytest.mark.asyncio
async def test_short_target_degrades_to_flat_and_closes_long() -> None:
    """allow_short=False: SHORT desired state closes the long, opens nothing."""
    broker = FakeBroker()
    service = _make_service(broker)
    bracket_id = _seed_open_sleeve(broker, service, "tsmom28")
    _script_engines(service, {"tsmom28": [SHORT_TARGET], "sma65": [FLAT_TARGET]})
    candle = _daily_candle(0, close=Decimal(165))

    await service.on_daily_candle(candle)

    expected_close_id = trend_client_order_id("tsmom28", SYMBOL, candle.open_time, "close")
    assert (broker.close_calls(), broker.placed_requests()) == (
        [(SYMBOL, bracket_id, expected_close_id)],
        [],
    )


@pytest.mark.asyncio
async def test_two_strategies_keep_separate_bracket_state() -> None:
    """One strategy's flip closes only its own bracket, never the sibling's."""
    broker = FakeBroker()
    service = _make_service(broker)
    tsmom_bracket = _seed_open_sleeve(broker, service, "tsmom28")
    sma_bracket = _seed_open_sleeve(broker, service, "sma65")
    _script_engines(service, {"tsmom28": [FLAT_TARGET], "sma65": [LONG_TARGET]})

    await service.on_daily_candle(_daily_candle(0, close=Decimal(165)))

    assert (
        [call[1] for call in broker.close_calls()],
        broker.positions[(SYMBOL, sma_bracket)].net_quantity,
        broker.placed_requests(),
    ) == ([tsmom_bracket], Decimal(1), [])


@pytest.mark.asyncio
async def test_replayed_candle_is_skipped() -> None:
    """Processing the same open_time twice must not re-run engines or orders."""
    broker = FakeBroker()
    service = _make_service(broker)
    service.warmup(SYMBOL, _warmup_candles())
    live = _daily_candle(WARMUP_BARS)

    await service.on_daily_candle(live)
    first_pass_orders = len(broker.placed_requests())
    await service.on_daily_candle(live)

    assert (first_pass_orders, len(broker.placed_requests())) == (2, 2)


@pytest.mark.asyncio
async def test_restart_recovery_does_not_duplicate_client_order_ids() -> None:
    """After restart + state recovery, an unchanged desired state is a no-op."""
    broker = FakeBroker()
    service = _make_service(broker)
    service.warmup(SYMBOL, _warmup_candles())
    quantity = EQUITY * Decimal("0.25") / Decimal(165)
    for strategy_id in ("tsmom28", "sma65"):
        _seed_open_sleeve(broker, service, strategy_id, quantity=quantity)
    broker.calls.clear()

    await service.on_daily_candle(_daily_candle(WARMUP_BARS))

    open_time = BASE_OPEN_TIME + timedelta(days=WARMUP_BARS)
    assert (
        broker.placed_requests(),
        broker.close_calls(),
        trend_client_order_id("tsmom28", SYMBOL, open_time, "long"),
    ) == ([], [], "trend-tsmom28-BTCUSDT-1d-20260307-long")


@pytest.mark.asyncio
async def test_missing_equity_fails_closed_then_self_heals() -> None:
    """No equity → no entry; the diff retries and succeeds on the next bar."""
    broker = FakeBroker()
    equity_box: dict[str, Decimal | None] = {"value": None}

    config = load_trend_live_config_from_env({"TREND_LIVE_SYMBOLS": SYMBOL})

    async def equity_provider() -> Decimal | None:
        return equity_box["value"]

    service = TrendDecisionService(
        config=config,
        broker=broker,
        equity_provider=equity_provider,
        risk=build_trend_risk_parameters(config),
    )
    _script_engines(
        service,
        {"tsmom28": [LONG_TARGET, LONG_TARGET], "sma65": [FLAT_TARGET, FLAT_TARGET]},
    )

    await service.on_daily_candle(_daily_candle(0, close=Decimal(165)))
    orders_without_equity = len(broker.placed_requests())
    equity_box["value"] = EQUITY
    await service.on_daily_candle(_daily_candle(1, close=Decimal(165)))

    assert (orders_without_equity, len(broker.placed_requests())) == (0, 1)


@pytest.mark.asyncio
async def test_invalid_stop_distance_fails_closed() -> None:
    """A stop at the entry price is unsizeable: no order, no crash."""
    broker = FakeBroker()
    service = _make_service(broker)
    degenerate = TrendTarget(
        desired="LONG",
        entry=Decimal(165),
        stop_loss=Decimal(165),
        ready=True,
    )
    _script_engines(service, {"tsmom28": [degenerate], "sma65": [FLAT_TARGET]})

    await service.on_daily_candle(_daily_candle(0, close=Decimal(165)))

    assert broker.placed_requests() == []


@pytest.mark.asyncio
async def test_stop_fill_clears_sleeve_and_reenters() -> None:
    """A filled stop empties the position; the sleeve re-enters, not closes."""
    broker = FakeBroker()
    service = _make_service(broker)
    bracket_id = _seed_open_sleeve(broker, service, "tsmom28", quantity=Decimal(0))
    _script_engines(service, {"tsmom28": [LONG_TARGET], "sma65": [FLAT_TARGET]})

    await service.on_daily_candle(_daily_candle(0, close=Decimal(165)))

    assert (broker.close_calls(), len(broker.placed_requests())) == ([], 1)


@pytest.mark.asyncio
async def test_decisions_recorded_with_deterministic_ids() -> None:
    """Entry and close decisions are audited with uuid5 decision ids."""
    broker = FakeBroker()
    recorded: list[TradingDecision] = []
    service = _make_service(broker, recorder_sink=recorded)
    _seed_open_sleeve(broker, service, "sma65")
    _script_engines(service, {"tsmom28": [LONG_TARGET], "sma65": [FLAT_TARGET]})
    candle = _daily_candle(0, close=Decimal(165))

    await service.on_daily_candle(candle)

    entry_id = trend_client_order_id("tsmom28", SYMBOL, candle.open_time, "long")
    close_id = trend_client_order_id("sma65", SYMBOL, candle.open_time, "close")
    assert [(d.action, d.decision_id, d.symbol) for d in recorded] == [
        ("BUY", trend_decision_id(entry_id), SYMBOL),
        ("CLOSE", trend_decision_id(close_id), SYMBOL),
    ]
