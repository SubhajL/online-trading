"""
Unit tests for outcome_comparison module - side-by-side Captain vs Internal comparison.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.models import Candle, TimeFrame
from app.engine.telegram_validator.fill_model import CostConfig
from app.engine.telegram_validator.outcome_comparison import (
    OutcomeResult,
    MatchedComparison,
    StreamComparisonResult,
    evaluate_bracket_outcome,
    compute_win_rate,
    compare_captain_vs_internal_outcomes,
)


def make_candle(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    timestamp: datetime | None = None,
) -> Candle:
    """Create a test candle."""
    from datetime import timedelta

    open_time = timestamp or datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
    return Candle(
        venue="spot",
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        trades=100,
        taker_buy_base_volume=Decimal("50"),
        taker_buy_quote_volume=Decimal("5000"),
    )


class TestEvaluateBracketOutcome:
    """Tests for evaluate_bracket_outcome function."""

    def test_returns_none_when_missing_direction(self) -> None:
        """Outcome is None when direction is missing."""
        candles = [make_candle(Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"))]
        result = evaluate_bracket_outcome(
            direction="",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            candles=candles,
        )
        assert result is None

    def test_returns_none_when_no_candles(self) -> None:
        """Outcome is None when candles list is empty."""
        result = evaluate_bracket_outcome(
            direction="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            candles=[],
        )
        assert result is None

    def test_evaluates_buy_tp_hit(self) -> None:
        """Buy order hits TP when high reaches target."""
        candles = [
            make_candle(Decimal("100"), Decimal("115"), Decimal("98"), Decimal("112")),
        ]
        result = evaluate_bracket_outcome(
            direction="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            candles=candles,
        )
        assert result is not None
        assert result.outcome == "TP_FULL"
        assert result.direction == "BUY"

    def test_evaluates_buy_sl_hit(self) -> None:
        """Buy order hits SL when low reaches stop."""
        candles = [
            make_candle(Decimal("100"), Decimal("102"), Decimal("88"), Decimal("89")),
        ]
        result = evaluate_bracket_outcome(
            direction="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("120"),
            candles=candles,
        )
        assert result is not None
        assert result.outcome == "SL"

    def test_evaluates_sell_tp_hit(self) -> None:
        """Sell order hits TP when low reaches target."""
        candles = [
            make_candle(Decimal("100"), Decimal("102"), Decimal("88"), Decimal("90")),
        ]
        result = evaluate_bracket_outcome(
            direction="SELL",
            entry_price=Decimal("100"),
            stop_loss=Decimal("110"),
            take_profit=Decimal("90"),
            candles=candles,
        )
        assert result is not None
        assert result.outcome == "TP_FULL"

    def test_evaluates_sell_sl_hit(self) -> None:
        """Sell order hits SL when high reaches stop."""
        candles = [
            make_candle(Decimal("100"), Decimal("115"), Decimal("98"), Decimal("112")),
        ]
        result = evaluate_bracket_outcome(
            direction="SELL",
            entry_price=Decimal("100"),
            stop_loss=Decimal("110"),
            take_profit=Decimal("85"),
            candles=candles,
        )
        assert result is not None
        assert result.outcome == "SL"

    def test_applies_cost_config(self) -> None:
        """Cost config affects net PnL."""
        candles = [
            make_candle(Decimal("100"), Decimal("115"), Decimal("98"), Decimal("112")),
        ]

        # Without costs
        result_no_costs = evaluate_bracket_outcome(
            direction="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            candles=candles,
            cost_config=CostConfig(
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
                funding_rate_8h=Decimal("0"),
            ),
        )

        # With costs
        result_with_costs = evaluate_bracket_outcome(
            direction="BUY",
            entry_price=Decimal("100"),
            stop_loss=Decimal("90"),
            take_profit=Decimal("110"),
            candles=candles,
            cost_config=CostConfig(
                fee_bps=Decimal("10"),
                slippage_bps=Decimal("5"),
                funding_rate_8h=Decimal("1"),
            ),
        )

        assert result_no_costs is not None
        assert result_with_costs is not None
        assert result_with_costs.net_pnl < result_no_costs.net_pnl


class TestComputeWinRate:
    """Tests for compute_win_rate function."""

    def test_returns_zero_for_empty_list(self) -> None:
        """Win rate is 0 for empty outcomes."""
        assert compute_win_rate([]) == Decimal("0")

    def test_returns_zero_for_no_decided_outcomes(self) -> None:
        """Win rate is 0 when no outcomes are decided (all NONE/TIMEOUT)."""
        outcomes = [
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="NONE",
                net_pnl=Decimal("0"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=0,
            ),
        ]
        assert compute_win_rate(outcomes) == Decimal("0")

    def test_computes_correct_win_rate_all_wins(self) -> None:
        """Win rate is 1.0 when all outcomes are wins."""
        outcomes = [
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="TP_FULL",
                net_pnl=Decimal("10"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=5,
            ),
            OutcomeResult(
                direction="SELL",
                entry_price=Decimal("100"),
                stop_loss=Decimal("110"),
                take_profit=Decimal("90"),
                outcome="TP_PARTIAL",
                net_pnl=Decimal("5"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=3,
            ),
        ]
        assert compute_win_rate(outcomes) == Decimal("1")

    def test_computes_correct_win_rate_mixed(self) -> None:
        """Win rate is correct for mixed outcomes."""
        outcomes = [
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="TP_FULL",
                net_pnl=Decimal("10"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=5,
            ),
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="SL",
                net_pnl=Decimal("-10"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=2,
            ),
        ]
        assert compute_win_rate(outcomes) == Decimal("0.5")

    def test_ignores_undecided_outcomes(self) -> None:
        """Win rate ignores NONE and TIMEOUT outcomes."""
        outcomes = [
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="TP_FULL",
                net_pnl=Decimal("10"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=5,
            ),
            OutcomeResult(
                direction="BUY",
                entry_price=Decimal("100"),
                stop_loss=Decimal("90"),
                take_profit=Decimal("110"),
                outcome="NONE",
                net_pnl=Decimal("0"),
                fees=Decimal("0"),
                slippage_cost=Decimal("0"),
                funding_cost=Decimal("0"),
                candles_held=100,
            ),
        ]
        # 1 win out of 1 decided = 100%
        assert compute_win_rate(outcomes) == Decimal("1")


class _FakeComparisonAdapter:
    """Fake adapter for testing compare_captain_vs_internal_outcomes."""

    def __init__(
        self,
        validations: list[dict] | None = None,
        signals: list[dict] | None = None,
        candles: list[Candle] | None = None,
        decisions: dict[str, dict] | None = None,
    ) -> None:
        self.validations = validations or []
        self.signals = signals or []
        self.candles = candles or []
        self.decisions = decisions or {}

    async def get_external_telegram_signal_validations(self, **kwargs) -> list[dict]:  # noqa: ANN001
        return self.validations

    async def get_external_telegram_signals(self, **kwargs) -> list[dict]:  # noqa: ANN001
        return self.signals

    async def get_candles(self, **kwargs) -> list[Candle]:  # noqa: ANN001
        return self.candles

    async def get_trading_decision_by_id(self, decision_id: str) -> dict | None:
        return self.decisions.get(decision_id)


class TestCompareOutcomes:
    """Tests for compare_captain_vs_internal_outcomes function."""

    @pytest.mark.asyncio
    async def test_returns_empty_result_for_no_validations(self) -> None:
        """Result has zero counts when no validations exist."""
        adapter = _FakeComparisonAdapter()
        result = await compare_captain_vs_internal_outcomes(
            adapter,
            source="captain",
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 1, 2, tzinfo=UTC),
        )
        assert result.captain_count == 0
        assert result.internal_count == 0
        assert result.matched_count == 0

    @pytest.mark.asyncio
    async def test_evaluates_captain_signal_without_internal_match(self) -> None:
        """Captain outcome evaluated even without internal match."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        adapter = _FakeComparisonAdapter(
            validations=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "internal_kind": None,
                    "internal_id": None,
                    "internal_timestamp": None,
                },
            ],
            signals=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profits": [Decimal("110")],
                    "timeframe": "1h",
                    "timestamp": timestamp,
                },
            ],
            candles=[
                make_candle(
                    Decimal("100"),
                    Decimal("115"),  # Hits TP
                    Decimal("98"),
                    Decimal("112"),
                    timestamp,
                ),
            ],
        )

        result = await compare_captain_vs_internal_outcomes(
            adapter,
            source="captain",
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 1, 2, tzinfo=UTC),
        )

        assert result.captain_count == 1
        assert result.internal_count == 0
        assert result.matched_count == 0
        assert len(result.comparisons) == 1
        assert result.comparisons[0].captain_outcome is not None
        assert result.comparisons[0].captain_outcome.outcome == "TP_FULL"

    @pytest.mark.asyncio
    async def test_evaluates_both_captain_and_internal(self) -> None:
        """Both Captain and Internal outcomes evaluated when matched."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        internal_id = "11111111-1111-1111-1111-111111111111"

        adapter = _FakeComparisonAdapter(
            validations=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "internal_kind": "trading_decision",
                    "internal_id": internal_id,
                    "internal_timestamp": timestamp + timedelta(minutes=5),
                },
            ],
            signals=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profits": [Decimal("110")],
                    "timeframe": "1h",
                    "timestamp": timestamp,
                },
            ],
            candles=[
                make_candle(
                    Decimal("100"),
                    Decimal("115"),  # Hits TP
                    Decimal("98"),
                    Decimal("112"),
                    timestamp,
                ),
            ],
            decisions={
                internal_id: {
                    "id": internal_id,
                    "action": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profit": Decimal("110"),
                },
            },
        )

        result = await compare_captain_vs_internal_outcomes(
            adapter,
            source="captain",
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 1, 2, tzinfo=UTC),
        )

        assert result.captain_count == 1
        assert result.internal_count == 1
        assert result.matched_count == 1
        assert len(result.comparisons) == 1

        comparison = result.comparisons[0]
        assert comparison.captain_outcome is not None
        assert comparison.internal_outcome is not None
        assert comparison.outcome_match is True  # Both TP_FULL

    @pytest.mark.asyncio
    async def test_computes_pnl_delta(self) -> None:
        """PnL delta computed as internal - captain."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        internal_id = "22222222-2222-2222-2222-222222222222"

        # Captain: entry 100, TP 110 (profit ~10)
        # Internal: entry 99, TP 110 (profit ~11, better entry)
        adapter = _FakeComparisonAdapter(
            validations=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "internal_kind": "trading_decision",
                    "internal_id": internal_id,
                    "internal_timestamp": timestamp,
                },
            ],
            signals=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profits": [Decimal("110")],
                    "timeframe": "1h",
                    "timestamp": timestamp,
                },
            ],
            candles=[
                make_candle(
                    Decimal("100"),
                    Decimal("115"),
                    Decimal("98"),
                    Decimal("112"),
                    timestamp,
                ),
            ],
            decisions={
                internal_id: {
                    "id": internal_id,
                    "action": "BUY",
                    "entry_price": Decimal("99"),  # Better entry
                    "stop_loss": Decimal("89"),
                    "take_profit": Decimal("110"),
                },
            },
        )

        result = await compare_captain_vs_internal_outcomes(
            adapter,
            source="captain",
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 1, 2, tzinfo=UTC),
            cost_config=CostConfig(
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
                funding_rate_8h=Decimal("0"),
            ),
        )

        assert len(result.comparisons) == 1
        comparison = result.comparisons[0]
        assert comparison.pnl_delta is not None
        # Internal should have better PnL (entered at 99, exited at 110)
        assert comparison.pnl_delta > Decimal("0")

    @pytest.mark.asyncio
    async def test_computes_timing_delta(self) -> None:
        """Timing delta computed as internal_timestamp - captain_timestamp."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
        internal_id = "33333333-3333-3333-3333-333333333333"

        adapter = _FakeComparisonAdapter(
            validations=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "internal_kind": "trading_decision",
                    "internal_id": internal_id,
                    "internal_timestamp": timestamp + timedelta(minutes=5),  # 300 seconds later
                },
            ],
            signals=[
                {
                    "chat_id": 123,
                    "message_id": 456,
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profits": [Decimal("110")],
                    "timeframe": "1h",
                    "timestamp": timestamp,
                },
            ],
            candles=[
                make_candle(
                    Decimal("100"),
                    Decimal("115"),
                    Decimal("98"),
                    Decimal("112"),
                    timestamp,
                ),
            ],
            decisions={
                internal_id: {
                    "id": internal_id,
                    "action": "BUY",
                    "entry_price": Decimal("100"),
                    "stop_loss": Decimal("90"),
                    "take_profit": Decimal("110"),
                },
            },
        )

        result = await compare_captain_vs_internal_outcomes(
            adapter,
            source="captain",
            start_time=datetime(2025, 1, 1, tzinfo=UTC),
            end_time=datetime(2025, 1, 2, tzinfo=UTC),
        )

        # Internal was 300 seconds (5 min) after Captain
        assert result.timing_delta_seconds == 300.0
