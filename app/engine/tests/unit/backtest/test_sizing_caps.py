from __future__ import annotations

from decimal import Decimal

from app.engine.decision.sizing import RiskCappedSize, size_with_exposure_caps
from app.engine.models import RiskParameters


def make_risk(**overrides: object) -> RiskParameters:
    params: dict[str, object] = {
        "max_position_size": Decimal("999999"),
        "max_daily_loss": Decimal("1"),
        "max_drawdown": Decimal("1"),
        "risk_per_trade": Decimal("0.005"),
        "max_correlation": Decimal("1"),
        "max_open_positions": 100,
        "max_total_exposure_leverage": Decimal("100"),
        "max_symbol_exposure_pct": Decimal("1"),
        "max_position_notional_pct": Decimal("1"),
        "risk_data_max_age_seconds": 86400,
        "drawdown_lookback_days": 30,
    }
    params.update(overrides)
    return RiskParameters(**params)  # type: ignore[arg-type]


class TestSizeWithExposureCaps:
    def test_uncapped_fixed_fractional_size(self) -> None:
        sized = size_with_exposure_caps(
            equity=Decimal(10_000),
            entry_price=Decimal(1000),
            stop_loss=Decimal(900),
            risk=make_risk(),
        )

        assert sized == RiskCappedSize(
            quantity=Decimal("0.5"),
            original_quantity=Decimal("0.5"),
        )
        assert sized is not None
        assert sized.capped is False

    def test_notional_cap_matches_publisher_pinned_case(self) -> None:
        sized = size_with_exposure_caps(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            stop_loss=Decimal("99.99"),
            risk=make_risk(
                risk_per_trade=Decimal("0.02"),
                max_position_notional_pct=Decimal("0.10"),
            ),
        )

        assert sized is not None
        assert (sized.quantity, str(sized.original_quantity), sized.capped) == (
            Decimal(10),
            "20000",
            True,
        )

    def test_zero_stop_distance_returns_none(self) -> None:
        sized = size_with_exposure_caps(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            stop_loss=Decimal(100),
            risk=make_risk(),
        )

        assert sized is None

    def test_exhausted_symbol_headroom_skips_candidate(self) -> None:
        sized = size_with_exposure_caps(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            stop_loss=Decimal(99),
            risk=make_risk(max_symbol_exposure_pct=Decimal("0.5")),
            existing_symbol_exposure_usd=Decimal(6000),
        )

        assert sized is not None
        assert (sized.quantity, sized.capped) == (Decimal(50), False)

    def test_remaining_total_headroom_caps_quantity(self) -> None:
        sized = size_with_exposure_caps(
            equity=Decimal(10_000),
            entry_price=Decimal(100),
            stop_loss=Decimal(99),
            risk=make_risk(max_total_exposure_leverage=Decimal(1)),
            existing_total_exposure_usd=Decimal(9000),
        )

        assert sized is not None
        assert (sized.quantity, sized.capped) == (Decimal(10), True)
