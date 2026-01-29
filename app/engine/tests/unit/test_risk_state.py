from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.decision.risk_state import build_risk_snapshot
from app.engine.models import RiskParameters


class _FakeDBAdapter:
    def __init__(
        self,
        *,
        equity: Decimal,
        equity_ts: datetime,
        start_of_day_equity: Decimal | None,
        peak_equity: Decimal | None,
        positions: list[dict[str, object]],
    ) -> None:
        self._equity = equity
        self._equity_ts = equity_ts
        self._start_of_day_equity = start_of_day_equity
        self._peak_equity = peak_equity
        self._positions = positions

    async def get_latest_equity_sample(self):
        return self._equity, self._equity_ts

    async def get_equity_sample_at_or_after(self, _ts: datetime):
        return self._start_of_day_equity

    async def get_peak_equity_since(self, _ts: datetime):
        return self._peak_equity

    async def get_active_positions(self, _venue: str):
        return self._positions


@pytest.mark.asyncio
async def test_build_risk_snapshot_rejects_stale_equity_sample() -> None:
    now = datetime(2026, 1, 29, 0, 10, tzinfo=UTC)
    db = _FakeDBAdapter(
        equity=Decimal("1000"),
        equity_ts=now - timedelta(seconds=500),
        start_of_day_equity=Decimal("1000"),
        peak_equity=Decimal("1000"),
        positions=[],
    )

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

    snapshot, errors = await build_risk_snapshot(
        db_adapter=db,
        venue="SPOT",
        now=now,
        risk=risk,
    )

    assert snapshot is None
    assert any(e.error_type == "stale_equity_sample" for e in errors)


@pytest.mark.asyncio
async def test_build_risk_snapshot_computes_exposure_from_positions() -> None:
    now = datetime(2026, 1, 29, 0, 10, tzinfo=UTC)
    db = _FakeDBAdapter(
        equity=Decimal("1000"),
        equity_ts=now - timedelta(seconds=30),
        start_of_day_equity=Decimal("1000"),
        peak_equity=Decimal("1200"),
        positions=[
            {"symbol": "BTCUSDT", "size": Decimal("2"), "current_price": Decimal("100")},
            {"symbol": "ETHUSDT", "size": "1.5", "current_price": "200"},
        ],
    )

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

    snapshot, errors = await build_risk_snapshot(
        db_adapter=db,
        venue="SPOT",
        now=now,
        risk=risk,
    )

    assert errors == []
    assert snapshot is not None
    assert snapshot.open_positions_count == 2
    assert snapshot.total_exposure_usd == Decimal("500")
    assert snapshot.symbol_exposure_usd["BTCUSDT"] == Decimal("200")
    assert snapshot.symbol_exposure_usd["ETHUSDT"] == Decimal("300")
