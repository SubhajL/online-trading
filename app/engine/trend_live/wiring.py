"""
Flag-gated construction of the phase-3a trend services.

main.py calls initialize_trend_live_services unconditionally; with
TREND_LIVE_ENABLED unset (the default) it returns an empty dict — zero new
services, tasks, or DB connections. Flag on builds the dedicated trio
(PaperBroker, TrendDecisionService, TrendDailyCandlePoller) without touching
any shared pipeline service.
"""

from __future__ import annotations

from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Protocol
import urllib.parse

from app.engine.ingest.binance_rest import BinanceRestClient
from app.engine.paper.broker import PaperBroker
from app.engine.paper.equity_sampler_service import calculate_current_equity

from .config import build_trend_risk_parameters, load_trend_live_config_from_env
from .daily_poller import TrendDailyCandlePoller, TrendDailyPollerConfig
from .decision_service import TrendDecisionService
from .recovery import load_open_trend_sleeves

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from app.engine.models import Candle, TradingDecision

logger = logging.getLogger(__name__)


class _EquityComponents(Protocol):
    @property
    def total_fees(self) -> Decimal: ...

    @property
    def realized_pnl(self) -> Decimal: ...

    @property
    def unrealized_pnl(self) -> Decimal: ...

    @property
    def total_funding(self) -> Decimal: ...


class TrendLiveDBAdapter(Protocol):
    """The TimescaleDBAdapter surface trend_live needs (structural)."""

    async def get_paper_equity_components(self) -> _EquityComponents: ...

    async def insert_trading_decision(self, decision: TradingDecision) -> bool: ...

    async def insert_candle(self, candle: Candle) -> bool: ...


class _DatabaseConfigLike(Protocol):
    host: str
    port: int
    database: str
    username: str
    password: str


def database_dsn(database: _DatabaseConfigLike) -> str:
    """Postgres DSN with URL-quoted credentials (PaperBroker needs a URL)."""
    username = urllib.parse.quote(database.username, safe="")
    password = urllib.parse.quote(database.password, safe="")
    return f"postgresql://{username}:{password}@{database.host}:{database.port}/{database.database}"


def make_paper_equity_provider(
    db_adapter: TrendLiveDBAdapter,
    starting_balance: Decimal,
) -> Callable[[], Awaitable[Decimal | None]]:
    """Equity from live paper_positions aggregates; None (fail closed) on error."""

    async def equity_provider() -> Decimal | None:
        try:
            components = await db_adapter.get_paper_equity_components()
        except Exception:
            logger.exception("Paper equity components unavailable; failing closed")
            return None
        return calculate_current_equity(
            starting_balance=starting_balance,
            total_fees=components.total_fees,
            realized_pnl=components.realized_pnl,
            unrealized_pnl=components.unrealized_pnl,
            total_funding=components.total_funding,
        )

    return equity_provider


async def initialize_trend_live_services(
    *,
    environ: Mapping[str, str],
    database_url: str,
    db_adapter: TrendLiveDBAdapter,
) -> dict[str, object]:
    """Build {trend_paper_broker, trend_decision_service, trend_daily_poller},
    or {} when TREND_LIVE_ENABLED is off."""
    config = load_trend_live_config_from_env(environ)
    if not config.enabled:
        return {}

    broker = PaperBroker(database_url=database_url)
    await broker.initialize()

    service = TrendDecisionService(
        config=config,
        broker=broker,
        equity_provider=make_paper_equity_provider(db_adapter, config.starting_balance),
        risk=build_trend_risk_parameters(config),
        decision_recorder=db_adapter.insert_trading_decision,
    )

    # Always mainnet public data (no keys needed for /api/v3/klines): the
    # accruing out-of-sample evidence must match the backtest's data source,
    # regardless of the engine's execution testnet mode.
    rest_client = BinanceRestClient(api_key="", api_secret="", testnet=False)

    poller = TrendDailyCandlePoller(
        rest_client=rest_client,
        service=service,
        config=TrendDailyPollerConfig(
            symbols=config.symbols,
            poll_interval_seconds=int(environ.get("TREND_LIVE_POLL_INTERVAL_SECONDS", "300")),
            warmup_days=int(environ.get("TREND_LIVE_WARMUP_DAYS", "90")),
        ),
        candle_writer=db_adapter.insert_candle,
        open_sleeve_loader=lambda: load_open_trend_sleeves(broker.db_pool),
    )

    logger.info(
        "Trend live services initialized (paper-only, symbols=%s, notional_pct=%s)",
        ",".join(config.symbols),
        config.notional_pct,
    )
    return {
        "trend_paper_broker": broker,
        "trend_decision_service": service,
        "trend_daily_poller": poller,
    }
