"""
Risk Manager

Comprehensive risk management system for trading decisions.
Implements position sizing, risk limits, correlation checks, and drawdown controls.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from ..types import (
    TradingDecision, Position, RiskParameters, PositionSizing,
    OrderSide, Candle, TechnicalIndicators
)


logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class RiskCheckResult:
    """Result of risk check with detailed information"""

    def __init__(self, approved: bool, risk_level: RiskLevel, checks: Dict[str, bool], reasons: List[str]):
        self.approved = approved
        self.risk_level = risk_level
        self.checks = checks
        self.reasons = reasons
        self.timestamp = datetime.utcnow()


class RiskManager:
    """
    Comprehensive risk management system.

    Features:
    - Position sizing calculations
    - Maximum loss limits
    - Drawdown monitoring
    - Correlation analysis
    - Volatility-based risk adjustment
    - Time-based risk controls
    """

    def __init__(self, risk_parameters: RiskParameters):
        self.risk_params = risk_parameters

        # Track positions and P&L
        self._positions: Dict[str, Position] = {}
        self._daily_pnl: Dict[str, Decimal] = {}  # date -> pnl
        self._trade_history: List[Dict] = []

        # Risk metrics
        self._max_drawdown = Decimal('0')
        self._peak_balance = Decimal('0')
        self._current_balance = Decimal('100000')  # Default starting balance

        # Correlation tracking
        self._symbol_correlations: Dict[Tuple[str, str], Decimal] = {}

        logger.info("RiskManager initialized with comprehensive risk controls")

    def calculate_position_size(
        self,
        decision: TradingDecision,
        account_balance: Decimal,
        current_price: Decimal
    ) -> PositionSizing:
        """
        Calculate position size based on risk parameters

        Args:
            decision: Trading decision
            account_balance: Current account balance
            current_price: Current market price

        Returns:
            PositionSizing object with calculated values
        """
        try:
            # Risk amount (percentage of account)
            risk_amount = account_balance * self.risk_params.risk_per_trade

            # Calculate position size based on stop loss distance
            if decision.stop_loss:
                if decision.action == "BUY":
                    stop_distance = abs(current_price - decision.stop_loss)
                else:  # SELL
                    stop_distance = abs(decision.stop_loss - current_price)

                if stop_distance > 0:
                    position_size = risk_amount / stop_distance
                else:
                    # Default to small position if no stop loss distance
                    position_size = risk_amount / (current_price * Decimal('0.02'))  # 2% default risk
            else:
                # Default position sizing without stop loss
                position_size = risk_amount / (current_price * Decimal('0.02'))

            # Apply maximum position size limit
            max_position_value = account_balance * self.risk_params.max_position_size
            max_quantity = max_position_value / current_price

            if position_size > max_quantity:
                position_size = max_quantity

            # Calculate margin requirements (assuming 1:1 leverage by default)
            leverage = Decimal('1')
            margin_required = (position_size * current_price) / leverage

            return PositionSizing(
                symbol=decision.symbol,
                entry_price=current_price,
                stop_loss=decision.stop_loss or Decimal('0'),
                risk_amount=risk_amount,
                position_size=position_size,
                leverage=leverage,
                margin_required=margin_required
            )

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            # Return minimal position size on error
            return PositionSizing(
                symbol=decision.symbol,
                entry_price=current_price,
                stop_loss=decision.stop_loss or Decimal('0'),
                risk_amount=account_balance * Decimal('0.01'),  # 1% default
                position_size=Decimal('0.001'),
                leverage=Decimal('1'),
                margin_required=Decimal('100')
            )

    def check_risk_limits(
        self,
        decision: TradingDecision,
        account_balance: Decimal,
        current_positions: List[Position]
    ) -> RiskCheckResult:
        """
        Comprehensive risk check for trading decision

        Args:
            decision: Trading decision to evaluate
            account_balance: Current account balance
            current_positions: List of current positions

        Returns:
            RiskCheckResult with approval status and details
        """
        checks = {}
        reasons = []
        risk_level = RiskLevel.LOW

        try:
            # Check 1: Daily loss limit
            today = datetime.utcnow().date().isoformat()
            daily_pnl = self._daily_pnl.get(today, Decimal('0'))
            max_daily_loss = account_balance * self.risk_params.max_daily_loss

            if abs(daily_pnl) >= max_daily_loss:
                checks['daily_loss_limit'] = False
                reasons.append(f"Daily loss limit exceeded: {daily_pnl}")
                risk_level = RiskLevel.EXTREME
            else:
                checks['daily_loss_limit'] = True

            # Check 2: Maximum drawdown
            current_drawdown = self._calculate_current_drawdown(account_balance)
            max_allowed_drawdown = self.risk_params.max_drawdown

            if current_drawdown >= max_allowed_drawdown:
                checks['max_drawdown'] = False
                reasons.append(f"Maximum drawdown exceeded: {current_drawdown * 100:.2f}%")
                risk_level = RiskLevel.EXTREME
            else:
                checks['max_drawdown'] = True
                if current_drawdown > max_allowed_drawdown * Decimal('0.8'):
                    risk_level = max(risk_level, RiskLevel.HIGH)

            # Check 3: Maximum open positions
            if len(current_positions) >= self.risk_params.max_open_positions:
                checks['max_positions'] = False
                reasons.append(f"Maximum open positions limit reached: {len(current_positions)}")
                risk_level = max(risk_level, RiskLevel.HIGH)
            else:
                checks['max_positions'] = True

            # Check 4: Symbol whitelist
            if self.risk_params.allowed_symbols and decision.symbol not in self.risk_params.allowed_symbols:
                checks['symbol_allowed'] = False
                reasons.append(f"Symbol {decision.symbol} not in allowed list")
                risk_level = max(risk_level, RiskLevel.MEDIUM)
            else:
                checks['symbol_allowed'] = True

            # Check 5: Position size limits
            if decision.position_sizing:
                position_value = decision.position_sizing.position_size * decision.position_sizing.entry_price
                max_position_value = account_balance * self.risk_params.max_position_size

                if position_value > max_position_value:
                    checks['position_size'] = False
                    reasons.append(f"Position size too large: {position_value} > {max_position_value}")
                    risk_level = max(risk_level, RiskLevel.HIGH)
                else:
                    checks['position_size'] = True
            else:
                checks['position_size'] = True

            # Check 6: Correlation limits
            correlation_risk = self._check_correlation_risk(decision.symbol, current_positions)
            if correlation_risk > self.risk_params.max_correlation:
                checks['correlation'] = False
                reasons.append(f"High correlation risk: {correlation_risk}")
                risk_level = max(risk_level, RiskLevel.MEDIUM)
            else:
                checks['correlation'] = True

            # Check 7: Trading hours (if specified)
            if self.risk_params.trading_hours:
                current_hour = datetime.utcnow().hour
                allowed_hours = self.risk_params.trading_hours.get('allowed_hours', [])

                if allowed_hours and current_hour not in allowed_hours:
                    checks['trading_hours'] = False
                    reasons.append(f"Trading outside allowed hours: {current_hour}")
                    risk_level = max(risk_level, RiskLevel.MEDIUM)
                else:
                    checks['trading_hours'] = True
            else:
                checks['trading_hours'] = True

            # Check 8: Confidence threshold
            min_confidence = Decimal('0.6')  # Default minimum confidence
            if decision.confidence < min_confidence:
                checks['confidence'] = False
                reasons.append(f"Decision confidence too low: {decision.confidence}")
                risk_level = max(risk_level, RiskLevel.MEDIUM)
            else:
                checks['confidence'] = True

            # Overall approval
            approved = all(checks.values())

            if not approved:
                logger.warning(f"Risk check failed for {decision.symbol}: {reasons}")
            else:
                logger.info(f"Risk check passed for {decision.symbol} with {risk_level.value} risk")

            return RiskCheckResult(
                approved=approved,
                risk_level=risk_level,
                checks=checks,
                reasons=reasons
            )

        except Exception as e:
            logger.error(f"Error in risk check: {e}")
            return RiskCheckResult(
                approved=False,
                risk_level=RiskLevel.EXTREME,
                checks={'error': False},
                reasons=[f"Risk check error: {str(e)}"]
            )

    def update_position(self, position: Position):
        """Update position tracking for risk calculations"""
        try:
            self._positions[position.symbol] = position

            # Update daily P&L
            today = datetime.utcnow().date().isoformat()
            if today not in self._daily_pnl:
                self._daily_pnl[today] = Decimal('0')

            # Add realized P&L to daily total
            self._daily_pnl[today] += position.realized_pnl

            logger.debug(f"Updated position tracking for {position.symbol}")

        except Exception as e:
            logger.error(f"Error updating position: {e}")

    def add_trade_result(self, symbol: str, pnl: Decimal, trade_data: Dict):
        """Add completed trade result for analysis"""
        try:
            trade_record = {
                'symbol': symbol,
                'pnl': pnl,
                'timestamp': datetime.utcnow(),
                'data': trade_data
            }

            self._trade_history.append(trade_record)

            # Update daily P&L
            today = datetime.utcnow().date().isoformat()
            if today not in self._daily_pnl:
                self._daily_pnl[today] = Decimal('0')
            self._daily_pnl[today] += pnl

            # Update balance tracking
            self._current_balance += pnl
            if self._current_balance > self._peak_balance:
                self._peak_balance = self._current_balance

            # Update max drawdown
            if self._peak_balance > 0:
                current_drawdown = (self._peak_balance - self._current_balance) / self._peak_balance
                if current_drawdown > self._max_drawdown:
                    self._max_drawdown = current_drawdown

            logger.info(f"Added trade result: {symbol} P&L: {pnl}")

        except Exception as e:
            logger.error(f"Error adding trade result: {e}")

    def _calculate_current_drawdown(self, current_balance: Decimal) -> Decimal:
        """Calculate current drawdown percentage"""
        try:
            if self._peak_balance == 0:
                self._peak_balance = current_balance
                return Decimal('0')

            if current_balance > self._peak_balance:
                self._peak_balance = current_balance
                return Decimal('0')

            drawdown = (self._peak_balance - current_balance) / self._peak_balance
            return drawdown

        except Exception as e:
            logger.error(f"Error calculating drawdown: {e}")
            return Decimal('0')

    def _check_correlation_risk(self, symbol: str, current_positions: List[Position]) -> Decimal:
        """Check correlation risk with existing positions"""
        try:
            if not current_positions:
                return Decimal('0')

            max_correlation = Decimal('0')

            for position in current_positions:
                if position.symbol == symbol:
                    continue

                # Get correlation between symbols (simplified - in reality would use price data)
                correlation = self._get_symbol_correlation(symbol, position.symbol)
                if correlation > max_correlation:
                    max_correlation = correlation

            return max_correlation

        except Exception as e:
            logger.error(f"Error checking correlation risk: {e}")
            return Decimal('0.5')  # Default moderate correlation

    def _get_symbol_correlation(self, symbol1: str, symbol2: str) -> Decimal:
        """Get correlation between two symbols"""
        try:
            # Simplified correlation logic - in reality would calculate from price data
            pair = (min(symbol1, symbol2), max(symbol1, symbol2))

            if pair in self._symbol_correlations:
                return self._symbol_correlations[pair]

            # Default correlations based on symbol similarity
            if symbol1[:3] == symbol2[:3]:  # Same base currency
                correlation = Decimal('0.7')
            elif 'BTC' in symbol1 and 'BTC' in symbol2:
                correlation = Decimal('0.8')
            elif 'ETH' in symbol1 and 'ETH' in symbol2:
                correlation = Decimal('0.8')
            else:
                correlation = Decimal('0.3')  # Default moderate correlation

            self._symbol_correlations[pair] = correlation
            return correlation

        except Exception as e:
            logger.error(f"Error getting symbol correlation: {e}")
            return Decimal('0.5')

    def adjust_risk_for_volatility(
        self,
        decision: TradingDecision,
        recent_candles: List[Candle],
        atr_value: Optional[Decimal] = None
    ) -> TradingDecision:
        """Adjust risk parameters based on market volatility"""
        try:
            if not recent_candles:
                return decision

            # Calculate volatility if ATR not provided
            if atr_value is None:
                atr_value = self._calculate_simple_volatility(recent_candles)

            # Volatility-based risk adjustment
            if atr_value:
                volatility_ratio = atr_value / recent_candles[-1].close_price

                # Adjust position sizing based on volatility
                if decision.position_sizing:
                    # Reduce position size in high volatility
                    if volatility_ratio > Decimal('0.03'):  # 3% volatility
                        adjustment_factor = Decimal('0.7')  # Reduce by 30%
                    elif volatility_ratio > Decimal('0.02'):  # 2% volatility
                        adjustment_factor = Decimal('0.85')  # Reduce by 15%
                    else:
                        adjustment_factor = Decimal('1.0')  # No adjustment

                    decision.position_sizing.position_size *= adjustment_factor
                    decision.position_sizing.risk_amount *= adjustment_factor

            logger.debug(f"Adjusted risk for volatility: {decision.symbol}")
            return decision

        except Exception as e:
            logger.error(f"Error adjusting risk for volatility: {e}")
            return decision

    def _calculate_simple_volatility(self, candles: List[Candle]) -> Decimal:
        """Calculate simple volatility measure"""
        try:
            if len(candles) < 2:
                return Decimal('0')

            # Calculate average true range over recent candles
            true_ranges = []

            for i in range(1, len(candles)):
                current = candles[i]
                previous = candles[i-1]

                tr1 = current.high_price - current.low_price
                tr2 = abs(current.high_price - previous.close_price)
                tr3 = abs(current.low_price - previous.close_price)

                true_range = max(tr1, tr2, tr3)
                true_ranges.append(true_range)

            if true_ranges:
                return sum(true_ranges) / len(true_ranges)
            else:
                return Decimal('0')

        except Exception as e:
            logger.error(f"Error calculating volatility: {e}")
            return Decimal('0')

    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics and statistics"""
        try:
            today = datetime.utcnow().date().isoformat()
            daily_pnl = self._daily_pnl.get(today, Decimal('0'))

            # Calculate win rate from trade history
            if self._trade_history:
                winning_trades = sum(1 for trade in self._trade_history if trade['pnl'] > 0)
                win_rate = winning_trades / len(self._trade_history)
            else:
                win_rate = 0

            return {
                'current_balance': float(self._current_balance),
                'peak_balance': float(self._peak_balance),
                'max_drawdown': float(self._max_drawdown),
                'daily_pnl': float(daily_pnl),
                'open_positions': len(self._positions),
                'total_trades': len(self._trade_history),
                'win_rate': win_rate,
                'risk_parameters': {
                    'max_position_size': float(self.risk_params.max_position_size),
                    'max_daily_loss': float(self.risk_params.max_daily_loss),
                    'max_drawdown': float(self.risk_params.max_drawdown),
                    'risk_per_trade': float(self.risk_params.risk_per_trade),
                    'max_open_positions': self.risk_params.max_open_positions
                }
            }

        except Exception as e:
            logger.error(f"Error getting risk metrics: {e}")
            return {}

    def reset_daily_limits(self):
        """Reset daily limits (call at start of new trading day)"""
        try:
            today = datetime.utcnow().date().isoformat()
            self._daily_pnl[today] = Decimal('0')
            logger.info("Reset daily risk limits")

        except Exception as e:
            logger.error(f"Error resetting daily limits: {e}")

    def update_risk_parameters(self, new_params: RiskParameters):
        """Update risk parameters"""
        try:
            self.risk_params = new_params
            logger.info("Updated risk parameters")

        except Exception as e:
            logger.error(f"Error updating risk parameters: {e}")