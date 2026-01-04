"""
Unit tests for PaperBroker fill simulation.

These tests exercise the candle-driven fill path (no DB required) by using a
mock asyncpg pool and real FillEngine/CostCalculator logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.engine.backtest.types import BacktestOrder, OrderSide, OrderStatus, OrderType
from app.engine.models import Candle, TimeFrame
from app.engine.paper.broker import PaperBroker

# Accessing broker internals is intentional in these fill-path unit tests.
# ruff: noqa: SLF001


@pytest.fixture
def mock_pool() -> tuple[MagicMock, AsyncMock]:
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool, conn


def _make_candle(
    *,
    symbol: str,
    open_price: Decimal,
    high: Decimal,
    low: Decimal,
) -> Candle:
    now = datetime.now(UTC)
    return Candle(
        symbol=symbol,
        timeframe=TimeFrame.M1,
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


@pytest.mark.asyncio
async def test_update_market_data_fills_market_order_and_persists_fill(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """
    Processes candle, fills a market order, inserts paper_fills row.
    """
    pool, conn = mock_pool
    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = pool

    order = BacktestOrder(
        id=uuid4(),
        client_order_id=f"paper_entry_{uuid4().hex[:8]}",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        status=OrderStatus.NEW,
        reduce_only=False,
    )
    broker.active_orders[order.client_order_id] = order
    broker._order_bracket_ids[order.client_order_id] = uuid4()

    candle = _make_candle(
        symbol="BTCUSDT",
        open_price=Decimal(50000),
        high=Decimal(50100),
        low=Decimal(49900),
    )

    # This should not raise and should persist a fill.
    await broker.update_market_data(candle)

    executed_sql = " ".join(call.args[0] for call in conn.execute.call_args_list)
    assert "INSERT INTO paper_fills" in executed_sql


@pytest.mark.asyncio
async def test_reduce_only_exit_does_not_fill_without_position(
    mock_pool: tuple[MagicMock, AsyncMock],
) -> None:
    """
    TP/SL remains NEW until a position exists.
    """
    pool, conn = mock_pool
    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = pool

    exit_order = BacktestOrder(
        id=uuid4(),
        client_order_id=f"paper_tp_{uuid4().hex[:8]}",
        symbol="BTCUSDT",
        side=OrderSide.SELL,
        type=OrderType.LIMIT,
        quantity=Decimal("0.01"),
        price=Decimal(50000),
        status=OrderStatus.NEW,
        reduce_only=True,
    )
    broker.active_orders[exit_order.client_order_id] = exit_order
    broker._order_bracket_ids[exit_order.client_order_id] = uuid4()

    candle = _make_candle(
        symbol="BTCUSDT",
        open_price=Decimal(50000),
        high=Decimal(50010),
        low=Decimal(49990),
    )

    await broker.update_market_data(candle)

    # No DB writes should occur because the exit is not eligible.
    assert conn.execute.call_count == 0
