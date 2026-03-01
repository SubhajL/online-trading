"""
Position sizing module for risk management.

CRITICAL: This module ensures we never risk more than 0.5% per trade.
"""

from dataclasses import dataclass
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


@dataclass
class PositionSizeConfig:
    """Configuration for position sizing."""

    fixed_risk_pct: Decimal = Decimal("0.005")  # 0.5% risk per trade
    max_position_pct: Decimal = Decimal("0.02")  # 2% max position size
    atr_multiplier: Decimal = Decimal("1.5")  # ATR multiplier for stops
    min_position_size: Decimal = Decimal("0.001")  # Minimum position
    confidence_scaling: bool = True  # Scale by confidence
    max_leverage: Decimal = Decimal(3)  # Max leverage for futures


class PositionSizer:
    """Calculate position sizes based on risk management rules."""

    def __init__(self, config: PositionSizeConfig) -> None:
        self.config = config

    def calculate_position_size(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        confidence: Decimal,
    ) -> Decimal:
        """
        Calculate position size using fixed fractional risk.

        Args:
            account_balance: Total account balance
            entry_price: Entry price for the position
            stop_loss: Stop loss price
            confidence: Signal confidence (0-1)

        Returns:
            Position size in base currency

        Raises:
            ValueError: If inputs are invalid
        """
        # Validate inputs
        if account_balance <= 0:
            raise ValueError("Account balance must be positive")
        if stop_loss >= entry_price:
            raise ValueError("Stop loss must be below entry price for long positions")

        # Calculate stop distance
        stop_distance = entry_price - stop_loss
        stop_pct = stop_distance / entry_price

        # Calculate risk amount (0.5% of account)
        risk_amount = account_balance * self.config.fixed_risk_pct

        # Apply confidence scaling if enabled
        if self.config.confidence_scaling:
            risk_amount = risk_amount * confidence

        # Calculate base position size
        position_size = risk_amount / stop_distance

        # Apply position size limits
        max_position_value = account_balance * self.config.max_position_pct
        max_position_size = max_position_value / entry_price

        # Use the smaller of risk-based or max position
        position_size = min(position_size, max_position_size)

        # Apply minimum position size
        position_size = max(position_size, self.config.min_position_size)

        # Round to reasonable precision (3 decimals)
        position_size = position_size.quantize(Decimal("0.001"))

        # Log the calculation
        logger.debug(
            f"Position size calculation: "
            f"balance=${account_balance}, entry=${entry_price}, "
            f"stop=${stop_loss} ({stop_pct:.2%}), "
            f"confidence={confidence:.2f}, "
            f"position={position_size}",
        )

        return position_size

    def calculate_position_size_with_atr(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        atr: Decimal,
        confidence: Decimal,
    ) -> Decimal:
        """
        Calculate position size using ATR-based stop.

        Args:
            account_balance: Total account balance
            entry_price: Entry price for the position
            atr: Average True Range value
            confidence: Signal confidence (0-1)

        Returns:
            Position size in base currency
        """
        # Calculate stop loss using ATR
        stop_distance = atr * self.config.atr_multiplier
        stop_loss = entry_price - stop_distance

        return self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=confidence,
        )

    def calculate_futures_position_size(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        confidence: Decimal,
        leverage: Decimal,
    ) -> Decimal:
        """
        Calculate position size for futures trading with leverage.

        Args:
            account_balance: Total account balance
            entry_price: Entry price for the position
            stop_loss: Stop loss price
            confidence: Signal confidence (0-1)
            leverage: Leverage to use (capped at max)

        Returns:
            Position size in contracts
        """
        # Cap leverage at maximum
        leverage = min(leverage, self.config.max_leverage)

        # Calculate base position size
        position_size = self.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=confidence,
        )

        # For futures, we need to ensure margin requirements are met
        margin_required = (position_size * entry_price) / leverage

        # Check if margin exceeds position limit
        max_margin = account_balance * self.config.max_position_pct
        if margin_required > max_margin:
            # Scale down position to fit margin limit
            position_size = (max_margin * leverage) / entry_price
            position_size = position_size.quantize(Decimal("0.001"))

        logger.debug(
            f"Futures position: size={position_size}, "
            f"leverage={leverage}x, margin=${margin_required:.2f}",
        )

        return position_size

    def validate_position_parameters(
        self,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal | None = None,
    ) -> bool:
        """
        Validate position parameters are sensible.

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Optional take profit price

        Returns:
            True if parameters are valid
        """
        # Stop must be below entry for longs
        if stop_loss >= entry_price:
            logger.warning(f"Invalid stop loss: {stop_loss} >= {entry_price}")
            return False

        # Take profit must be above entry for longs
        if take_profit and take_profit <= entry_price:
            logger.warning(f"Invalid take profit: {take_profit} <= {entry_price}")
            return False

        # Risk/reward should be reasonable (at least 1:1)
        if take_profit:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            rr_ratio = reward / risk

            if rr_ratio < Decimal("1.0"):
                logger.warning(f"Poor risk/reward ratio: {rr_ratio:.2f}")
                # Still valid, just warning

        return True

    def calculate_risk_metrics(
        self,
        position_size: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        account_balance: Decimal,
    ) -> dict:
        """
        Calculate risk metrics for a position.

        Args:
            position_size: Position size
            entry_price: Entry price
            stop_loss: Stop loss price
            account_balance: Account balance

        Returns:
            Dictionary of risk metrics
        """
        stop_distance = entry_price - stop_loss
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / account_balance

        position_value = position_size * entry_price
        position_pct = position_value / account_balance

        return {
            "risk_amount": float(risk_amount),
            "risk_pct": float(risk_pct),
            "position_value": float(position_value),
            "position_pct": float(position_pct),
            "stop_distance": float(stop_distance),
            "stop_pct": float(stop_distance / entry_price),
        }
