from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.backtest.position_sizing import (
    annualized_volatility,
    notional_quantity,
    vol_target_quantity,
)


class TestNotionalQuantity:
    def test_quantity_is_equity_fraction_over_entry(self) -> None:
        qty = notional_quantity(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            notional_pct=Decimal("0.5"),
        )

        assert qty == Decimal(50)

    @pytest.mark.parametrize(
        ("equity", "entry_price", "notional_pct"),
        [
            (Decimal(10_000), Decimal(0), Decimal("0.5")),
            (Decimal(10_000), Decimal(100), Decimal(0)),
            (Decimal(0), Decimal(100), Decimal("0.5")),
        ],
    )
    def test_non_positive_inputs_return_none(
        self,
        equity: Decimal,
        entry_price: Decimal,
        notional_pct: Decimal,
    ) -> None:
        qty = notional_quantity(
            equity=equity,
            entry_price=entry_price,
            notional_pct=notional_pct,
        )

        assert qty is None


class TestAnnualizedVolatility:
    def test_known_return_series_scales_by_sqrt_bars_per_year(self) -> None:
        # Per-bar returns [2%, 0%, 2%, 0%] -> population std 1% -> x sqrt(10000) = 100%
        closes = [
            Decimal(100),
            Decimal(102),
            Decimal(102),
            Decimal("104.04"),
            Decimal("104.04"),
        ]

        vol = annualized_volatility(closes, bars_per_year=10_000.0)

        assert vol is not None
        assert float(vol) == pytest.approx(1.0, abs=1e-12)

    def test_flat_series_returns_zero(self) -> None:
        closes = [Decimal(100)] * 5

        assert annualized_volatility(closes, bars_per_year=10_000.0) == Decimal(0)

    def test_fewer_than_two_closes_returns_none(self) -> None:
        assert annualized_volatility([Decimal(100)], bars_per_year=10_000.0) is None

    @pytest.mark.parametrize(
        "closes",
        [
            [Decimal(100), Decimal(0), Decimal(100)],
            [Decimal(100), Decimal("-5"), Decimal(100)],
        ],
    )
    def test_non_positive_close_returns_none(self, closes: list[Decimal]) -> None:
        # A zero/negative close would make the ratio undefined; return None
        # rather than raising DivisionByZero mid-sizing.
        assert annualized_volatility(closes, bars_per_year=10_000.0) is None


class TestVolTargetQuantity:
    def test_quantity_scales_equity_by_target_over_realized_vol(self) -> None:
        # 40% annual target / 100% realized vol -> 0.4 weight -> 10000 * 0.4 / 100
        qty = vol_target_quantity(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            vol_target_annual_pct=Decimal(40),
            annualized_vol=Decimal(1),
        )

        assert qty == Decimal(40)

    def test_low_realized_vol_levers_weight_up(self) -> None:
        # 40% target / 50% realized -> 0.8 weight -> 10000 * 0.8 / 100
        qty = vol_target_quantity(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            vol_target_annual_pct=Decimal(40),
            annualized_vol=Decimal("0.5"),
        )

        assert qty == Decimal(80)

    @pytest.mark.parametrize("annualized_vol", [None, Decimal(0)])
    def test_missing_or_zero_vol_returns_none(self, annualized_vol: Decimal | None) -> None:
        qty = vol_target_quantity(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            vol_target_annual_pct=Decimal(40),
            annualized_vol=annualized_vol,
        )

        assert qty is None

    def test_zero_target_returns_none(self) -> None:
        qty = vol_target_quantity(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            vol_target_annual_pct=Decimal(0),
            annualized_vol=Decimal(1),
        )

        assert qty is None
