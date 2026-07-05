"""
Unit tests for engine-supplied client order IDs and venue propagation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.engine.backtest.types import BacktestOrder, OrderSide, OrderStatus, OrderType
from app.engine.paper.broker import ClientOrderIDs, PaperBroker, PlaceBracketRequest

# Accessing broker internals is intentional in these unit tests.
# ruff: noqa: SLF001


@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool


def _bracket_request(client_order_ids: ClientOrderIDs | None = None) -> PlaceBracketRequest:
    return PlaceBracketRequest(
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("0.01"),
        entry_price=Decimal(50000),
        take_profit_prices=[Decimal(51000)],
        stop_loss_price=Decimal(49500),
        order_type="LIMIT",
        client_order_ids=client_order_ids,
    )


@pytest.mark.asyncio
async def test_place_bracket_honors_engine_supplied_client_ids(mock_pool: MagicMock) -> None:
    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = mock_pool
    supplied = ClientOrderIDs(
        main="engine-main-1",
        take_profits=["engine-tp-1"],
        stop_loss="engine-sl-1",
    )

    response = await broker.place_bracket_order(_bracket_request(supplied))

    assert (
        response.client_order_ids,
        sorted(broker.active_orders),
        broker._order_venues["engine-main-1"],
    ) == (supplied, ["engine-main-1", "engine-sl-1", "engine-tp-1"], "SPOT")


@pytest.mark.asyncio
async def test_place_bracket_mints_paper_ids_when_none_supplied(mock_pool: MagicMock) -> None:
    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = mock_pool

    response = await broker.place_bracket_order(_bracket_request())

    assert response.client_order_ids.main.startswith("paper_")
    assert broker._order_venues[response.client_order_ids.main] == "SPOT"


@pytest.mark.asyncio
async def test_place_bracket_rejects_mismatched_tp_id_count(mock_pool: MagicMock) -> None:
    from fastapi import HTTPException

    broker = PaperBroker(database_url="postgresql://test:test@localhost/test")
    broker.db_pool = mock_pool
    supplied = ClientOrderIDs(
        main="engine-main-1",
        take_profits=["engine-tp-1", "engine-tp-2"],
        stop_loss="engine-sl-1",
    )

    with pytest.raises(HTTPException) as exc_info:
        await broker.place_bracket_order(_bracket_request(supplied))

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_publish_order_update_swallows_publisher_exception() -> None:
    async def exploding_publisher(topic: str, payload: dict[str, object]) -> bool:
        raise RuntimeError("engine unreachable")

    broker = PaperBroker(
        database_url="postgresql://test:test@localhost/test",
        event_publisher=exploding_publisher,
    )
    order = BacktestOrder(
        id=uuid4(),
        client_order_id="engine-main-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("0.01"),
        order_time=datetime.now(UTC),
    )

    await broker._publish_order_update(order, "FILLED")


@pytest.mark.asyncio
async def test_publish_order_update_includes_tracked_venue() -> None:
    published: dict = {}

    async def capturing_publisher(topic: str, payload: dict[str, object]) -> bool:
        published["topic"] = topic
        published["payload"] = payload
        return True

    broker = PaperBroker(
        database_url="postgresql://test:test@localhost/test",
        event_publisher=capturing_publisher,
    )
    broker._order_venues["engine-main-1"] = "USD_M"
    order = BacktestOrder(
        id=uuid4(),
        client_order_id="engine-main-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("0.01"),
        order_time=datetime.now(UTC),
    )

    await broker._publish_order_update(order, "FILLED")

    assert (published["topic"], published["payload"]["venue"]) == (
        "order_update.v1",
        "USD_M",
    )
