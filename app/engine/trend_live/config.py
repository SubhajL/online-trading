"""
trend_live configuration — feature flag plus the two ex-ante co-primary configs.

The BacktestConfigs must match the backtested v3 daily taker arm exactly
(reports/backtest/strategies/v3-tsmom28-taker.yaml and v3-sma65-taker.yaml):
changing a knob here silently invalidates the accruing out-of-sample evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from app.engine.backtest.types import BacktestConfig
from app.engine.models import RiskParameters

if TYPE_CHECKING:
    from collections.abc import Mapping

_DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT"
_DEFAULT_NOTIONAL_PCT = "0.25"
_DEFAULT_STARTING_BALANCE = "10000"


@dataclass(frozen=True)
class TrendStrategySpec:
    strategy_id: str
    config: BacktestConfig


@dataclass(frozen=True)
class TrendLiveConfig:
    enabled: bool
    symbols: tuple[str, ...]
    notional_pct: Decimal
    starting_balance: Decimal
    strategies: tuple[TrendStrategySpec, ...]


def _decimal_env(environ: Mapping[str, str], key: str, default: str) -> Decimal:
    raw = environ.get(key, default)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"{key} is not a valid decimal: {raw!r}") from exc


def _co_primary_config(notional_pct: Decimal, **overrides: object) -> BacktestConfig:
    return BacktestConfig(
        fee_bps_spot=Decimal(10),
        slippage_bps=Decimal(2),
        funding_model="disabled",
        risk_per_trade=Decimal("0.005"),
        allow_short=False,
        atr_period=14,
        atr_stop_mult=Decimal(2),
        trend_tp_r=Decimal(0),
        sizing_mode="notional",
        notional_pct=notional_pct,
        max_position_notional_pct=notional_pct,
        max_symbol_exposure_pct=min(2 * notional_pct, Decimal(1)),
        max_total_exposure_leverage=Decimal(3),
        **overrides,  # type: ignore[arg-type]
    )


def load_trend_live_config_from_env(environ: Mapping[str, str]) -> TrendLiveConfig:
    """Build the phase-3a config; defaults are OFF and the ex-ante arm."""
    enabled = environ.get("TREND_LIVE_ENABLED", "0") == "1"

    symbols = tuple(
        symbol.strip().upper()
        for symbol in environ.get("TREND_LIVE_SYMBOLS", _DEFAULT_SYMBOLS).split(",")
        if symbol.strip()
    )
    if not symbols:
        raise ValueError("TREND_LIVE_SYMBOLS must name at least one symbol")

    notional_pct = _decimal_env(environ, "TREND_LIVE_NOTIONAL_PCT", _DEFAULT_NOTIONAL_PCT)
    if not Decimal(0) < notional_pct <= Decimal(1):
        raise ValueError(f"TREND_LIVE_NOTIONAL_PCT must be in (0, 1]: {notional_pct}")

    starting_balance = _decimal_env(
        environ,
        "TREND_LIVE_STARTING_BALANCE",
        _DEFAULT_STARTING_BALANCE,
    )
    if starting_balance <= 0:
        raise ValueError(f"TREND_LIVE_STARTING_BALANCE must be positive: {starting_balance}")

    strategies = (
        TrendStrategySpec(
            strategy_id="tsmom28",
            config=_co_primary_config(
                notional_pct,
                signal_source="tsmom",
                tsmom_lookback=28,
                tsmom_deadband_bps=Decimal(0),
            ),
        ),
        TrendStrategySpec(
            strategy_id="sma65",
            config=_co_primary_config(
                notional_pct,
                signal_source="price_sma",
                sma_period=65,
            ),
        ),
    )

    return TrendLiveConfig(
        enabled=enabled,
        symbols=symbols,
        notional_pct=notional_pct,
        starting_balance=starting_balance,
        strategies=strategies,
    )


def build_trend_risk_parameters(config: TrendLiveConfig) -> RiskParameters:
    """Exposure-cap backstop for trend sizing; loss/drawdown gates stay off
    here (paper-only path), mirroring the simulator's RiskParameters."""
    return RiskParameters(
        max_position_size=Decimal(1_000_000_000),
        max_daily_loss=Decimal(1),
        max_drawdown=Decimal(1),
        risk_per_trade=Decimal("0.005"),
        max_correlation=Decimal(1),
        max_open_positions=len(config.strategies) * len(config.symbols) + 1,
        max_total_exposure_leverage=Decimal(3),
        max_symbol_exposure_pct=min(2 * config.notional_pct, Decimal(1)),
        max_position_notional_pct=config.notional_pct,
        risk_data_max_age_seconds=86400,
        drawdown_lookback_days=30,
    )
