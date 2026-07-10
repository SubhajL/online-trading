"""
Unit tests for zero-TP brackets and bracket-scoped position close.

Phase 3a (trend paper): the trend co-primaries run with no take profit
(exit on flip/stop), and two strategies can hold positions on the same
symbol, so closing must be scoped to a single bracket and must cancel the
bracket's resting stop before the close order (no double exit fill).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest

from app.engine.backtest.types import BacktestOrder, OrderSide, OrderStatus, OrderType
from app.engine.models import Candle, TimeFrame
from app.engine.paper.broker import (
    ClientOrderIDs,
    PaperBroker,
    PaperPosition,
    PlaceBracketRequest,
)

# Accessing broker internals is intentional in these unit tests.
# ruff: noqa: SLF001

SYMBOL = "BTCUSDT"
ENTRY_PRICE = Decimal(50000)
STOP_PRICE = Decimal(49500)
QUANTITY = Decimal("0.01")


@pytest.fixture
def mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool, conn


def _make_broker(pool: MagicMock) -> PaperBroker:
    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = pool
    return broker


def _make_candle(*, open_price: Decimal, high: Decimal, low: Decimal) -> Candle:
    now = datetime.now(UTC)
    return Candle(
        venue="spot",
        symbol=SYMBOL,
        timeframe=TimeFrame.D1,
        open_time=now,
        close_time=now,
        open_price=open_price,
        high_price=high,
        low_price=low,
        close_price=open_price,
        volume=Decimal(100),
        quote_volume=Decimal(0),
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )


def _zero_tp_request(client_order_ids: ClientOrderIDs | None = None) -> PlaceBracketRequest:
    return PlaceBracketRequest(
        symbol=SYMBOL,
        side="BUY",
        quantity=QUANTITY,
        take_profit_prices=[],
        stop_loss_price=STOP_PRICE,
        order_type="MARKET",
        client_order_ids=client_order_ids,
    )


def _seed_long_bracket(
    broker: PaperBroker,
    bracket_id: UUID,
    stop_client_order_id: str,
) -> None:
    """Seed a filled long position with its resting stop, as after entry fill."""
    position = PaperPosition(SYMBOL)
    position.net_quantity = QUANTITY
    position.avg_entry_price = ENTRY_PRICE
    broker.positions[(SYMBOL, bracket_id)] = position

    stop_order = BacktestOrder(
        symbol=SYMBOL,
        side=OrderSide.SELL,
        type=OrderType.STOP_MARKET,
        quantity=QUANTITY,
        stop_price=STOP_PRICE,
        client_order_id=stop_client_order_id,
        status=OrderStatus.NEW,
        reduce_only=True,
    )
    broker.active_orders[stop_client_order_id] = stop_order
    broker._order_bracket_ids[stop_client_order_id] = bracket_id


@pytest.mark.asyncio
async def test_zero_tp_bracket_creates_entry_and_stop_only(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """Empty take_profit_prices places exactly two orders: entry + stop."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)

    response = await broker.place_bracket_order(_zero_tp_request())

    entry = broker.active_orders[response.client_order_ids.main]
    stop = broker.active_orders[response.client_order_ids.stop_loss]
    assert (
        response.client_order_ids.take_profits,
        len(broker.active_orders),
        (entry.type, entry.reduce_only),
        (stop.type, stop.stop_price, stop.reduce_only),
    ) == ([], 2, (OrderType.MARKET, False), (OrderType.STOP_MARKET, STOP_PRICE, True))


@pytest.mark.asyncio
async def test_zero_tp_bracket_honors_engine_supplied_ids(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """Engine-supplied IDs with an empty take_profits list are accepted."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    supplied = ClientOrderIDs(main="trend-main-1", take_profits=[], stop_loss="trend-sl-1")

    response = await broker.place_bracket_order(_zero_tp_request(supplied))

    assert (response.client_order_ids, sorted(broker.active_orders)) == (
        supplied,
        ["trend-main-1", "trend-sl-1"],
    )


@pytest.mark.asyncio
async def test_bracket_with_multiple_tp_prices_rejected(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """More than one TP is still rejected with HTTP 400."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    request = PlaceBracketRequest(
        symbol=SYMBOL,
        side="BUY",
        quantity=QUANTITY,
        take_profit_prices=[Decimal(51000), Decimal(52000)],
        stop_loss_price=STOP_PRICE,
        order_type="MARKET",
    )

    with pytest.raises(HTTPException) as exc_info:
        await broker.place_bracket_order(request)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_close_position_closes_only_matching_bracket(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """Two brackets on one symbol: closing one leaves the other's position and stop."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    bracket_a, bracket_b = uuid4(), uuid4()
    _seed_long_bracket(broker, bracket_a, "sleeve-a-sl")
    _seed_long_bracket(broker, bracket_b, "sleeve-b-sl")
    candle = _make_candle(
        open_price=Decimal(50200),
        high=Decimal(50300),
        low=Decimal(50100),
    )
    broker.latest_candles[SYMBOL] = candle
    broker.current_prices[SYMBOL] = candle.close_price

    result = await broker.close_position(SYMBOL, bracket_a, client_order_id="trend-close-a")

    assert (
        result["status"],
        broker.positions[(SYMBOL, bracket_a)].net_quantity,
        broker.positions[(SYMBOL, bracket_b)].net_quantity,
        "sleeve-a-sl" in broker.active_orders,
        "sleeve-b-sl" in broker.active_orders,
    ) == ("success", Decimal(0), QUANTITY, False, True)


@pytest.mark.asyncio
async def test_close_position_cancels_resting_stop_before_close(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """A candle that would trigger the stop must not double-exit the position."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    bracket_id = uuid4()
    _seed_long_bracket(broker, bracket_id, "trend-sl-1")
    candle = _make_candle(
        open_price=Decimal(49400),
        high=Decimal(49450),
        low=Decimal(49000),
    )
    broker.latest_candles[SYMBOL] = candle
    broker.current_prices[SYMBOL] = candle.close_price

    result = await broker.close_position(SYMBOL, bracket_id, client_order_id="trend-close-1")

    assert (
        result["status"],
        broker.positions[(SYMBOL, bracket_id)].net_quantity,
        broker.active_orders,
    ) == ("success", Decimal(0), {})


@pytest.mark.asyncio
async def test_close_position_without_position_cancels_resting_orders(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """Flattening a bracket with no position cancels its resting orders in DB and memory."""
    pool, conn = mock_pool
    broker = _make_broker(pool)
    bracket_id = uuid4()
    entry_order = BacktestOrder(
        symbol=SYMBOL,
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        quantity=QUANTITY,
        price=ENTRY_PRICE,
        client_order_id="trend-main-1",
        status=OrderStatus.NEW,
        reduce_only=False,
    )
    broker.active_orders["trend-main-1"] = entry_order
    broker._order_bracket_ids["trend-main-1"] = bracket_id
    _seed_long_bracket(broker, bracket_id, "trend-sl-1")
    broker.positions.pop((SYMBOL, bracket_id))

    result = await broker.close_position(SYMBOL, bracket_id)

    executed_sql = " ".join(call.args[0] for call in conn.execute.call_args_list)
    assert (
        result["status"],
        broker.active_orders,
        "UPDATE paper_orders" in executed_sql,
    ) == ("success", {}, True)


@pytest.mark.asyncio
async def test_close_position_closes_short_position_with_buy_order(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """A short bracket flattens to zero via a BUY market close."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    bracket_id = uuid4()
    position = PaperPosition(SYMBOL)
    position.net_quantity = -QUANTITY
    position.avg_entry_price = ENTRY_PRICE
    broker.positions[(SYMBOL, bracket_id)] = position
    candle = _make_candle(
        open_price=Decimal(50200),
        high=Decimal(50300),
        low=Decimal(50100),
    )
    broker.latest_candles[SYMBOL] = candle
    broker.current_prices[SYMBOL] = candle.close_price

    result = await broker.close_position(SYMBOL, bracket_id, client_order_id="trend-close-short")

    assert (
        result["status"],
        result["closed"],
        broker.positions[(SYMBOL, bracket_id)].net_quantity,
    ) == ("success", "true", Decimal(0))


@pytest.mark.asyncio
async def test_close_position_duplicate_client_id_places_single_close(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """Retrying a close with the same client_order_id does not duplicate the order."""
    pool, _conn = mock_pool
    broker = _make_broker(pool)
    bracket_id = uuid4()
    _seed_long_bracket(broker, bracket_id, "trend-sl-1")

    first = await broker.close_position(SYMBOL, bracket_id, client_order_id="trend-close-1")
    second = await broker.close_position(SYMBOL, bracket_id, client_order_id="trend-close-1")

    close_orders = [
        order for order in broker.active_orders.values() if order.client_order_id == "trend-close-1"
    ]
    assert (first["status"], second["status"], len(close_orders)) == (
        "success",
        "duplicate",
        1,
    )
