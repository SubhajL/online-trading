"""
Fill price logic for backtesting engine.
Implements intrabar HI/LO touch rules for realistic fill simulation.
"""

from decimal import Decimal

from ..models import Candle
from .types import BacktestFill, BacktestOrder, FillReason, OrderSide, OrderType


class FillEngine:
    """
    Handles order fills using intrabar HI/LO touch rules.

    Fill rules:
    - LIMIT orders: fill at limit price if within [low, high] of bar
    - STOP_MARKET: trigger when HI/LO crosses stop, fill at stop +/- slippage
    - MARKET orders: fill at open of next bar + slippage
    """

    def __init__(self, slippage_bps: Decimal = Decimal(2)):
        """
        Initialize fill engine.

        Args:
            slippage_bps: Slippage in basis points (e.g., 2 = 0.02%)
        """
        self.slippage_bps = slippage_bps

    def can_fill_limit_order(
        self,
        order: BacktestOrder,
        candle: Candle,
    ) -> bool:
        """
        Check if limit order can be filled based on HI/LO touch.

        Args:
            order: Limit order to check
            candle: Current candle data

        Returns:
            True if order can be filled
        """
        if order.type != OrderType.LIMIT or order.price is None:
            return False

        # For BUY limit: price must be >= candle low
        # For SELL limit: price must be <= candle high
        if order.side == OrderSide.BUY:
            return order.price >= candle.low_price
        # SELL
        return order.price <= candle.high_price

    def can_trigger_stop_order(
        self,
        order: BacktestOrder,
        candle: Candle,
    ) -> bool:
        """
        Check if stop order should be triggered.

        Args:
            order: Stop order to check
            candle: Current candle data

        Returns:
            True if stop should trigger
        """
        if order.stop_price is None:
            return False

        # BUY stop: trigger when price goes above stop_price
        # SELL stop: trigger when price goes below stop_price
        if order.side == OrderSide.BUY:
            return candle.high_price >= order.stop_price
        # SELL
        return candle.low_price <= order.stop_price

    def calculate_slippage(
        self,
        price: Decimal,
        side: OrderSide,
        is_market_order: bool = False,
    ) -> Decimal:
        """
        Calculate slippage adjustment for fill price.

        Args:
            price: Base fill price
            side: Order side
            is_market_order: Whether this is a market order

        Returns:
            Price adjustment for slippage
        """
        slippage_factor = self.slippage_bps / Decimal(10000)  # Convert bps to decimal

        # Market orders and aggressive fills get more slippage
        multiplier = Decimal("1.5") if is_market_order else Decimal("1.0")
        slippage_amount = price * slippage_factor * multiplier

        # Slippage is unfavorable to the trader
        if side == OrderSide.BUY:
            return slippage_amount  # Pay more
        # SELL
        return -slippage_amount  # Receive less

    def fill_limit_order(
        self,
        order: BacktestOrder,
        candle: Candle,
    ) -> BacktestFill | None:
        """
        Fill a limit order at the limit price.

        Args:
            order: Limit order to fill
            candle: Current candle

        Returns:
            Fill if order can be filled, None otherwise
        """
        if not self.can_fill_limit_order(order, candle):
            return None

        if order.price is None:
            return None

        # Fill at limit price (no slippage for limit orders that get filled)
        fill_price = order.price

        return BacktestFill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.remaining_quantity,
            price=fill_price,
            slippage=Decimal(0),  # No slippage for limit fills
            fill_reason=FillReason.LIMIT,
            fill_time=candle.close_time,
            candle_open_time=candle.open_time,
            candle_high=candle.high_price,
            candle_low=candle.low_price,
        )

    def fill_stop_market_order(
        self,
        order: BacktestOrder,
        candle: Candle,
    ) -> BacktestFill | None:
        """
        Fill a stop market order with slippage.

        Args:
            order: Stop market order to fill
            candle: Current candle

        Returns:
            Fill if stop is triggered, None otherwise
        """
        if not self.can_trigger_stop_order(order, candle):
            return None

        if order.stop_price is None:
            return None

        # Fill at stop price + slippage (unfavorable)
        base_price = order.stop_price
        slippage_adj = self.calculate_slippage(base_price, order.side, True)
        fill_price = base_price + slippage_adj

        return BacktestFill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.remaining_quantity,
            price=fill_price,
            slippage=abs(slippage_adj),
            fill_reason=FillReason.STOP,
            fill_time=candle.close_time,
            candle_open_time=candle.open_time,
            candle_high=candle.high_price,
            candle_low=candle.low_price,
        )

    def fill_market_order(
        self,
        order: BacktestOrder,
        candle: Candle,
        fill_at_open: bool = True,
    ) -> BacktestFill:
        """
        Fill a market order at market price with slippage.

        Args:
            order: Market order to fill
            candle: Current candle
            fill_at_open: If True, fill at open price, else close price

        Returns:
            Fill for the market order
        """
        base_price = candle.open_price if fill_at_open else candle.close_price
        slippage_adj = self.calculate_slippage(base_price, order.side, True)
        fill_price = base_price + slippage_adj

        return BacktestFill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.remaining_quantity,
            price=fill_price,
            slippage=abs(slippage_adj),
            fill_reason=FillReason.MARKET,
            fill_time=candle.close_time,
            candle_open_time=candle.open_time,
            candle_high=candle.high_price,
            candle_low=candle.low_price,
        )

    def process_order_fills(
        self,
        orders: list[BacktestOrder],
        candle: Candle,
    ) -> list[BacktestFill]:
        """
        Process all resting orders against current candle for fills.

        Args:
            orders: List of active orders
            candle: Current market candle

        Returns:
            List of fills generated
        """
        fills = []

        for order in orders:
            fill = None

            if order.type == OrderType.MARKET:
                fill = self.fill_market_order(order, candle)
            elif order.type == OrderType.LIMIT:
                fill = self.fill_limit_order(order, candle)
            elif order.type == OrderType.STOP_MARKET:
                fill = self.fill_stop_market_order(order, candle)

            if fill:
                fills.append(fill)

        return fills

    def calculate_realistic_fill_price(
        self,
        order_type: OrderType,
        order_side: OrderSide,
        target_price: Decimal | None,
        candle: Candle,
        is_aggressive: bool = False,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate realistic fill price and slippage cost.

        Args:
            order_type: Type of order
            order_side: BUY or SELL
            target_price: Desired fill price (for limit orders)
            candle: Current market candle
            is_aggressive: Whether this is an aggressive order

        Returns:
            Tuple of (fill_price, slippage_cost)
        """
        if order_type == OrderType.LIMIT and target_price:
            # Limit orders get filled at limit price if touched
            if (order_side == OrderSide.BUY and target_price >= candle.low_price) or (
                order_side == OrderSide.SELL and target_price <= candle.high_price
            ):
                return target_price, Decimal(0)
            # No fill possible
            return Decimal(0), Decimal(0)

        # Market or triggered stop orders
        base_price = candle.open_price
        slippage_adj = self.calculate_slippage(base_price, order_side, True)
        return base_price + slippage_adj, abs(slippage_adj)
