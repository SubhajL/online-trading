"""
Unit tests for the trend_live configuration loader.

Phase 3a: the two ex-ante co-primaries (tsmom-28d, price>SMA-65d) must be
constructed exactly as backtested — daily, long/cash, no TP, notional sizing —
and the feature must default OFF.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.trend_live.config import (
    build_trend_risk_parameters,
    load_trend_live_config_from_env,
)

DEFAULT_NOTIONAL_PCT = Decimal("0.25")


def test_defaults_are_off_with_ex_ante_co_primaries() -> None:
    """Empty env loads flag-off config with the two backtested strategies."""
    config = load_trend_live_config_from_env({})

    tsmom28, sma65 = config.strategies
    assert (
        config.enabled,
        config.symbols,
        config.notional_pct,
        config.starting_balance,
        (tsmom28.strategy_id, tsmom28.config.signal_source, tsmom28.config.tsmom_lookback),
        (sma65.strategy_id, sma65.config.signal_source, sma65.config.sma_period),
    ) == (
        False,
        ("BTCUSDT", "ETHUSDT"),
        DEFAULT_NOTIONAL_PCT,
        Decimal(10_000),
        ("tsmom28", "tsmom", 28),
        ("sma65", "price_sma", 65),
    )


def test_strategy_configs_match_backtested_arm() -> None:
    """Both strategies carry the exact ex-ante knobs from the v3 taker arm."""
    config = load_trend_live_config_from_env({})

    knobs = [
        (
            spec.config.allow_short,
            spec.config.trend_tp_r,
            spec.config.atr_period,
            spec.config.atr_stop_mult,
            spec.config.sizing_mode,
            spec.config.notional_pct,
            spec.config.fee_bps_spot,
            spec.config.slippage_bps,
        )
        for spec in config.strategies
    ]
    expected = (
        False,
        Decimal(0),
        14,
        Decimal(2),
        "notional",
        DEFAULT_NOTIONAL_PCT,
        Decimal(10),
        Decimal(2),
    )
    assert knobs == [expected, expected]


def test_enabled_flag_and_overrides_parse() -> None:
    """Env overrides for flag, symbols, notional and balance are honored."""
    config = load_trend_live_config_from_env(
        {
            "TREND_LIVE_ENABLED": "1",
            "TREND_LIVE_SYMBOLS": "btcusdt, solusdt",
            "TREND_LIVE_NOTIONAL_PCT": "0.10",
            "TREND_LIVE_STARTING_BALANCE": "25000",
        },
    )

    assert (
        config.enabled,
        config.symbols,
        config.notional_pct,
        config.starting_balance,
        config.strategies[0].config.notional_pct,
    ) == (True, ("BTCUSDT", "SOLUSDT"), Decimal("0.10"), Decimal(25_000), Decimal("0.10"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"TREND_LIVE_NOTIONAL_PCT": "0"},
        {"TREND_LIVE_NOTIONAL_PCT": "-0.1"},
        {"TREND_LIVE_NOTIONAL_PCT": "1.5"},
        {"TREND_LIVE_STARTING_BALANCE": "0"},
        {"TREND_LIVE_SYMBOLS": " , "},
    ],
)
def test_invalid_env_fails_closed(overrides: dict[str, str]) -> None:
    """Bad sizing/symbol env values raise instead of silently trading."""
    with pytest.raises(ValueError, match="TREND_LIVE"):
        load_trend_live_config_from_env(overrides)


def test_risk_parameters_backstop_scales_with_notional() -> None:
    """Caps allow one sleeve per strategy: 25% per position, 50% per symbol."""
    config = load_trend_live_config_from_env({})

    risk = build_trend_risk_parameters(config)

    assert (
        risk.max_position_notional_pct,
        risk.max_symbol_exposure_pct,
        risk.max_total_exposure_leverage,
    ) == (DEFAULT_NOTIONAL_PCT, Decimal("0.5"), Decimal(3))
