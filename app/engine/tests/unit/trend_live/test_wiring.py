"""
Unit tests for trend_live wiring — the only place PR3 touches main.py behavior.

TREND_LIVE_ENABLED=0 (default) must construct NOTHING; flag on builds the
dedicated broker + service + poller trio without touching shared services.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from app.engine.trend_live import wiring as wiring_mod
from app.engine.trend_live.wiring import (
    database_dsn,
    initialize_trend_live_services,
    make_paper_equity_provider,
)

STARTING_BALANCE = Decimal(10_000)


class _StubBroker:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = dict(kwargs)
        self.initialized = False
        self.db_pool = object()

    async def initialize(self) -> None:
        self.initialized = True


class _StubRestClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _Components:
    total_fees = Decimal(10)
    realized_pnl = Decimal(200)
    unrealized_pnl = Decimal(-50)
    total_funding = Decimal(0)


class _StubDBAdapter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def get_paper_equity_components(self) -> _Components:
        if self.fail:
            raise ConnectionError("db down")
        return _Components()

    async def insert_trading_decision(self, decision: object) -> bool:
        return True

    async def insert_candle(self, candle: object) -> bool:
        return True


@pytest.mark.asyncio
async def test_flag_off_builds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default env: no broker, no poller, no service — zero new behavior."""
    _StubBroker.last_kwargs = None
    monkeypatch.setattr(wiring_mod, "PaperBroker", _StubBroker)

    services = await initialize_trend_live_services(
        environ={},
        database_url="postgresql://u:p@localhost:5432/test",
        db_adapter=_StubDBAdapter(),
    )

    assert (services, _StubBroker.last_kwargs) == ({}, None)


@pytest.mark.asyncio
async def test_flag_on_builds_broker_service_and_poller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag on: dedicated PaperBroker + decision service + D1 poller."""
    monkeypatch.setattr(wiring_mod, "PaperBroker", _StubBroker)
    monkeypatch.setattr(wiring_mod, "BinanceRestClient", _StubRestClient)

    services = await initialize_trend_live_services(
        environ={"TREND_LIVE_ENABLED": "1", "TREND_LIVE_SYMBOLS": "BTCUSDT"},
        database_url="postgresql://u:p@localhost:5432/test",
        db_adapter=_StubDBAdapter(),
    )

    broker = services["trend_paper_broker"]
    poller = services["trend_daily_poller"]
    assert (
        sorted(services),
        _StubBroker.last_kwargs,
        broker.initialized,  # type: ignore[attr-defined]
        poller.config.symbols,  # type: ignore[attr-defined]
    ) == (
        ["trend_daily_poller", "trend_decision_service", "trend_paper_broker"],
        {"database_url": "postgresql://u:p@localhost:5432/test"},
        True,
        ("BTCUSDT",),
    )


@pytest.mark.asyncio
async def test_equity_provider_computes_from_components() -> None:
    """equity = starting − fees + realized + unrealized − funding."""
    provider = make_paper_equity_provider(_StubDBAdapter(), STARTING_BALANCE)

    equity = await provider()

    assert equity == STARTING_BALANCE - Decimal(10) + Decimal(200) + Decimal(-50)


@pytest.mark.asyncio
async def test_equity_provider_fails_closed_on_db_error() -> None:
    """A DB failure yields None so the decision service skips the entry."""
    provider = make_paper_equity_provider(_StubDBAdapter(fail=True), STARTING_BALANCE)

    assert await provider() is None


def test_database_dsn_quotes_credentials() -> None:
    """Reserved characters in credentials survive the round trip."""
    cfg = type(
        "DatabaseCfg",
        (),
        {
            "host": "db.local",
            "port": 5433,
            "database": "trading_engine",
            "username": "user@corp",
            "password": "p@ss:word/1",  # noqa: S105
        },
    )()

    assert database_dsn(cfg) == (
        "postgresql://user%40corp:p%40ss%3Aword%2F1@db.local:5433/trading_engine"
    )
