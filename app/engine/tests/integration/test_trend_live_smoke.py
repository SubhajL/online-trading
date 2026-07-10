"""
Phase 3a integration smoke: BTC/ETH daily trend co-primaries against a real DB.

One end-to-end story through TrendDecisionService + PaperBroker + recovery:
warmup places nothing -> a rising close puts all four sleeves LONG (zero-TP
brackets, audit rows) -> a restarted service recovers its sleeves and treats
a replayed candle as a no-op -> a trend flip closes each sleeve bracket-scoped
(candle ranges are wide, ATR=45, so the flip candle does NOT touch the resting
stops — the close_position path is what must fire).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from typing import TYPE_CHECKING

import asyncpg
import pytest

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
from app.engine.models import Candle, TimeFrame
from app.engine.paper.broker import PaperBroker
from app.engine.tests.integration.db_config import load_test_database_config
from app.engine.trend_live.config import (
    build_trend_risk_parameters,
    load_trend_live_config_from_env,
)
from app.engine.trend_live.decision_service import TrendDecisionService
from app.engine.trend_live.recovery import load_open_trend_sleeves
from app.engine.trend_live.wiring import make_paper_equity_provider

if TYPE_CHECKING:
    from app.engine.trend_live.config import TrendLiveConfig

SYMBOLS = ("BTCUSDT", "ETHUSDT")
BASE_OPEN_TIME = datetime(2026, 1, 1, tzinfo=UTC)
WARMUP_BARS = 65
SLEEVES = 4  # 2 strategies x 2 symbols
# Wide ranges: constant true range 45 -> Wilder ATR exactly 45, so the 2xATR
# stop sits 90 below the close and a flip candle can stay above it.
ENTRY_CLOSE = Decimal(100 + WARMUP_BARS)
FLIP_CLOSE = Decimal(120)


def _daily_candle(symbol: str, day_index: int, close: Decimal | None = None) -> Candle:
    close_price = close if close is not None else Decimal(100 + day_index)
    open_time = BASE_OPEN_TIME + timedelta(days=day_index)
    return Candle(
        venue="SPOT",
        symbol=symbol,
        timeframe=TimeFrame.D1,
        open_time=open_time,
        close_time=open_time + timedelta(days=1),
        open_price=close_price - 1,
        high_price=close_price + 20,
        low_price=close_price - 25,
        close_price=close_price,
        volume=Decimal(100),
        quote_volume=Decimal(0),
        trades=1,
        taker_buy_base_volume=Decimal(0),
        taker_buy_quote_volume=Decimal(0),
    )


async def _truncate_trend_tables() -> None:
    cfg = load_test_database_config()
    conn = await asyncpg.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.username,
        password=cfg.password,
        database=cfg.database,
    )
    try:
        await conn.execute("TRUNCATE TABLE paper_orders CASCADE")
        await conn.execute("TRUNCATE TABLE paper_positions CASCADE")
        await conn.execute("TRUNCATE TABLE paper_fills CASCADE")
        await conn.execute("DELETE FROM trading_decisions WHERE reasoning LIKE 'trend_live%'")
    finally:
        await conn.close()


async def _fetch_state() -> dict[str, object]:
    cfg = load_test_database_config()
    conn = await asyncpg.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.username,
        password=cfg.password,
        database=cfg.database,
    )
    try:
        orders = await conn.fetch(
            "SELECT status, reduce_only, client_order_id FROM paper_orders ORDER BY order_time",
        )
        open_positions = await conn.fetchval(
            "SELECT COUNT(*) FROM paper_positions WHERE quantity > 0",
        )
        decisions = await conn.fetch(
            "SELECT action FROM trading_decisions "
            "WHERE reasoning LIKE 'trend_live%' ORDER BY timestamp, action",
        )
    finally:
        await conn.close()
    return {
        "order_count": len(orders),
        "entry_statuses": sorted(
            r["status"] for r in orders if r["client_order_id"].endswith("-long")
        ),
        "stop_statuses": sorted(
            r["status"] for r in orders if r["client_order_id"].endswith("-long-sl")
        ),
        "close_statuses": sorted(
            r["status"] for r in orders if r["client_order_id"].endswith("-close")
        ),
        "open_positions": open_positions,
        "actions": sorted(r["action"] for r in decisions),
    }


def _make_service(
    config: TrendLiveConfig,
    broker: PaperBroker,
    db_adapter: TimescaleDBAdapter,
) -> TrendDecisionService:
    return TrendDecisionService(
        config=config,
        broker=broker,
        equity_provider=make_paper_equity_provider(db_adapter, config.starting_balance),
        risk=build_trend_risk_parameters(config),
        decision_recorder=db_adapter.insert_trading_decision,
    )


@pytest.mark.integration
class TestTrendLiveSmoke:
    @pytest.mark.asyncio
    async def test_btc_eth_full_cycle_with_restart_recovery(self) -> None:
        """Warmup -> 4 LONG sleeves -> idempotent restart -> flip closes all."""
        await _truncate_trend_tables()
        database_url = os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://trading_user:your_secure_password_here@localhost:5432/trading_platform_test",
        )
        cfg = load_test_database_config()
        config = load_trend_live_config_from_env({"TREND_LIVE_ENABLED": "1"})

        db_adapter = TimescaleDBAdapter(
            host=cfg.host,
            port=cfg.port,
            database=cfg.database,
            username=cfg.username,
            password=cfg.password,
        )
        await db_adapter.initialize()

        broker = PaperBroker(database_url=database_url)
        await broker.initialize()
        try:
            service = _make_service(config, broker, db_adapter)
            history = {
                symbol: [_daily_candle(symbol, i) for i in range(WARMUP_BARS)] for symbol in SYMBOLS
            }
            for symbol in SYMBOLS:
                service.warmup(symbol, history[symbol])
            after_warmup = await _fetch_state()

            # Live bar: rising close -> both co-primaries LONG on both symbols.
            entry_candles = {
                symbol: _daily_candle(symbol, WARMUP_BARS, close=ENTRY_CLOSE) for symbol in SYMBOLS
            }
            for symbol in SYMBOLS:
                await service.on_daily_candle(entry_candles[symbol])
            after_entry = await _fetch_state()
        finally:
            await broker.close()

        # Restart: fresh broker + service, recover sleeves, replay the same bar.
        broker2 = PaperBroker(database_url=database_url)
        await broker2.initialize()
        try:
            service2 = _make_service(config, broker2, db_adapter)
            for symbol in SYMBOLS:
                service2.warmup(symbol, [*history[symbol], entry_candles[symbol]])
            service2.restore_open_sleeves(await load_open_trend_sleeves(broker2.db_pool))
            for symbol in SYMBOLS:
                await service2.on_daily_candle(entry_candles[symbol])
            after_replay = await _fetch_state()

            # Flip: close 120 is below SMA-65 and the 28d trailing return, but
            # above every resting stop (~75) -> bracket-scoped closes fire.
            for symbol in SYMBOLS:
                await service2.on_daily_candle(
                    _daily_candle(symbol, WARMUP_BARS + 1, close=FLIP_CLOSE),
                )
            after_flip = await _fetch_state()
        finally:
            await broker2.close()
            await db_adapter.close()

        assert (
            after_warmup["order_count"],
            after_entry["order_count"],
            after_entry["entry_statuses"],
            after_entry["stop_statuses"],
            after_entry["open_positions"],
            after_entry["actions"],
            after_replay["order_count"],
            after_flip["order_count"],
            after_flip["stop_statuses"],
            after_flip["close_statuses"],
            after_flip["open_positions"],
            after_flip["actions"],
        ) == (
            0,
            SLEEVES * 2,
            ["FILLED"] * SLEEVES,
            ["NEW"] * SLEEVES,
            SLEEVES,
            ["BUY"] * SLEEVES,
            SLEEVES * 2,
            SLEEVES * 3,
            ["CANCELED"] * SLEEVES,
            ["FILLED"] * SLEEVES,
            0,
            [*(["BUY"] * SLEEVES), *(["CLOSE"] * SLEEVES)],
        )
