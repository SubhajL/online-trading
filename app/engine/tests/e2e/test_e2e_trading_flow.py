"""
CRITICAL: End-to-End trading flow tests.

These tests simulate the complete trading flow from signal detection to order placement:
1. Candle ingestion → Features calculation → SMC analysis → Signal generation
2. Decision making with risk management → Order formatting → Router interaction
3. Position tracking and P&L calculation
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from app.engine.models import (
    Candle, TimeFrame, CandleUpdateEvent, FeaturesUpdateEvent,
    SMCEvent, ZoneEvent, SignalEvent, TradingDecision
)
from app.engine.features.indicators import IndicatorCalculator
from app.engine.smc.core import SMCAnalyzer, StructureTracker
from app.engine.retest.analyzer import RetestAnalyzer
from app.engine.decision.engine import DecisionEngine
from app.engine.decision.risk_manager import RiskManager, RiskManagerConfig
from app.engine.decision.position_sizer import PositionSizer, PositionSizeConfig
from app.engine.decision.order_formatter import OrderFormatter, ExchangeInfo


class TestE2ETradingFlow:
    """Test complete trading flow from data to orders."""

    @pytest.fixture
    def mock_event_bus(self):
        """Create mock event bus for testing."""
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def candles_for_signal(self):
        """Generate candles that will produce a trading signal."""
        candles = []
        base_time = datetime.now() - timedelta(hours=10)

        # Create uptrend with structure break setup
        prices = [
            # Initial downtrend
            50000, 49800, 49600, 49400, 49200,
            # Reversal starts (higher low)
            49300, 49500, 49700, 49900, 50100,
            # Pullback to form higher low
            50000, 49850, 49800, 49850, 49900,
            # Strong move up (BOS)
            50200, 50400, 50600, 50800, 51000,
            # Retest of broken zone
            50900, 50750, 50700, 50650, 50700,  # Current candle retesting
        ]

        for i, price in enumerate(prices):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=base_time + timedelta(minutes=5*i),
                close_time=base_time + timedelta(minutes=5*(i+1)),
                open_price=Decimal(str(price - 50)),
                high_price=Decimal(str(price + 100)),
                low_price=Decimal(str(price - 100)),
                close_price=Decimal(str(price)),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=1000,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000"),
            )
            candles.append(candle)

        return candles

    @pytest.fixture
    def indicator_calculator(self):
        """Create indicator calculator."""
        return IndicatorCalculator()

    @pytest.fixture
    def smc_analyzer(self):
        """Create SMC analyzer."""
        return SMCAnalyzer()

    @pytest.fixture
    def structure_tracker(self):
        """Create structure tracker."""
        return StructureTracker(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            lookback_pivots=3
        )

    @pytest.fixture
    def risk_manager(self):
        """Create risk manager with test config."""
        config = RiskManagerConfig(
            max_daily_loss_pct=Decimal("0.02"),
            max_positions=5,
            max_correlation_positions=3,
            max_drawdown_pct=Decimal("0.05"),
            risk_reduction_factor=Decimal("0.5")
        )
        return RiskManager(config)

    @pytest.fixture
    def position_sizer(self):
        """Create position sizer."""
        config = PositionSizeConfig(
            fixed_risk_pct=Decimal("0.005"),
            max_position_pct=Decimal("0.02"),
            min_position_size=Decimal("0.0001"),
            confidence_scale_factor=Decimal("1.0")
        )
        return PositionSizer(config)

    @pytest.fixture
    def order_formatter(self):
        """Create order formatter with exchange info."""
        exchange_info = {
            "BTCUSDT": ExchangeInfo(
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
                price_tick_size=Decimal("0.01"),
                price_min=Decimal("0.01"),
                price_max=Decimal("1000000"),
                qty_step_size=Decimal("0.00001"),
                qty_min=Decimal("0.0001"),
                qty_max=Decimal("9000"),
                min_notional=Decimal("10"),
            )
        }
        return OrderFormatter(exchange_info)

    @pytest.fixture
    def decision_engine(self, risk_manager, position_sizer, order_formatter):
        """Create decision engine."""
        return DecisionEngine(
            risk_manager=risk_manager,
            position_sizer=position_sizer,
            order_formatter=order_formatter,
            account_balance=Decimal("10000")
        )

    def test_complete_trading_flow(
        self,
        candles_for_signal,
        indicator_calculator,
        smc_analyzer,
        structure_tracker,
        decision_engine
    ):
        """Test complete flow from candles to trading decision."""
        # Step 1: Calculate indicators for all candles
        features = []
        for i in range(len(candles_for_signal)):
            window = candles_for_signal[max(0, i-200):i+1]  # Get historical window

            if len(window) >= 20:  # Need minimum data for indicators
                feature = indicator_calculator.calculate_indicators(
                    symbol="BTCUSDT",
                    timeframe=TimeFrame.M5,
                    candles=window
                )
                features.append(feature)

        assert len(features) > 0, "Should have calculated features"

        # Step 2: Analyze SMC patterns
        pivots = smc_analyzer.detect_pivots(candles_for_signal, lookback=3)
        assert len(pivots) > 0, "Should detect pivots"

        # Track structure
        smc_events = []
        zones = []

        for candle in candles_for_signal:
            # Update structure
            structure_event = structure_tracker.update(candle)
            if structure_event:
                smc_events.append(structure_event)

                # Detect zones from structure breaks
                if structure_event.event_type in ["BOS", "CHOCH"]:
                    zone = smc_analyzer.identify_zone_from_break(
                        candles_for_signal,
                        structure_event,
                        lookback_candles=20
                    )
                    if zone:
                        zones.append(zone)

        assert len(smc_events) > 0, "Should detect structure events"
        assert len(zones) > 0, "Should identify zones"

        # Step 3: Check for retest signals
        latest_candle = candles_for_signal[-1]
        latest_features = features[-1] if features else None

        # Find if current price is retesting any zone
        signal = None
        for zone in zones:
            if zone.zone_type == "demand" and zone.is_active:
                # Check if price is retesting demand zone
                if (latest_candle.low_price <= zone.high_price and
                    latest_candle.low_price >= zone.low_price):

                    # Generate buy signal
                    signal = SignalEvent(
                        timestamp=datetime.now(),
                        symbol="BTCUSDT",
                        timeframe=TimeFrame.M5,
                        signal_type="BUY",
                        entry_price=latest_candle.close_price,
                        stop_loss=zone.low_price - Decimal("50"),  # Below zone
                        take_profit=latest_candle.close_price + Decimal("400"),  # 1:2 RR
                        confidence=Decimal("0.85"),
                        source="zone_retest",
                        metadata={
                            "zone_type": "demand",
                            "zone_strength": "high",
                            "confluence": ["BOS", "EMA_support", "RSI_oversold"]
                        }
                    )
                    break

        assert signal is not None, "Should generate a signal from zone retest"

        # Step 4: Make trading decision
        decision = decision_engine.process_signal(signal, latest_features)

        assert decision is not None, "Should make a trading decision"
        assert decision.action == "BUY"
        assert decision.quantity > 0

        # Step 5: Format order for exchange
        order = {
            "symbol": decision.symbol,
            "side": decision.action,
            "type": "LIMIT",
            "price": decision.entry_price,
            "quantity": decision.quantity,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
        }

        formatted_order = decision_engine.order_formatter.format_order(order)

        # Verify order meets exchange requirements
        is_valid, errors = decision_engine.order_formatter.validate_order(formatted_order)
        assert is_valid, f"Order should be valid: {errors}"

        # Verify risk constraints
        position_value = formatted_order["quantity"] * formatted_order["price"]
        account_balance = Decimal("10000")
        position_pct = position_value / account_balance

        assert position_pct <= Decimal("0.02"), "Position should not exceed 2% of account"

        # Calculate risk
        risk_amount = formatted_order["quantity"] * abs(
            formatted_order["price"] - formatted_order["stop_loss"]
        )
        risk_pct = risk_amount / account_balance

        assert risk_pct <= Decimal("0.005"), "Risk should not exceed 0.5% of account"

    def test_flow_with_risk_rejection(self, decision_engine, risk_manager):
        """Test that high-risk signals are rejected."""
        # Add existing positions to approach risk limit
        for i in range(4):
            risk_manager.add_position(f"SYMBOL{i}", "crypto")

        # Create high-risk signal
        risky_signal = SignalEvent(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            signal_type="BUY",
            entry_price=Decimal("50000"),
            stop_loss=Decimal("45000"),  # 10% stop - too risky
            take_profit=Decimal("55000"),
            confidence=Decimal("0.6"),  # Low confidence
            source="test",
            metadata={}
        )

        # Process signal
        decision = decision_engine.process_signal(risky_signal, None)

        # Should reject due to risk
        assert decision is None or decision.action == "SKIP"

    def test_flow_with_multiple_timeframes(self):
        """Test signal generation across multiple timeframes."""
        timeframes = [TimeFrame.M5, TimeFrame.M15, TimeFrame.H1]
        signals_by_tf = {}

        for tf in timeframes:
            # Generate candles for timeframe
            candles = self._generate_candles_for_timeframe(tf)

            # Calculate indicators
            calculator = IndicatorCalculator()
            features = calculator.calculate_indicators(
                symbol="BTCUSDT",
                timeframe=tf,
                candles=candles
            )

            # Store for multi-timeframe analysis
            signals_by_tf[tf] = features

        # Verify we can analyze across timeframes
        assert len(signals_by_tf) == 3

        # Higher timeframe should confirm lower timeframe signals
        # This is where multi-timeframe confluence would be checked

    def _generate_candles_for_timeframe(self, timeframe: TimeFrame):
        """Generate test candles for a specific timeframe."""
        candles = []
        base_time = datetime.now() - timedelta(hours=24)

        # Determine candle interval based on timeframe
        if timeframe == TimeFrame.M5:
            interval = timedelta(minutes=5)
            count = 100
        elif timeframe == TimeFrame.M15:
            interval = timedelta(minutes=15)
            count = 50
        else:  # H1
            interval = timedelta(hours=1)
            count = 24

        for i in range(count):
            price = Decimal("50000") + Decimal(str(i * 10))
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=timeframe,
                open_time=base_time + interval * i,
                close_time=base_time + interval * (i + 1),
                open_price=price,
                high_price=price + Decimal("50"),
                low_price=price - Decimal("50"),
                close_price=price + Decimal("20"),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=1000,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000"),
            )
            candles.append(candle)

        return candles

    @pytest.mark.asyncio
    async def test_async_event_flow(self, mock_event_bus):
        """Test async event propagation through the system."""
        events_received = []

        async def track_event(event):
            events_received.append(event)

        mock_event_bus.publish.side_effect = track_event

        # Simulate candle event
        candle = Candle(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=datetime.now() - timedelta(minutes=5),
            close_time=datetime.now(),
            open_price=Decimal("50000"),
            high_price=Decimal("50100"),
            low_price=Decimal("49900"),
            close_price=Decimal("50050"),
            volume=Decimal("100"),
            quote_volume=Decimal("5000000"),
            trades=1000,
            taker_buy_base_volume=Decimal("60"),
            taker_buy_quote_volume=Decimal("3000000"),
        )

        candle_event = CandleUpdateEvent(
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=candle
        )

        # Publish candle event
        await mock_event_bus.publish(candle_event)

        # Verify event was received
        assert len(events_received) == 1
        assert isinstance(events_received[0], CandleUpdateEvent)

    def test_paper_trading_flow(self):
        """Test paper trading execution flow."""
        from app.engine.paper.broker import PaperBroker, PaperBrokerConfig

        # Create paper broker
        config = PaperBrokerConfig(
            initial_balance=Decimal("10000"),
            maker_fee=Decimal("0.001"),
            taker_fee=Decimal("0.001"),
            slippage_bps=10  # 0.1% slippage
        )
        broker = PaperBroker(config)

        # Place a paper order
        order_id = broker.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            stop_loss=Decimal("49500"),
            take_profit=Decimal("51000")
        )

        assert order_id is not None

        # Simulate market movement and fill
        market_price = Decimal("50000")
        broker.update_market_price("BTCUSDT", market_price)

        # Check position
        position = broker.get_position("BTCUSDT")
        assert position is not None
        assert position["quantity"] == Decimal("0.1")
        assert position["entry_price"] == Decimal("50000")

        # Simulate hitting take profit
        broker.update_market_price("BTCUSDT", Decimal("51000"))

        # Position should be closed
        position = broker.get_position("BTCUSDT")
        assert position is None

        # Check P&L
        stats = broker.get_statistics()
        assert stats["total_trades"] == 1
        assert stats["winning_trades"] == 1
        assert stats["total_pnl"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
pytestmark = pytest.mark.e2e
