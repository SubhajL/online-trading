"""
Cost modeling for backtesting: fees, slippage, and funding.
"""

from datetime import datetime
from decimal import Decimal

from .types import BacktestFill, OrderSide


class CostCalculator:
    """
    Calculates trading costs including fees, slippage, and funding.
    """

    def __init__(
        self,
        fee_bps_spot: Decimal = Decimal(10),      # 0.10% for spot
        fee_bps_futures: Decimal = Decimal(4),    # 0.04% for futures
        funding_model: str = "disabled",
    ):
        """
        Initialize cost calculator.

        Args:
            fee_bps_spot: Spot trading fee in basis points
            fee_bps_futures: Futures trading fee in basis points
            funding_model: "disabled", "constant", or path to funding series
        """
        self.fee_bps_spot = fee_bps_spot
        self.fee_bps_futures = fee_bps_futures
        self.funding_model = funding_model

        # Convert basis points to decimal
        self.spot_fee_rate = fee_bps_spot / Decimal(10000)
        self.futures_fee_rate = fee_bps_futures / Decimal(10000)

    def calculate_trading_fee(
        self,
        notional: Decimal,
        is_futures: bool = False,
        is_maker: bool = False,
    ) -> Decimal:
        """
        Calculate trading fee based on notional value.

        Args:
            notional: Notional trade value (price * quantity)
            is_futures: Whether this is a futures trade
            is_maker: Whether this is a maker trade (gets rebate)

        Returns:
            Fee amount in quote currency
        """
        base_rate = self.futures_fee_rate if is_futures else self.spot_fee_rate

        # Maker rebate (simplified - assume 25% reduction)
        if is_maker:
            base_rate *= Decimal("0.75")

        return notional * base_rate

    def calculate_fill_fee(self, fill: BacktestFill, is_futures: bool = False) -> Decimal:
        """
        Calculate fee for a specific fill.

        Args:
            fill: Fill to calculate fee for
            is_futures: Whether this is a futures fill

        Returns:
            Fee amount
        """
        notional = fill.price * fill.quantity
        return self.calculate_trading_fee(notional, is_futures)

    def calculate_funding_payment(
        self,
        position_size: Decimal,
        position_side: str,  # "LONG" or "SHORT"
        mark_price: Decimal,
        funding_rate: Decimal,
        funding_interval_hours: int = 8,
    ) -> Decimal:
        """
        Calculate funding payment for futures position.

        Args:
            position_size: Size of position
            position_side: LONG or SHORT
            mark_price: Mark price at funding time
            funding_rate: Funding rate (positive means longs pay shorts)
            funding_interval_hours: Hours between funding payments

        Returns:
            Funding payment (positive = pay, negative = receive)
        """
        if self.funding_model == "disabled":
            return Decimal(0)

        notional_value = position_size * mark_price

        # Long positions pay positive funding rates
        # Short positions receive positive funding rates
        if position_side == "LONG":
            return notional_value * funding_rate
        # SHORT
        return -notional_value * funding_rate

    def get_funding_rate(
        self,
        symbol: str,
        timestamp: datetime,
    ) -> Decimal:
        """
        Get funding rate for symbol at given time.

        Args:
            symbol: Trading symbol
            timestamp: Time to get funding rate for

        Returns:
            Funding rate (can be positive or negative)
        """
        if self.funding_model == "disabled":
            return Decimal(0)

        if self.funding_model == "constant":
            # Use a constant funding rate for testing
            return Decimal("0.0001")  # 0.01% per 8 hours

        # TODO: Implement funding series loader
        # For now, return a simple time-based mock
        hour = timestamp.hour
        if hour % 8 == 0:  # Funding at 00:00, 08:00, 16:00 UTC
            # Simple oscillating funding rate
            return Decimal("0.0001") if (timestamp.day % 2) == 0 else Decimal("-0.0001")

        return Decimal(0)

    def should_charge_funding(
        self,
        timestamp: datetime,
        position_opened_at: datetime,
    ) -> bool:
        """
        Determine if funding should be charged at this timestamp.

        Args:
            timestamp: Current timestamp
            position_opened_at: When position was opened

        Returns:
            True if funding should be charged
        """
        if self.funding_model == "disabled":
            return False

        # Funding occurs at 00:00, 08:00, 16:00 UTC
        funding_hours = {0, 8, 16}

        # Only charge if position was open before this funding time
        current_funding_time = timestamp.replace(
            hour=timestamp.hour - (timestamp.hour % 8),
            minute=0,
            second=0,
            microsecond=0,
        )

        return (timestamp.hour in funding_hours and
                timestamp.minute == 0 and
                position_opened_at < current_funding_time)

    def calculate_total_trade_cost(
        self,
        entry_fill: BacktestFill,
        exit_fill: BacktestFill | None,
        funding_payments: list[Decimal],
        is_futures: bool = False,
    ) -> dict[str, Decimal]:
        """
        Calculate total cost breakdown for a trade.

        Args:
            entry_fill: Entry fill
            exit_fill: Exit fill (if trade is closed)
            funding_payments: List of funding payments during trade
            is_futures: Whether this is a futures trade

        Returns:
            Dictionary with cost breakdown
        """
        costs = {
            "entry_fee": self.calculate_fill_fee(entry_fill, is_futures),
            "entry_slippage": entry_fill.slippage,
            "exit_fee": Decimal(0),
            "exit_slippage": Decimal(0),
            "funding": sum(funding_payments),
            "total_fees": Decimal(0),
            "total_slippage": Decimal(0),
            "total_funding": sum(funding_payments),
            "total_cost": Decimal(0),
        }

        if exit_fill:
            costs["exit_fee"] = self.calculate_fill_fee(exit_fill, is_futures)
            costs["exit_slippage"] = exit_fill.slippage

        costs["total_fees"] = costs["entry_fee"] + costs["exit_fee"]
        costs["total_slippage"] = costs["entry_slippage"] + costs["exit_slippage"]
        costs["total_cost"] = (costs["total_fees"] +
                              costs["total_slippage"] +
                              costs["total_funding"])

        return costs

    def calculate_breakeven_price(
        self,
        entry_price: Decimal,
        entry_side: OrderSide,
        entry_size: Decimal,
        is_futures: bool = False,
    ) -> Decimal:
        """
        Calculate breakeven price including fees.

        Args:
            entry_price: Entry price
            entry_side: BUY or SELL
            entry_size: Position size
            is_futures: Whether this is futures

        Returns:
            Breakeven price after fees
        """
        # Calculate entry fee
        entry_notional = entry_price * entry_size
        entry_fee = self.calculate_trading_fee(entry_notional, is_futures)

        # Assume exit fee will be similar
        exit_fee = entry_fee

        total_fees = entry_fee + exit_fee
        fee_per_unit = total_fees / entry_size

        # Adjust breakeven price for fees
        if entry_side == OrderSide.BUY:
            # Long position: need price to rise by fee amount
            return entry_price + fee_per_unit
        # SELL (short)
        # Short position: need price to fall by fee amount
        return entry_price - fee_per_unit

    def estimate_daily_funding_impact(
        self,
        position_value: Decimal,
        average_funding_rate: Decimal = Decimal("0.0001"),
    ) -> Decimal:
        """
        Estimate daily funding impact for position sizing.

        Args:
            position_value: Notional position value
            average_funding_rate: Average daily funding rate

        Returns:
            Estimated daily funding cost
        """
        if self.funding_model == "disabled":
            return Decimal(0)

        # 3 funding periods per day (every 8 hours)
        daily_funding_rate = average_funding_rate * 3
        return position_value * daily_funding_rate
