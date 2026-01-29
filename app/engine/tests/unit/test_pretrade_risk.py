from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.engine.decision.pretrade_risk import evaluate_pretrade_risk
from app.engine.decision.risk_state import RiskSnapshot
from app.engine.models import RiskParameters, TradingDecision


def test_evaluate_pretrade_risk_blocks_on_daily_loss() -> None:
    risk = RiskParameters(
        max_position_size=Decimal("10"),
        max_daily_loss=Decimal("0.05"),
        max_drawdown=Decimal("0.25"),
        risk_per_trade=Decimal("0.02"),
        max_correlation=Decimal("0.7"),
        max_open_positions=10,
        max_total_exposure_leverage=Decimal("3"),
        max_symbol_exposure_pct=Decimal("0.25"),
        max_position_notional_pct=Decimal("0.10"),
        risk_data_max_age_seconds=120,
        drawdown_lookback_days=30,
    )

    snapshot = RiskSnapshot(
        equity=Decimal("900"),
        equity_ts=datetime(2026, 1, 29, 0, 1, tzinfo=UTC),
        start_of_day_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        open_positions_count=0,
        total_exposure_usd=Decimal("0"),
        symbol_exposure_usd={},
    )

    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=datetime(2026, 1, 29, 0, 2, tzinfo=UTC),
        action="BUY",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        confidence=Decimal("0.9"),
        reasoning="test",
    )

    ok, reasons = evaluate_pretrade_risk(snapshot=snapshot, decision=decision, risk=risk)
    assert ok is False
    assert any("daily_loss" in r for r in reasons)


def test_evaluate_pretrade_risk_blocks_on_total_exposure_leverage() -> None:
    risk = RiskParameters(
        max_position_size=Decimal("10"),
        max_daily_loss=Decimal("1"),
        max_drawdown=Decimal("1"),
        risk_per_trade=Decimal("0.02"),
        max_correlation=Decimal("0.7"),
        max_open_positions=10,
        max_total_exposure_leverage=Decimal("3"),
        max_symbol_exposure_pct=Decimal("1"),
        max_position_notional_pct=Decimal("1"),
        risk_data_max_age_seconds=120,
        drawdown_lookback_days=30,
    )

    snapshot = RiskSnapshot(
        equity=Decimal("1000"),
        equity_ts=datetime(2026, 1, 29, 0, 1, tzinfo=UTC),
        start_of_day_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        open_positions_count=0,
        total_exposure_usd=Decimal("2900"),
        symbol_exposure_usd={},
    )

    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=datetime(2026, 1, 29, 0, 2, tzinfo=UTC),
        action="BUY",
        entry_price=Decimal("200"),
        quantity=Decimal("1"),
        stop_loss=Decimal("190"),
        take_profit=Decimal("220"),
        confidence=Decimal("0.9"),
        reasoning="test",
    )

    ok, reasons = evaluate_pretrade_risk(snapshot=snapshot, decision=decision, risk=risk)
    assert ok is False
    assert any("max_total_exposure" in r for r in reasons)


def test_evaluate_pretrade_risk_allows_when_limits_ok() -> None:
    risk = RiskParameters(
        max_position_size=Decimal("10"),
        max_daily_loss=Decimal("0.05"),
        max_drawdown=Decimal("0.20"),
        risk_per_trade=Decimal("0.02"),
        max_correlation=Decimal("0.7"),
        max_open_positions=10,
        max_total_exposure_leverage=Decimal("3"),
        max_symbol_exposure_pct=Decimal("0.25"),
        max_position_notional_pct=Decimal("0.10"),
        risk_data_max_age_seconds=120,
        drawdown_lookback_days=30,
    )

    snapshot = RiskSnapshot(
        equity=Decimal("1000"),
        equity_ts=datetime(2026, 1, 29, 0, 1, tzinfo=UTC),
        start_of_day_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        open_positions_count=0,
        total_exposure_usd=Decimal("0"),
        symbol_exposure_usd={},
    )

    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=datetime(2026, 1, 29, 0, 2, tzinfo=UTC),
        action="BUY",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        confidence=Decimal("0.9"),
        reasoning="test",
    )

    ok, reasons = evaluate_pretrade_risk(snapshot=snapshot, decision=decision, risk=risk)
    assert ok is True
    assert reasons == ["ok"]
