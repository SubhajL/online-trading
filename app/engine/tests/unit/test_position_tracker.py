"""
Unit tests for position tracker.
Following T-3: Pure logic unit tests without database dependencies.
Following T-4: Avoiding heavy mocking.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

# Import from the actual module (will create after tests)
from app.engine.services.position_tracker import (
    update_position,
    calculate_unrealized_pnl,
    should_close_position,
    Position,
    PositionSide,
    OrderFill,
    MarketData,
    CloseSignal,
    CloseReason
)


class TestUpdatePosition:
    """Tests for position update logic."""

    def test_update_position_new_position(self):
        """Creates new position from first fill."""
        fill = OrderFill(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            commission=Decimal("10"),  # $10 commission
            timestamp=datetime.now(timezone.utc)
        )

        position = update_position(fill)

        assert position.symbol == "BTCUSDT"
        assert position.side == PositionSide.LONG
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000")
        assert position.realized_pnl == Decimal("-10")  # Just commission
        assert position.total_commission == Decimal("10")

    def test_update_position_add_to_existing(self):
        """Correctly averages price on additional fills."""
        # First fill
        fill1 = OrderFill(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            commission=Decimal("10"),
            timestamp=datetime.now(timezone.utc)
        )
        position = update_position(fill1)

        # Second fill - add to position
        fill2 = OrderFill(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("51000"),
            commission=Decimal("10.2"),
            timestamp=datetime.now(timezone.utc)
        )
        position = update_position(fill2, position)

        # Average price should be (0.1 * 50000 + 0.1 * 51000) / 0.2 = 50500
        assert position.quantity == Decimal("0.2")
        assert position.entry_price == Decimal("50500")
        assert position.total_commission == Decimal("20.2")

    def test_update_position_partial_close(self):
        """Handles partial position closure correctly."""
        # Initial position
        initial = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.2"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("-20"),  # Commission from entry
            total_commission=Decimal("20"),
            open_time=datetime.now(timezone.utc)
        )

        # Close half the position at profit
        close_fill = OrderFill(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,  # Opposite side to close
            quantity=Decimal("0.1"),
            price=Decimal("52000"),
            commission=Decimal("10.4"),
            timestamp=datetime.now(timezone.utc)
        )
        position = update_position(close_fill, initial)

        # Should have half position left
        assert position.quantity == Decimal("0.1")
        assert position.entry_price == Decimal("50000")  # Entry price unchanged
        # PnL: 0.1 * (52000 - 50000) - 10.4 = 200 - 10.4 = 189.6
        # Plus previous -20 = 169.6
        assert position.realized_pnl == Decimal("169.6")

    def test_update_position_full_close(self):
        """Handles full position closure."""
        initial = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("-10"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        # Close entire short position (buy back)
        close_fill = OrderFill(
            symbol="BTCUSDT",
            side=PositionSide.LONG,  # Buy to close short
            quantity=Decimal("0.1"),
            price=Decimal("49000"),  # Profit on short
            commission=Decimal("9.8"),
            timestamp=datetime.now(timezone.utc)
        )
        position = update_position(close_fill, initial)

        assert position.quantity == Decimal("0")
        assert position.is_closed is True
        # PnL for short: 0.1 * (50000 - 49000) - 9.8 = 100 - 9.8 = 90.2
        # Plus previous -10 = 80.2
        assert position.realized_pnl == Decimal("80.2")


class TestCalculateUnrealizedPnl:
    """Tests for unrealized PnL calculation."""

    def test_calculate_unrealized_pnl_long_profit(self):
        """Calculates profit for long position."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        pnl = calculate_unrealized_pnl(position, Decimal("52000"))

        # Unrealized: 0.1 * (52000 - 50000) = 200
        assert pnl == Decimal("200")

    def test_calculate_unrealized_pnl_short_loss(self):
        """Calculates loss for short position."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        pnl = calculate_unrealized_pnl(position, Decimal("51000"))

        # Unrealized for short: 0.1 * (50000 - 51000) = -100
        assert pnl == Decimal("-100")

    def test_calculate_unrealized_pnl_zero_quantity(self):
        """Returns zero for closed position."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("100"),
            total_commission=Decimal("20"),
            open_time=datetime.now(timezone.utc),
            is_closed=True
        )

        pnl = calculate_unrealized_pnl(position, Decimal("52000"))

        assert pnl == Decimal("0")


class TestShouldClosePosition:
    """Tests for position close decision logic."""

    def test_should_close_position_stop_loss_hit(self):
        """Triggers close when stop loss reached."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        market = MarketData(
            symbol="BTCUSDT",
            current_price=Decimal("48900"),  # Below stop loss
            bid=Decimal("48899"),
            ask=Decimal("48901"),
            timestamp=datetime.now(timezone.utc)
        )

        signal = should_close_position(position, market)

        assert signal.should_close is True
        assert signal.reason == CloseReason.STOP_LOSS
        assert signal.close_price == Decimal("48900")

    def test_should_close_position_take_profit_hit(self):
        """Triggers close at take profit level."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.SHORT,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            take_profit=Decimal("48000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        market = MarketData(
            symbol="BTCUSDT",
            current_price=Decimal("47900"),  # Below take profit for short
            bid=Decimal("47899"),
            ask=Decimal("47901"),
            timestamp=datetime.now(timezone.utc)
        )

        signal = should_close_position(position, market)

        assert signal.should_close is True
        assert signal.reason == CloseReason.TAKE_PROFIT
        assert signal.close_price == Decimal("47900")

    def test_should_close_position_time_stop(self):
        """Triggers close after max holding time."""
        from datetime import timedelta

        # Position open for more than 24 hours
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=old_time,
            max_hold_time=timedelta(hours=24)
        )

        market = MarketData(
            symbol="BTCUSDT",
            current_price=Decimal("50100"),
            bid=Decimal("50099"),
            ask=Decimal("50101"),
            timestamp=datetime.now(timezone.utc)
        )

        signal = should_close_position(position, market)

        assert signal.should_close is True
        assert signal.reason == CloseReason.TIME_STOP
        assert signal.close_price == Decimal("50100")

    def test_should_close_position_no_close(self):
        """No close signal when conditions not met."""
        position = Position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            take_profit=Decimal("52000"),
            realized_pnl=Decimal("0"),
            total_commission=Decimal("10"),
            open_time=datetime.now(timezone.utc)
        )

        market = MarketData(
            symbol="BTCUSDT",
            current_price=Decimal("50500"),  # Between SL and TP
            bid=Decimal("50499"),
            ask=Decimal("50501"),
            timestamp=datetime.now(timezone.utc)
        )

        signal = should_close_position(position, market)

        assert signal.should_close is False
        assert signal.reason is None