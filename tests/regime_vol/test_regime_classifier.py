"""Tests for market regime classification."""

from decimal import Decimal
import pytest

from app.engine.regime_vol.engine import (
    MarketRegime,
    calculate_volatility_metrics,
    classify_regime,
    determine_regime,
)


def test_regime_transitions():
    """Test TREND→RANGE→SHOCK classifications."""
    config = {
        "trend_thresholds": {
            "adx_min": 70,
            "bb_width_max": 30,
        },
        "range_thresholds": {
            "adx_max": 30,
            "atr_percentile_max": 40,
        },
        "shock_thresholds": {
            "atr_percentile_min": 80,
            "bb_width_min": 70,
        },
    }

    # TREND: High ADX, low BB width
    regime = classify_regime(
        atr_percentile=Decimal("50"),
        bb_width_percentile=Decimal("20"),
        adx_percentile=Decimal("75"),
        config=config,
    )
    assert regime == MarketRegime.TREND

    # RANGE: Low ADX, low ATR
    regime = classify_regime(
        atr_percentile=Decimal("30"),
        bb_width_percentile=Decimal("40"),
        adx_percentile=Decimal("25"),
        config=config,
    )
    assert regime == MarketRegime.RANGE

    # SHOCK: High ATR, high BB width
    regime = classify_regime(
        atr_percentile=Decimal("85"),
        bb_width_percentile=Decimal("75"),
        adx_percentile=Decimal("50"),
        config=config,
    )
    assert regime == MarketRegime.SHOCK


def test_volatility_metrics_calculation():
    """Test calculation of ATR, BB width, and ADX percentiles."""
    # Mock candle data
    candles = [
        {"high": Decimal("101"), "low": Decimal("99"), "close": Decimal("100")},
        {"high": Decimal("102"), "low": Decimal("98"), "close": Decimal("101")},
        {"high": Decimal("103"), "low": Decimal("97"), "close": Decimal("99")},
        {"high": Decimal("101"), "low": Decimal("99"), "close": Decimal("100")},
        {"high": Decimal("100"), "low": Decimal("99.5"), "close": Decimal("99.8")},
    ] * 20  # Repeat to have enough data

    metrics = calculate_volatility_metrics(candles, lookback_period=100)

    assert "atr_percentile" in metrics
    assert "bb_width_percentile" in metrics
    assert "adx_percentile" in metrics

    # All percentiles should be between 0 and 100
    assert Decimal("0") <= metrics["atr_percentile"] <= Decimal("100")
    assert Decimal("0") <= metrics["bb_width_percentile"] <= Decimal("100")
    assert Decimal("0") <= metrics["adx_percentile"] <= Decimal("100")


def test_regime_determination_logic():
    """Test regime determination from metrics."""
    thresholds = {
        "trend": {"adx_min": 70, "bb_width_max": 30},
        "range": {"adx_max": 30, "atr_max": 40},
        "shock": {"atr_min": 80, "bb_width_min": 70},
    }

    # Clear trend metrics
    metrics = {
        "atr_percentile": Decimal("50"),
        "bb_width_percentile": Decimal("20"),
        "adx_percentile": Decimal("75"),
    }
    assert determine_regime(metrics, thresholds) == MarketRegime.TREND

    # Clear range metrics
    metrics = {
        "atr_percentile": Decimal("30"),
        "bb_width_percentile": Decimal("40"),
        "adx_percentile": Decimal("25"),
    }
    assert determine_regime(metrics, thresholds) == MarketRegime.RANGE

    # Clear shock metrics
    metrics = {
        "atr_percentile": Decimal("85"),
        "bb_width_percentile": Decimal("75"),
        "adx_percentile": Decimal("50"),
    }
    assert determine_regime(metrics, thresholds) == MarketRegime.SHOCK


def test_edge_case_regimes():
    """Test edge cases and ambiguous metrics."""
    thresholds = {
        "trend": {"adx_min": 70, "bb_width_max": 30},
        "range": {"adx_max": 30, "atr_max": 40},
        "shock": {"atr_min": 80, "bb_width_min": 70},
    }

    # Ambiguous metrics - should default to RANGE
    metrics = {
        "atr_percentile": Decimal("50"),
        "bb_width_percentile": Decimal("50"),
        "adx_percentile": Decimal("50"),
    }
    assert determine_regime(metrics, thresholds) == MarketRegime.RANGE