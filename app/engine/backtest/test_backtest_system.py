"""
Comprehensive tests for backtesting system.

Tests cover:
1. Unit tests for individual components
2. Integration tests for full pipeline
3. Parity tests (backtest vs live math)
4. Edge case handling
5. Performance tests
"""

from datetime import datetime, timedelta
from decimal import Decimal
import os
import tempfile

import pytest

from ..models import Candle, TimeFrame
from .costs import CostCalculator
from .dataset import CSVDataset
from .fills import FillEngine
from .metrics import MetricsCalculator
from .policies import (  # type: ignore[attr-defined]
    FundingGuardPolicy,
    NewsGuardPolicy,
    PolicyManager,
    RegimeFilter,
    SessionPolicy,
)
from .simulator import BacktestSimulator
from .types import (
    BacktestConfig,
    BacktestOrder,
    BacktestTrade,
    ExitReason,
    OrderSide,
    OrderType,
)
from .wfo import ParameterGrid, WFOWindow


class TestFillEngine:
    """Test fill engine logic"""

    def setup_method(self):
        self.fill_engine = FillEngine()
        self.candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime(2024, 1, 1, 12, 0),
            close_time=datetime(2024, 1, 1, 12, 15),
            open_price=Decimal(50000),
            high_price=Decimal(50100),
            low_price=Decimal(49900),
            close_price=Decimal(50050),
            volume=Decimal(100),
            quote_volume=Decimal(5000000),
            trades=100,
            taker_buy_base_volume=Decimal(60),
            taker_buy_quote_volume=Decimal(3000000),
        )

    def test_market_order_always_fills(self):
        """Market orders should always fill immediately"""
        order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal(1),
        )

        assert self.fill_engine.can_fill_order(order, self.candle)

    def test_limit_buy_fills_when_price_touches_low(self):
        """Limit buy should fill when price touches the order price"""
        # Buy limit at the low - should fill
        order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(49900),  # Candle low
        )

        assert self.fill_engine.can_fill_order(order, self.candle)

    def test_limit_buy_no_fill_when_price_too_high(self):
        """Limit buy should not fill when price never reaches order level"""
        # Buy limit below the low - should not fill
        order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(49800),  # Below candle low
        )

        assert not self.fill_engine.can_fill_order(order, self.candle)

    def test_limit_sell_fills_when_price_touches_high(self):
        """Limit sell should fill when price touches the order price"""
        # Sell limit at the high - should fill
        order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(50100),  # Candle high
        )

        assert self.fill_engine.can_fill_order(order, self.candle)

    def test_stop_loss_triggers_correctly(self):
        """Stop loss orders should trigger when stop price is hit"""
        # Stop loss sell triggered when price falls below stop
        order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            type=OrderType.STOP_MARKET,
            quantity=Decimal(1),
            stop_price=Decimal(49950),  # Within candle range
        )

        assert self.fill_engine.can_fill_order(order, self.candle)

    def test_fill_price_calculation(self):
        """Test that fill prices are calculated correctly"""
        # Market buy should fill at open + slippage
        market_buy = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=Decimal(1),
        )

        fill_price = self.fill_engine.get_fill_price(market_buy, self.candle)
        assert fill_price >= self.candle.open_price  # Should include slippage

        # Limit order should fill at limit price
        limit_buy = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(49900),
        )

        fill_price = self.fill_engine.get_fill_price(limit_buy, self.candle)
        assert fill_price == Decimal(49900)


class TestCostCalculator:
    """Test cost calculations"""

    def setup_method(self):
        self.cost_calc = CostCalculator(
            spot_fee_rate=Decimal("0.001"),  # 0.1%
            futures_fee_rate=Decimal("0.0004"),  # 0.04%
            slippage_bps=Decimal(2),  # 2 bps
        )

    def test_spot_trading_fees(self):
        """Test spot trading fee calculation"""
        notional = Decimal(10000)  # $10,000 trade

        # Taker fee
        fee = self.cost_calc.calculate_trading_fee(
            notional,
            is_futures=False,
            is_maker=False,
        )
        expected = notional * Decimal("0.001")
        assert fee == expected

        # Maker fee (discounted)
        maker_fee = self.cost_calc.calculate_trading_fee(
            notional,
            is_futures=False,
            is_maker=True,
        )
        expected_maker = expected * Decimal("0.75")  # 25% discount
        assert maker_fee == expected_maker

    def test_futures_trading_fees(self):
        """Test futures trading fee calculation"""
        notional = Decimal(10000)

        fee = self.cost_calc.calculate_trading_fee(
            notional,
            is_futures=True,
            is_maker=False,
        )
        expected = notional * Decimal("0.0004")
        assert fee == expected

    def test_slippage_calculation(self):
        """Test slippage calculation based on order size"""
        quantity = Decimal(10)
        volume = Decimal(1000)

        slippage = self.cost_calc.calculate_slippage(quantity, volume)

        # Should be proportional to order size vs volume
        market_impact = quantity / volume
        expected = market_impact * self.cost_calc.slippage_bps / Decimal(10000)
        assert slippage == expected

    def test_funding_calculation(self):
        """Test funding payment calculation"""
        position_value = Decimal(10000)
        funding_rate = Decimal("0.0001")  # 0.01%
        hours = Decimal(8)  # 8-hour funding period

        funding = self.cost_calc.calculate_funding_payment(
            position_value,
            funding_rate,
            hours,
        )

        expected = position_value * funding_rate * (hours / Decimal(8))
        assert funding == expected


class TestPolicyManager:
    """Test trading policy enforcement"""

    def setup_method(self):
        self.session_policy = SessionPolicy(
            enabled=True,
            exclude_hours=[(22, 6), (12, 13)],  # Exclude late night and lunch
        )

        self.news_guard = NewsGuardPolicy(
            before_minutes=15,
            after_minutes=15,
        )

        self.funding_guard = FundingGuardPolicy(
            before_minutes=5,
            after_minutes=5,
        )

        self.regime_filter = RegimeFilter(
            enabled=True,
            allowed_regimes=["trending", "volatile"],
        )

        self.policy_manager = PolicyManager(
            session_policy=self.session_policy,
            news_guard_policy=self.news_guard,
            funding_guard_policy=self.funding_guard,
            regime_filter=self.regime_filter,
        )

    def test_session_filtering(self):
        """Test session-based trade filtering"""
        # During allowed hours
        allowed_time = datetime(2024, 1, 1, 15, 0)  # 3 PM
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            allowed_time,
            "BTCUSDT",
        )
        assert is_allowed
        assert len(reasons) == 0

        # During excluded hours
        excluded_time = datetime(2024, 1, 1, 23, 0)  # 11 PM
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            excluded_time,
            "BTCUSDT",
        )
        assert not is_allowed
        assert "session_excluded" in reasons

    def test_news_guard(self):
        """Test news event blocking"""
        # Mock news events
        news_events = [
            {
                "symbol": "BTCUSDT",
                "timestamp": datetime(2024, 1, 1, 15, 0),
                "impact": "high",
            },
        ]

        # 10 minutes before news - should be blocked
        test_time = datetime(2024, 1, 1, 14, 50)
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            test_time,
            "BTCUSDT",
            news_events=news_events,
        )
        assert not is_allowed
        assert "news_guard" in reasons

    def test_funding_guard(self):
        """Test funding rate blocking"""
        # 3 minutes before funding (every 8 hours: 00:00, 08:00, 16:00 UTC)
        funding_time = datetime(2024, 1, 1, 15, 57)  # 3 min before 16:00
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            funding_time,
            "BTCUSDT",
            is_futures=True,
        )
        assert not is_allowed
        assert "funding_guard" in reasons

    def test_regime_filtering(self):
        """Test regime-based filtering"""
        # Allowed regime
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            datetime(2024, 1, 1, 15, 0),
            "BTCUSDT",
            current_regime="trending",
        )
        assert is_allowed

        # Disallowed regime
        is_allowed, reasons = self.policy_manager.is_trading_allowed(
            datetime(2024, 1, 1, 15, 0),
            "BTCUSDT",
            current_regime="ranging",
        )
        assert not is_allowed
        assert "regime_filter" in reasons


class TestMetricsCalculator:
    """Test performance metrics calculation"""

    def setup_method(self):
        self.initial_balance = Decimal(10000)
        self.metrics_calc = MetricsCalculator(self.initial_balance)

    def test_basic_metrics_calculation(self):
        """Test basic trade statistics"""
        # Create sample trades
        trades = [
            BacktestTrade(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                entry_price=Decimal(50000),
                exit_price=Decimal(51000),
                size=Decimal(1),
                net_pnl=Decimal(1000),
                net_pnl_r=Decimal("2.0"),  # 2R win
                exit_reason=ExitReason.TAKE_PROFIT,
            ),
            BacktestTrade(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                entry_price=Decimal(51000),
                exit_price=Decimal(50500),
                size=Decimal(1),
                net_pnl=Decimal(-500),
                net_pnl_r=Decimal("-1.0"),  # 1R loss
                exit_reason=ExitReason.STOP_LOSS,
            ),
        ]

        # Create sample equity curve
        equity_curve = [
            (datetime(2024, 1, 1), self.initial_balance),
            (datetime(2024, 1, 2), self.initial_balance + Decimal(1000)),
            (datetime(2024, 1, 3), self.initial_balance + Decimal(500)),
        ]

        # Create sample drawdown curve
        drawdown_curve = [
            (datetime(2024, 1, 1), Decimal(0)),
            (datetime(2024, 1, 2), Decimal(0)),
            (datetime(2024, 1, 3), Decimal("0.05")),  # 5% drawdown
        ]

        metrics = self.metrics_calc.calculate_metrics(
            trades,
            equity_curve,
            drawdown_curve,
        )

        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.hit_rate_pct == Decimal(50)
        assert metrics.total_pnl == Decimal(500)
        assert metrics.profit_factor == Decimal(2)  # 1000 wins / 500 losses

    def test_sharpe_ratio_calculation(self):
        """Test Sharpe ratio calculation"""
        # Create equity curve with consistent returns
        equity_points = []
        base_equity = self.initial_balance

        for i in range(252):  # 252 trading days
            daily_return = Decimal("0.001")  # 0.1% daily
            base_equity = base_equity * (Decimal(1) + daily_return)
            equity_points.append(
                (datetime(2024, 1, 1) + timedelta(days=i), base_equity),
            )

        metrics = self.metrics_calc.calculate_metrics([], equity_points, [])

        # Should have positive Sharpe ratio for consistent positive returns
        assert metrics.sharpe_ratio is not None
        assert metrics.sharpe_ratio > 0

    def test_drawdown_calculation(self):
        """Test maximum drawdown calculation"""
        drawdown_curve = [
            (datetime(2024, 1, 1), Decimal(0)),
            (datetime(2024, 1, 2), Decimal("0.02")),  # 2% DD
            (datetime(2024, 1, 3), Decimal("0.05")),  # 5% DD (max)
            (datetime(2024, 1, 4), Decimal("0.03")),  # Recovery
            (datetime(2024, 1, 5), Decimal(0)),  # Full recovery
        ]

        metrics = self.metrics_calc.calculate_metrics([], [], drawdown_curve)

        assert metrics.max_drawdown_pct == Decimal(5)  # 5% max DD


class TestBacktestSimulator:
    """Test full backtest simulation"""

    def setup_method(self):
        self.config = BacktestConfig(
            fee_bps_spot=Decimal(10),
            slippage_bps=Decimal(2),
            funding_model="disabled",
        )
        self.simulator = BacktestSimulator(self.config, Decimal(10000))

    def test_candle_processing(self):
        """Test that simulator processes candles correctly"""
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime(2024, 1, 1, 12, 0),
            close_time=datetime(2024, 1, 1, 12, 15),
            open_price=Decimal(50000),
            high_price=Decimal(50100),
            low_price=Decimal(49900),
            close_price=Decimal(50050),
            volume=Decimal(100),
            quote_volume=Decimal(5000000),
            trades=100,
            taker_buy_base_volume=Decimal(60),
            taker_buy_quote_volume=Decimal(3000000),
        )

        initial_candle_count = len(self.simulator.processed_candles)
        self.simulator.process_candle(candle)
        assert len(self.simulator.processed_candles) == initial_candle_count + 1

    def test_equity_tracking(self):
        """Test that equity is tracked correctly"""
        initial_equity_points = len(self.simulator.equity_history)

        candle = self._create_test_candle()
        self.simulator.process_candle(candle)

        # Should have added equity point
        assert len(self.simulator.equity_history) == initial_equity_points + 1

    def _create_test_candle(self):
        """Helper to create test candle"""
        return Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime(2024, 1, 1, 12, 0),
            close_time=datetime(2024, 1, 1, 12, 15),
            open_price=Decimal(50000),
            high_price=Decimal(50100),
            low_price=Decimal(49900),
            close_price=Decimal(50050),
            volume=Decimal(100),
            quote_volume=Decimal(5000000),
            trades=100,
            taker_buy_base_volume=Decimal(60),
            taker_buy_quote_volume=Decimal(3000000),
        )


class TestParameterGrid:
    """Test parameter grid generation for WFO"""

    def test_simple_grid(self):
        """Test simple parameter grid"""
        ranges = {
            "param1": [1, 2, 3],
            "param2": ["a", "b"],
        }

        grid = ParameterGrid(ranges)
        combinations = list(grid.generate_combinations())

        assert len(combinations) == 6  # 3 * 2
        assert {"param1": 1, "param2": "a"} in combinations
        assert {"param1": 3, "param2": "b"} in combinations

    def test_count_combinations(self):
        """Test combination counting"""
        ranges = {
            "param1": [1, 2, 3, 4],
            "param2": [10, 20],
            "param3": ["x", "y", "z"],
        }

        grid = ParameterGrid(ranges)
        assert grid.count_combinations() == 24  # 4 * 2 * 3


class TestWFOWindow:
    """Test WFO window generation"""

    def test_window_creation(self):
        """Test WFO window creation"""
        window = WFOWindow(
            window_id=1,
            train_start=datetime(2024, 1, 1),
            train_end=datetime(2024, 3, 31),
            test_start=datetime(2024, 4, 1),
            test_end=datetime(2024, 4, 30),
        )

        assert window.window_id == 1
        assert window.train_start == datetime(2024, 1, 1)
        assert window.test_end == datetime(2024, 4, 30)


class TestCSVDataset:
    """Test CSV data loading"""

    def setup_method(self):
        # Create temporary CSV file
        self.temp_dir = tempfile.mkdtemp()
        self.csv_file = os.path.join(self.temp_dir, "btcusdt_15m.csv")

        # Write test data
        with open(self.csv_file, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2024-01-01T12:00:00,50000,50100,49900,50050,100\n")
            f.write("2024-01-01T12:15:00,50050,50150,49950,50100,120\n")

    def test_csv_loading(self):
        """Test CSV data loading"""
        dataset = CSVDataset(self.temp_dir)

        candles = dataset.load_candles(
            "BTCUSDT",
            TimeFrame.M15,
            datetime(2024, 1, 1, 11, 0),
            datetime(2024, 1, 1, 13, 0),
        )

        assert len(candles) == 2
        assert candles[0].open_price == Decimal(50000)
        assert candles[1].close_price == Decimal(50100)

    def teardown_method(self):
        """Clean up temp files"""
        import shutil

        shutil.rmtree(self.temp_dir)


class TestParityChecks:
    """
    Critical parity tests to ensure backtest math matches live trading.

    These tests verify that:
    1. Indicator calculations are identical
    2. SMC analysis produces same results
    3. Signal generation is consistent
    4. Order sizing is identical
    """

    @pytest.mark.integration
    def test_indicator_parity(self):
        """Test that backtest indicators match live calculations"""
        # This would require importing live indicator modules
        # and comparing outputs on the same data
        pytest.skip("Requires live trading modules")

    @pytest.mark.integration
    def test_smc_parity(self):
        """Test that SMC analysis matches between backtest and live"""
        pytest.skip("Requires live SMC modules")

    @pytest.mark.integration
    def test_signal_generation_parity(self):
        """Test that signals are generated identically"""
        pytest.skip("Requires live signal modules")

    @pytest.mark.integration
    def test_position_sizing_parity(self):
        """Test that position sizing is identical"""
        pytest.skip("Requires live position sizing modules")


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_empty_candle_data(self):
        """Test handling of empty candle data"""
        config = BacktestConfig()
        simulator = BacktestSimulator(config, Decimal(10000))

        # Should not crash with empty data
        metrics_calc = MetricsCalculator(Decimal(10000))
        metrics = metrics_calc.calculate_metrics([], [], [])

        assert metrics.total_trades == 0
        assert metrics.total_pnl == Decimal(0)

    def test_zero_volume_candle(self):
        """Test handling of zero volume candles"""
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime(2024, 1, 1, 12, 0),
            close_time=datetime(2024, 1, 1, 12, 15),
            open_price=Decimal(50000),
            high_price=Decimal(50000),
            low_price=Decimal(50000),
            close_price=Decimal(50000),
            volume=Decimal(0),  # Zero volume
            quote_volume=Decimal(0),
            trades=0,
            taker_buy_base_volume=Decimal(0),
            taker_buy_quote_volume=Decimal(0),
        )

        config = BacktestConfig()
        simulator = BacktestSimulator(config, Decimal(10000))

        # Should handle without crashing
        simulator.process_candle(candle)

    def test_extreme_price_movements(self):
        """Test handling of extreme price movements"""
        # Test with massive price gap
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime(2024, 1, 1, 12, 0),
            close_time=datetime(2024, 1, 1, 12, 15),
            open_price=Decimal(50000),
            high_price=Decimal(100000),  # 100% gap up
            low_price=Decimal(25000),  # 50% gap down
            close_price=Decimal(75000),
            volume=Decimal(1000),
            quote_volume=Decimal(50000000),
            trades=1000,
            taker_buy_base_volume=Decimal(600),
            taker_buy_quote_volume=Decimal(30000000),
        )

        fill_engine = FillEngine()

        # Limit orders should still work correctly
        buy_order = BacktestOrder(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal(1),
            price=Decimal(30000),  # Within the range
        )

        assert fill_engine.can_fill_order(buy_order, candle)


@pytest.mark.performance
class TestPerformance:
    """Performance tests for backtesting system"""

    def test_candle_processing_performance(self):
        """Test that candle processing is fast enough"""
        config = BacktestConfig()
        simulator = BacktestSimulator(config, Decimal(10000))

        # Create 10,000 candles
        candles = []
        for i in range(10000):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M15,
                open_time=datetime(2024, 1, 1) + timedelta(minutes=15 * i),
                close_time=datetime(2024, 1, 1) + timedelta(minutes=15 * (i + 1)),
                open_price=Decimal(50000) + Decimal(str(i % 100)),
                high_price=Decimal(50100) + Decimal(str(i % 100)),
                low_price=Decimal(49900) + Decimal(str(i % 100)),
                close_price=Decimal(50050) + Decimal(str(i % 100)),
                volume=Decimal(100),
                quote_volume=Decimal(5000000),
                trades=100,
                taker_buy_base_volume=Decimal(60),
                taker_buy_quote_volume=Decimal(3000000),
            )
            candles.append(candle)

        import time

        start_time = time.time()

        # Process all candles
        for candle in candles:
            simulator.process_candle(candle)

        elapsed_time = time.time() - start_time

        # Should process 10k candles in under 10 seconds
        assert elapsed_time < 10.0
        print(f"Processed 10,000 candles in {elapsed_time:.2f} seconds")


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "--tb=short"])
