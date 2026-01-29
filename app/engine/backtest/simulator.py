"""
Event-driven backtesting simulator.
Reuses exact same math as live trading system with no lookahead.
"""

from datetime import datetime
from decimal import Decimal
import logging

from ..decision.engine import DecisionEngine
from ..features.indicators import TechnicalIndicatorsCalculator
from ..models import Candle, TechnicalIndicators
from ..smc.engine import SMCEngine
from .costs import CostCalculator
from .fills import FillEngine
from .policies import TradingPolicyManager
from .types import (
    BacktestConfig,
    BacktestOrder,
    BacktestPosition,
    BacktestTrade,
    ExitReason,
    OrderSide,
    OrderStatus,
    OrderType,
)

logger = logging.getLogger(__name__)


class BacktestSimulator:
    """
    Event-driven backtesting simulator that processes candles sequentially
    and reuses the exact same math as live trading.
    """

    def __init__(
        self,
        config: BacktestConfig,
        initial_balance: Decimal = Decimal(10000),
    ):
        """
        Initialize backtest simulator.

        Args:
            config: Backtesting configuration
            initial_balance: Starting capital
        """
        self.config = config
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # Core engines - REUSE SAME MATH AS LIVE
        self.indicators_calc = TechnicalIndicatorsCalculator()
        self.smc_engine = SMCEngine()
        self.decision_engine = DecisionEngine()

        # Backtest-specific engines
        self.fill_engine = FillEngine(config.slippage_bps)
        self.cost_calculator = CostCalculator(
            fee_bps_spot=config.fee_bps_spot,
            funding_model=config.funding_model,
        )
        self.policy_manager = TradingPolicyManager()

        # State tracking
        self.current_time: datetime | None = None
        self.active_orders: list[BacktestOrder] = []
        self.positions: dict[str, BacktestPosition] = {}
        self.completed_trades: list[BacktestTrade] = []
        self.equity_history: list[tuple[datetime, Decimal]] = []
        self.drawdown_history: list[tuple[datetime, Decimal]] = []

        # Performance tracking
        self.peak_balance = initial_balance
        self.total_fees = Decimal(0)
        self.total_slippage = Decimal(0)
        self.total_funding = Decimal(0)

    def process_candle(self, candle: Candle) -> None:
        """
        Process a single candle through the complete trading pipeline.

        Args:
            candle: Market candle to process
        """
        self.current_time = candle.close_time
        symbol = candle.symbol

        logger.debug(f"Processing candle: {symbol} at {candle.close_time}")

        # 1. Update market data and calculate indicators
        indicators = self._calculate_indicators(
            [candle],
        )  # In real backtest, use history
        if not indicators:
            return

        # 2. Process SMC analysis
        self.smc_engine.process_candle(candle)

        # 3. Check and execute fills for existing orders
        self._process_order_fills(candle)

        # 4. Update positions with current prices
        self._update_positions(candle)

        # 5. Process funding (if futures)
        self._process_funding(candle)

        # 6. Check for signal generation
        signal = self._generate_trading_signal(candle, indicators)

        # 7. Apply trading policies and filters
        if signal:
            allowed, reasons = self.policy_manager.is_trading_allowed(
                candle.close_time,
                symbol,
                signal.get("direction"),
                signal.get("regime"),
                indicators,
            )

            if allowed:
                self._execute_signal(signal, candle, indicators)
            else:
                logger.debug(f"Signal blocked: {reasons}")

        # 8. Update equity curve and drawdown
        self._update_equity_curve()

        # 9. Check for position management (TP/SL adjustments)
        self._manage_positions(candle)

    def _calculate_indicators(
        self,
        candles: list[Candle],
    ) -> TechnicalIndicators | None:
        """
        Calculate technical indicators using the same calculator as live trading.

        Args:
            candles: List of candles for calculation

        Returns:
            Technical indicators or None if insufficient data
        """
        if len(candles) < 50:  # Need enough data for indicators
            return None

        try:
            # Extract price data
            closes = [c.close_price for c in candles]
            highs = [c.high_price for c in candles]
            lows = [c.low_price for c in candles]
            volumes = [c.volume for c in candles]

            # Use the exact same calculation as live
            return self.indicators_calc.calculate_all(
                candles=candles,
                ema_periods=[9, 21, 50],
                rsi_period=14,
                macd_fast=12,
                macd_slow=26,
                macd_signal=9,
                bb_period=20,
                bb_std=2.0,
                atr_period=14,
            )

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return None

    def _process_order_fills(self, candle: Candle) -> None:
        """
        Process fills for active orders based on current candle.

        Args:
            candle: Current market candle
        """
        fills = self.fill_engine.process_order_fills(self.active_orders, candle)

        for fill in fills:
            self._execute_fill(fill, candle)

    def _execute_fill(self, fill, candle: Candle) -> None:
        """
        Execute a fill and update positions.

        Args:
            fill: Fill to execute
            candle: Current candle
        """
        # Find and update the order
        order = next((o for o in self.active_orders if o.id == fill.order_id), None)
        if not order:
            logger.error(f"Order not found for fill: {fill.order_id}")
            return

        # Calculate fees
        fee = self.cost_calculator.calculate_fill_fee(fill)
        fill.fee = fee
        self.total_fees += fee
        self.total_slippage += fill.slippage

        # Update order status
        order.filled_quantity += fill.quantity
        order.remaining_quantity -= fill.quantity
        order.fill_time = fill.fill_time

        if order.remaining_quantity <= Decimal(0):
            order.status = OrderStatus.FILLED
            self.active_orders.remove(order)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        # Update position
        self._update_position_from_fill(fill, candle)

        logger.info(
            f"Fill executed: {fill.symbol} {fill.side} {fill.quantity}@{fill.price}",
        )

    def _update_position_from_fill(self, fill, candle: Candle) -> None:
        """
        Update position based on fill.

        Args:
            fill: Executed fill
            candle: Current candle
        """
        symbol = fill.symbol
        position = self.positions.get(symbol)

        if not position:
            # Create new position
            position = BacktestPosition(
                symbol=symbol,
                opened_at=fill.fill_time,
            )
            self.positions[symbol] = position

        # Update position based on fill
        fill_value = fill.quantity * fill.price

        if fill.side == OrderSide.BUY:
            if position.side == "SHORT":
                # Closing short position
                self._close_position_partially(position, fill.quantity, fill.price)
            else:
                # Opening/adding to long position
                position.side = "LONG"
                old_value = (
                    position.quantity * position.entry_price
                    if position.quantity > 0
                    else Decimal(0)
                )
                new_quantity = position.quantity + fill.quantity
                new_value = old_value + fill_value
                position.entry_price = new_value / new_quantity if new_quantity > 0 else Decimal(0)
                position.quantity = new_quantity

        elif position.side == "LONG":
            # Closing long position
            self._close_position_partially(position, fill.quantity, fill.price)
        else:
            # Opening/adding to short position
            position.side = "SHORT"
            old_value = (
                position.quantity * position.entry_price if position.quantity > 0 else Decimal(0)
            )
            new_quantity = position.quantity + fill.quantity
            new_value = old_value + fill_value
            position.entry_price = new_value / new_quantity if new_quantity > 0 else Decimal(0)
            position.quantity = new_quantity

        position.mark_price = candle.close_price
        position.total_fees += fill.fee

    def _close_position_partially(
        self,
        position: BacktestPosition,
        close_quantity: Decimal,
        close_price: Decimal,
    ) -> None:
        """
        Partially or fully close a position.

        Args:
            position: Position to close
            close_quantity: Quantity to close
            close_price: Price to close at
        """
        if close_quantity >= position.quantity:
            # Full close
            pnl = self._calculate_position_pnl(position, close_price)
            position.realized_pnl += pnl
            self.current_balance += pnl

            # Create completed trade record
            self._record_completed_trade(position, close_price)

            # Reset position
            position.quantity = Decimal(0)
            position.side = None
        else:
            # Partial close
            close_ratio = close_quantity / position.quantity
            partial_pnl = self._calculate_position_pnl(position, close_price) * close_ratio
            position.realized_pnl += partial_pnl
            position.quantity -= close_quantity
            self.current_balance += partial_pnl

    def _calculate_position_pnl(
        self,
        position: BacktestPosition,
        current_price: Decimal,
    ) -> Decimal:
        """
        Calculate position PnL at current price.

        Args:
            position: Position to calculate PnL for
            current_price: Current market price

        Returns:
            PnL amount
        """
        if position.quantity == Decimal(0) or not position.side:
            return Decimal(0)

        price_diff = current_price - position.entry_price

        if position.side == "LONG":
            return position.quantity * price_diff
        # SHORT
        return position.quantity * -price_diff

    def _update_positions(self, candle: Candle) -> None:
        """
        Update all positions with current market prices.

        Args:
            candle: Current market candle
        """
        for symbol, position in self.positions.items():
            if symbol == candle.symbol:
                position.mark_price = candle.close_price
                position.unrealized_pnl = self._calculate_position_pnl(
                    position,
                    candle.close_price,
                )

    def _process_funding(self, candle: Candle) -> None:
        """
        Process funding payments for futures positions.

        Args:
            candle: Current candle
        """
        # Skip if funding is disabled
        if self.config.funding_model == "disabled":
            return

        for symbol, position in self.positions.items():
            if position.quantity == Decimal(0) or not position.side:
                continue

            if not position.opened_at:
                continue

            # Check if funding should be charged
            if self.cost_calculator.should_charge_funding(
                candle.close_time,
                position.opened_at,
            ):
                funding_rate = self.cost_calculator.get_funding_rate(
                    symbol,
                    candle.close_time,
                )
                funding_payment = self.cost_calculator.calculate_funding_payment(
                    position.quantity,
                    position.side,
                    position.mark_price,
                    funding_rate,
                )

                position.total_funding += funding_payment
                self.total_funding += funding_payment
                self.current_balance -= funding_payment  # Funding is a cost

                logger.debug(f"Funding payment: {symbol} {funding_payment}")

    def _generate_trading_signal(
        self,
        candle: Candle,
        indicators: TechnicalIndicators,
    ) -> dict | None:
        """
        Generate trading signal using decision engine.

        Args:
            candle: Current candle
            indicators: Technical indicators

        Returns:
            Trading signal or None
        """
        try:
            # This would use the actual decision engine logic
            # For now, return a simple mock signal
            # TODO: Integrate with real decision engine

            return {
                "direction": "long",
                "confidence": Decimal("0.75"),
                "entry_price": candle.close_price,
                "stop_loss": candle.close_price * Decimal("0.98"),
                "take_profits": [
                    {
                        "price": candle.close_price * Decimal("1.015"),
                        "size": Decimal("0.4"),
                    },
                    {
                        "price": candle.close_price * Decimal("1.02"),
                        "size": Decimal("0.3"),
                    },
                    {
                        "price": candle.close_price * Decimal("1.03"),
                        "size": Decimal("0.3"),
                    },
                ],
                "regime": "trending",
            }
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None

    def _execute_signal(
        self,
        signal: dict,
        candle: Candle,
        indicators: TechnicalIndicators,
    ) -> None:
        """
        Execute a trading signal by placing orders.

        Args:
            signal: Trading signal to execute
            candle: Current candle
            indicators: Technical indicators
        """
        symbol = candle.symbol
        direction = signal["direction"]
        entry_price = signal["entry_price"]

        # Calculate position size (simplified)
        risk_per_trade = self.current_balance * Decimal("0.01")  # 1% risk
        stop_distance = abs(entry_price - signal["stop_loss"])
        position_size = risk_per_trade / stop_distance if stop_distance > 0 else Decimal(100)

        # Place entry order
        entry_order = BacktestOrder(
            symbol=symbol,
            side=OrderSide.BUY if direction == "long" else OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=position_size,
            order_time=candle.close_time,
        )

        self.active_orders.append(entry_order)

        logger.info(f"Signal executed: {direction} {symbol} size={position_size}")

    def _update_equity_curve(self) -> None:
        """
        Update equity curve and drawdown tracking.
        """
        if not self.current_time:
            return

        # Calculate current equity
        unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        current_equity = self.current_balance + unrealized_pnl

        # Update equity curve
        self.equity_history.append((self.current_time, current_equity))

        # Update peak and drawdown
        self.peak_balance = max(self.peak_balance, current_equity)

        drawdown = (self.peak_balance - current_equity) / self.peak_balance
        self.drawdown_history.append((self.current_time, drawdown))

    def _manage_positions(self, candle: Candle) -> None:
        """
        Manage existing positions (move to breakeven, trailing stops, etc.).

        Args:
            candle: Current candle
        """
        # TODO: Implement position management logic
        # - Move to breakeven at TP1
        # - Trailing stops after TP2
        # - Partial exits at TP levels

    def _record_completed_trade(
        self,
        position: BacktestPosition,
        exit_price: Decimal,
    ) -> None:
        """
        Record a completed trade.

        Args:
            position: Closed position
            exit_price: Exit price
        """
        if not position.opened_at or not position.side:
            return

        trade = BacktestTrade(
            symbol=position.symbol,
            side=position.side.lower(),
            entry_time=position.opened_at,
            exit_time=self.current_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.quantity,
            fees=position.total_fees,
            funding=position.total_funding,
            exit_reason=ExitReason.MANUAL,  # TODO: Determine actual reason
        )

        # Calculate PnL
        trade.gross_pnl = position.realized_pnl
        trade.net_pnl = trade.gross_pnl - trade.fees - trade.funding

        # Calculate R multiples (risk-reward)
        stop_distance = abs(
            trade.entry_price - (position.stop_loss or trade.entry_price),
        )
        if stop_distance > 0:
            trade.gross_pnl_r = trade.gross_pnl / (stop_distance * trade.size)
            trade.net_pnl_r = trade.net_pnl / (stop_distance * trade.size)

        self.completed_trades.append(trade)

    def get_current_state(self) -> dict:
        """
        Get current simulator state for debugging/monitoring.

        Returns:
            Dictionary with current state
        """
        return {
            "current_time": self.current_time,
            "balance": self.current_balance,
            "positions": len([p for p in self.positions.values() if p.quantity > 0]),
            "active_orders": len(self.active_orders),
            "completed_trades": len(self.completed_trades),
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_funding": self.total_funding,
            "current_equity": self.current_balance
            + sum(p.unrealized_pnl for p in self.positions.values()),
        }
