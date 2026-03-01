"""
Unit tests for fill model - bracket trade simulation with costs.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.telegram_validator.fill_model import (
    BracketSpec,
    CostConfig,
    apply_slippage,
    check_level_touch,
    compute_fees,
    compute_funding_cost,
    resolve_intrabar_conflict,
    simulate_bracket_fills,
)


def make_candle(
    *,
    open_time: datetime,
    open_p: Decimal,
    high_p: Decimal,
    low_p: Decimal,
    close_p: Decimal,
) -> Candle:
    """Helper to create test candles."""
    return Candle(
        venue="spot",
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open_price=open_p,
        high_price=high_p,
        low_price=low_p,
        close_price=close_p,
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        trades=50,
        taker_buy_base_volume=Decimal("50"),
        taker_buy_quote_volume=Decimal("5000"),
    )


class TestBracketSpec:
    """Tests for BracketSpec validation."""

    def test_valid_bracket_with_single_tp(self) -> None:
        """Single TP with 100% size is valid."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        assert bracket.side == "BUY"
        assert len(bracket.take_profits) == 1

    def test_valid_bracket_with_multiple_tps(self) -> None:
        """Multiple TPs with sizes summing to 1.0 is valid."""
        bracket = BracketSpec(
            side="SELL",
            entry_price=Decimal("100"),
            stop_loss=Decimal("105"),
            take_profits=(Decimal("95"), Decimal("90")),
            tp_sizes=(Decimal("0.5"), Decimal("0.5")),
        )
        assert len(bracket.take_profits) == 2
        assert sum(bracket.tp_sizes) == Decimal("1.0")

    def test_raises_on_mismatched_tp_sizes_length(self) -> None:
        """Raises if take_profits and tp_sizes have different lengths."""
        with pytest.raises(ValueError, match="same length"):
            BracketSpec(
                side="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("95"),
                take_profits=(Decimal("110"), Decimal("120")),
                tp_sizes=(Decimal("1.0"),),  # Only one size
            )

    def test_raises_on_sizes_not_summing_to_one(self) -> None:
        """Raises if tp_sizes don't sum to 1.0."""
        with pytest.raises(ValueError, match="sum to 1.0"):
            BracketSpec(
                side="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("95"),
                take_profits=(Decimal("110"), Decimal("120")),
                tp_sizes=(Decimal("0.3"), Decimal("0.3")),  # Sum = 0.6
            )


class TestCheckLevelTouch:
    """Tests for check_level_touch function."""

    def test_buy_tp_touched_when_high_reaches_level(self) -> None:
        """BUY TP is touched when candle high >= level."""
        candle = make_candle(
            open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open_p=Decimal("100"),
            high_p=Decimal("110"),
            low_p=Decimal("99"),
            close_p=Decimal("108"),
        )
        result = check_level_touch(candle, Decimal("110"), "BUY", is_stop=False)
        assert result is True

    def test_buy_tp_not_touched_when_high_below_level(self) -> None:
        """BUY TP is NOT touched when candle high < level."""
        candle = make_candle(
            open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open_p=Decimal("100"),
            high_p=Decimal("109"),
            low_p=Decimal("99"),
            close_p=Decimal("108"),
        )
        result = check_level_touch(candle, Decimal("110"), "BUY", is_stop=False)
        assert result is False

    def test_buy_sl_touched_when_low_reaches_level(self) -> None:
        """BUY SL is touched when candle low <= level."""
        candle = make_candle(
            open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open_p=Decimal("100"),
            high_p=Decimal("102"),
            low_p=Decimal("95"),
            close_p=Decimal("96"),
        )
        result = check_level_touch(candle, Decimal("95"), "BUY", is_stop=True)
        assert result is True

    def test_sell_tp_touched_when_low_reaches_level(self) -> None:
        """SELL TP is touched when candle low <= level."""
        candle = make_candle(
            open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open_p=Decimal("100"),
            high_p=Decimal("102"),
            low_p=Decimal("90"),
            close_p=Decimal("92"),
        )
        result = check_level_touch(candle, Decimal("90"), "SELL", is_stop=False)
        assert result is True

    def test_sell_sl_touched_when_high_reaches_level(self) -> None:
        """SELL SL is touched when candle high >= level."""
        candle = make_candle(
            open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open_p=Decimal("100"),
            high_p=Decimal("105"),
            low_p=Decimal("98"),
            close_p=Decimal("104"),
        )
        result = check_level_touch(candle, Decimal("105"), "SELL", is_stop=True)
        assert result is True


class TestResolveIntrabarConflict:
    """Tests for resolve_intrabar_conflict function."""

    def test_worst_case_chooses_sl(self) -> None:
        """With worst_case policy, SL wins when both touched."""
        result = resolve_intrabar_conflict(
            sl_touched=True,
            tp_touched=True,
            policy="worst_case",
        )
        assert result == "SL"

    def test_best_case_chooses_tp(self) -> None:
        """With best_case policy, TP wins when both touched."""
        result = resolve_intrabar_conflict(
            sl_touched=True,
            tp_touched=True,
            policy="best_case",
        )
        assert result == "TP"


class TestApplySlippage:
    """Tests for apply_slippage function."""

    def test_buy_entry_slippage_increases_price(self) -> None:
        """BUY entry slippage makes entry price worse (higher)."""
        result = apply_slippage(
            price=Decimal("100"),
            side="BUY",
            slippage_bps=Decimal("10"),  # 0.1%
            is_entry=True,
        )
        assert result == Decimal("100.10")

    def test_sell_entry_slippage_decreases_price(self) -> None:
        """SELL entry slippage makes entry price worse (lower)."""
        result = apply_slippage(
            price=Decimal("100"),
            side="SELL",
            slippage_bps=Decimal("10"),  # 0.1%
            is_entry=True,
        )
        assert result == Decimal("99.90")

    def test_buy_exit_slippage_decreases_price(self) -> None:
        """BUY exit (sell to close) slippage makes exit worse (lower)."""
        result = apply_slippage(
            price=Decimal("100"),
            side="BUY",
            slippage_bps=Decimal("10"),
            is_entry=False,
        )
        assert result == Decimal("99.90")

    def test_sell_exit_slippage_increases_price(self) -> None:
        """SELL exit (buy to close) slippage makes exit worse (higher)."""
        result = apply_slippage(
            price=Decimal("100"),
            side="SELL",
            slippage_bps=Decimal("10"),
            is_entry=False,
        )
        assert result == Decimal("100.10")

    def test_zero_slippage_returns_same_price(self) -> None:
        """Zero slippage returns unchanged price."""
        result = apply_slippage(
            price=Decimal("100"),
            side="BUY",
            slippage_bps=Decimal("0"),
            is_entry=True,
        )
        assert result == Decimal("100")


class TestComputeFees:
    """Tests for compute_fees function."""

    def test_computes_fee_correctly(self) -> None:
        """Fee = notional * (fee_bps / 10000)."""
        result = compute_fees(
            notional=Decimal("10000"),
            fee_bps=Decimal("10"),  # 0.1%
        )
        assert result == Decimal("10")  # 10000 * 0.001

    def test_zero_notional_returns_zero_fee(self) -> None:
        """Zero notional means zero fee."""
        result = compute_fees(notional=Decimal("0"), fee_bps=Decimal("10"))
        assert result == Decimal("0")

    def test_large_notional_computes_correctly(self) -> None:
        """Large notional values compute correctly."""
        result = compute_fees(
            notional=Decimal("1000000"),
            fee_bps=Decimal("5"),  # 0.05%
        )
        assert result == Decimal("500")


class TestComputeFundingCost:
    """Tests for compute_funding_cost function."""

    def test_no_funding_periods_crossed(self) -> None:
        """No cost if no funding periods crossed."""
        entry_ts = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
        exit_ts = datetime(2025, 1, 1, 15, 0, tzinfo=UTC)  # 6 hours, no 16:00 crossed
        result = compute_funding_cost(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            notional=Decimal("10000"),
            funding_rate_8h=Decimal("10"),  # 0.1%
        )
        assert result == Decimal("0")

    def test_one_funding_period_crossed(self) -> None:
        """Cost for one funding period."""
        entry_ts = datetime(2025, 1, 1, 7, 0, tzinfo=UTC)
        exit_ts = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)  # Crosses 08:00
        result = compute_funding_cost(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            notional=Decimal("10000"),
            funding_rate_8h=Decimal("10"),  # 0.1%
        )
        assert result == Decimal("10")  # 10000 * 0.001 * 1 period

    def test_multiple_funding_periods_crossed(self) -> None:
        """Cost increases with more funding periods."""
        entry_ts = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)
        exit_ts = datetime(2025, 1, 1, 17, 0, tzinfo=UTC)  # Crosses 08:00 and 16:00
        result = compute_funding_cost(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            notional=Decimal("10000"),
            funding_rate_8h=Decimal("10"),
        )
        assert result == Decimal("20")  # 2 periods


class TestSimulateBracketFills:
    """Tests for simulate_bracket_fills function."""

    def test_hits_tp_when_only_tp_touched(self) -> None:
        """TP fills when only TP level is touched."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("102"),
                low_p=Decimal("99"),
                close_p=Decimal("101"),
            ),
            make_candle(
                open_time=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
                open_p=Decimal("101"),
                high_p=Decimal("112"),  # Hits TP at 110
                low_p=Decimal("100"),
                close_p=Decimal("111"),
            ),
        ]

        result = simulate_bracket_fills(candles, bracket)

        assert result.outcome == "TP_FULL"
        assert len(result.fills) == 1
        assert result.fills[0].fill_type == "TP"
        assert result.candles_held == 2

    def test_hits_sl_when_only_sl_touched(self) -> None:
        """SL fills when only SL level is touched."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("101"),
                low_p=Decimal("94"),  # Hits SL at 95
                close_p=Decimal("94"),
            ),
        ]

        result = simulate_bracket_fills(candles, bracket)

        assert result.outcome == "SL"
        assert len(result.fills) == 1
        assert result.fills[0].fill_type == "SL"

    def test_intrabar_worst_case_chooses_sl(self) -> None:
        """When both SL and TP touched, worst_case chooses SL."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),  # Hits TP
                low_p=Decimal("93"),  # Also hits SL
                close_p=Decimal("105"),
            ),
        ]

        result = simulate_bracket_fills(candles, bracket, intrabar_policy="worst_case")

        assert result.outcome == "SL"

    def test_intrabar_best_case_chooses_tp(self) -> None:
        """When both SL and TP touched, best_case chooses TP."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),  # Hits TP
                low_p=Decimal("93"),  # Also hits SL
                close_p=Decimal("105"),
            ),
        ]

        result = simulate_bracket_fills(candles, bracket, intrabar_policy="best_case")

        assert result.outcome == "TP_FULL"

    def test_timeout_when_max_bars_exceeded(self) -> None:
        """Returns TIMEOUT when max_bars exceeded without fill."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profits=(Decimal("120"),),
            tp_sizes=(Decimal("1.0"),),
        )
        # Candles that don't hit SL or TP
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, i, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("105"),
                low_p=Decimal("95"),
                close_p=Decimal("100"),
            )
            for i in range(10)
        ]

        result = simulate_bracket_fills(candles, bracket, max_bars=5)

        assert result.outcome == "TIMEOUT"
        assert result.candles_held == 5

    def test_fees_reduce_net_pnl(self) -> None:
        """Fees reduce net_pnl below gross_pnl."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),
                low_p=Decimal("99"),
                close_p=Decimal("111"),
            ),
        ]
        cost_config = CostConfig(fee_bps=Decimal("10"), slippage_bps=Decimal("0"))

        result = simulate_bracket_fills(candles, bracket, cost_config=cost_config)

        assert result.fees > Decimal("0")
        assert result.net_pnl < result.gross_pnl

    def test_slippage_worsens_entry_for_buy(self) -> None:
        """Slippage makes BUY entry price worse (higher)."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("112"),
                low_p=Decimal("99"),
                close_p=Decimal("111"),
            ),
        ]

        # With zero slippage
        result_no_slip = simulate_bracket_fills(
            candles,
            bracket,
            cost_config=CostConfig(slippage_bps=Decimal("0"), fee_bps=Decimal("0")),
        )

        # With slippage
        result_slip = simulate_bracket_fills(
            candles,
            bracket,
            cost_config=CostConfig(slippage_bps=Decimal("50"), fee_bps=Decimal("0")),
        )

        assert result_slip.slippage_cost > Decimal("0")
        assert result_slip.net_pnl < result_no_slip.net_pnl

    def test_partial_tp_fills_ladder(self) -> None:
        """Multiple TPs can fill progressively."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("105"), Decimal("110")),
            tp_sizes=(Decimal("0.5"), Decimal("0.5")),
        )
        candles = [
            make_candle(
                open_time=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
                open_p=Decimal("100"),
                high_p=Decimal("106"),  # Hits TP1 only
                low_p=Decimal("99"),
                close_p=Decimal("105"),
            ),
            make_candle(
                open_time=datetime(2025, 1, 1, 11, 0, tzinfo=UTC),
                open_p=Decimal("105"),
                high_p=Decimal("112"),  # Hits TP2
                low_p=Decimal("104"),
                close_p=Decimal("110"),
            ),
        ]

        result = simulate_bracket_fills(candles, bracket)

        assert result.outcome == "TP_FULL"
        assert len(result.fills) == 2
        assert result.fills[0].fill_type == "TP"
        assert result.fills[0].level_index == 0
        assert result.fills[1].fill_type == "TP"
        assert result.fills[1].level_index == 1

    def test_none_outcome_when_no_candles(self) -> None:
        """Returns NONE when no candles provided."""
        bracket = BracketSpec(
            side="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("95"),
            take_profits=(Decimal("110"),),
            tp_sizes=(Decimal("1.0"),),
        )

        result = simulate_bracket_fills([], bracket)

        assert result.outcome == "NONE"
        assert result.candles_held == 0
