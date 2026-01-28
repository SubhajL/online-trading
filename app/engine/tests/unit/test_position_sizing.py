"""
CRITICAL: Position sizing tests to ensure we never risk more than 0.5% per trade.

These tests verify the most important safety mechanism in our trading system.
If position sizing is wrong, we could lose significant capital.
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pytest

from app.engine.decision.position_sizer import PositionSizeConfig, PositionSizer


class TestPositionSizing:
    """Test position sizing calculations for risk management."""

    @pytest.fixture
    def config(self):
        """Standard position sizing configuration."""
        return PositionSizeConfig(
            fixed_risk_pct=Decimal("0.005"),  # 0.5% risk per trade
            max_position_pct=Decimal("0.02"),  # 2% max position size
            atr_multiplier=Decimal("1.5"),     # 1.5x ATR for stop distance
            min_position_size=Decimal("0.001"), # Minimum position
            confidence_scaling=True,           # Scale by confidence
        )

    @pytest.fixture
    def sizer(self, config):
        """Create position sizer instance."""
        return PositionSizer(config)

    def test_position_size_never_exceeds_half_percent_risk(self, sizer):
        """CRITICAL: Verify 0.5% risk limit is strictly enforced."""
        account_balance = Decimal("10000")
        entry_price = Decimal("50000")
        stop_loss = Decimal("49000")  # 2% stop distance

        position_size = sizer.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=Decimal("1.0"),  # Max confidence
        )

        # Calculate actual risk
        stop_distance = entry_price - stop_loss
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / account_balance

        # CRITICAL: Risk must never exceed 0.5%
        assert risk_pct <= Decimal("0.005"), f"Risk {risk_pct:.4%} exceeds 0.5% limit!"

        # In this case, position is limited by 2% max position rule
        # With BTC at $50k and account at $10k, max position is 0.004 BTC
        expected_risk = Decimal("0.0004")  # 0.04% due to position limit
        assert abs(risk_pct - expected_risk) < Decimal("0.0001"), \
            f"Risk {risk_pct:.4%} != expected {expected_risk:.4%}"

    def test_position_sizing_achieves_target_risk_when_possible(self, sizer):
        """Test position sizing hits target risk when not position-capped."""
        config = sizer.config
        account_balance = Decimal("100000")  # $100k account
        entry_price = Decimal("50000")       # BTC at $50k

        test_cases = [
            # (stop_loss, stop_desc)
            (Decimal("49500"), "1%"),    # Position-capped, low risk
            (Decimal("45000"), "10%"),   # Position-capped, higher risk
            (Decimal("35000"), "30%"),   # Risk-capped, should reach 0.5%
        ]

        for stop_loss, stop_desc in test_cases:
            position_size = sizer.calculate_position_size(
                account_balance=account_balance,
                entry_price=entry_price,
                stop_loss=stop_loss,
                confidence=Decimal("1.0"),
            )

            # Calculate actual risk
            stop_distance = entry_price - stop_loss
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / account_balance

            # Check position size
            position_value = position_size * entry_price
            position_pct = position_value / account_balance

            # Verify constraints
            assert (
                risk_pct <= config.fixed_risk_pct
            ), f"Risk {risk_pct:.4%} exceeds {config.fixed_risk_pct:.4%}!"
            assert (
                position_pct <= config.max_position_pct
            ), f"Position {position_pct:.2%} exceeds {config.max_position_pct:.2%}!"

            stop_pct = stop_distance / entry_price
            expected_risk_pct = min(config.fixed_risk_pct, config.max_position_pct * stop_pct)

            assert abs(risk_pct - expected_risk_pct) < Decimal(
                "0.0001",
            ), f"{stop_desc}: Risk {risk_pct:.4%} != expected {expected_risk_pct:.4%}"

    def test_position_sizing_with_confidence_scaling(self, sizer):
        """Test position size scales down with lower confidence."""
        config = sizer.config
        # Use a wide stop so we're risk-capped (not position-capped).
        account_balance = Decimal("100000")
        entry_price = Decimal("50000")
        stop_loss = Decimal("35000")  # 30% stop

        test_cases = [
            # (confidence, expected_risk_factor)
            (Decimal("1.0"), Decimal("1.0")),    # Full risk
            (Decimal("0.8"), Decimal("0.8")),    # 80% of risk
            (Decimal("0.5"), Decimal("0.5")),    # 50% of risk
            (Decimal("0.3"), Decimal("0.3")),    # 30% of risk
        ]

        for confidence, risk_factor in test_cases:
            position_size = sizer.calculate_position_size(
                account_balance=account_balance,
                entry_price=entry_price,
                stop_loss=stop_loss,
                confidence=confidence,
            )

            # Calculate actual risk
            stop_distance = entry_price - stop_loss
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / account_balance

            expected_risk = config.fixed_risk_pct * risk_factor
            assert abs(risk_pct - expected_risk) < Decimal("0.0001"), \
                f"Confidence {confidence}: Risk {risk_pct:.4%} != {expected_risk:.4%}"

    def test_max_position_size_limit(self, sizer):
        """Test maximum position size is enforced (2% of account)."""
        account_balance = Decimal("10000")
        entry_price = Decimal("50000")
        stop_loss = Decimal("49990")  # Very tight stop (0.02%)

        position_size = sizer.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=Decimal("1.0"),
        )

        # Position value as % of account
        position_value = position_size * entry_price
        position_pct = position_value / account_balance

        # Should be capped at 2%
        assert position_pct <= Decimal("0.02"), \
            f"Position {position_pct:.2%} exceeds 2% limit"

    def test_minimum_position_size(self, sizer):
        """Test minimum position size is enforced."""
        account_balance = Decimal("100")  # Small account
        entry_price = Decimal("50000")
        stop_loss = Decimal("40000")  # 20% stop

        position_size = sizer.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=Decimal("1.0"),
        )

        # Should be at least minimum
        assert position_size >= Decimal("0.001"), \
            f"Position {position_size} below minimum"

    def test_position_sizing_with_atr_stop(self, sizer):
        """Test position sizing with ATR-based stops."""
        config = sizer.config
        account_balance = Decimal("100000")
        entry_price = Decimal("50000")
        atr = Decimal("500")  # 1% ATR

        # Calculate stop based on ATR
        stop_distance = atr * sizer.config.atr_multiplier  # 1.5 * 500 = 750
        stop_loss = entry_price - stop_distance  # 49250

        position_size = sizer.calculate_position_size_with_atr(
            account_balance=account_balance,
            entry_price=entry_price,
            atr=atr,
            confidence=Decimal("1.0"),
        )

        # Verify risk
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / account_balance

        stop_pct = stop_distance / entry_price
        expected_risk_pct = min(config.fixed_risk_pct, config.max_position_pct * stop_pct)
        assert abs(risk_pct - expected_risk_pct) < Decimal("0.0001"), \
            f"ATR-based risk {risk_pct:.4%} != expected {expected_risk_pct:.4%}"

    def test_position_sizing_edge_cases(self, sizer):
        """Test edge cases that could cause errors."""
        account_balance = Decimal("10000")

        # Edge case: Stop at entry (no risk)
        with pytest.raises(ValueError, match="Stop loss must be below entry"):
            sizer.calculate_position_size(
                account_balance=account_balance,
                entry_price=Decimal("50000"),
                stop_loss=Decimal("50000"),
                confidence=Decimal("1.0"),
            )

        # Edge case: Stop above entry
        with pytest.raises(ValueError, match="Stop loss must be below entry"):
            sizer.calculate_position_size(
                account_balance=account_balance,
                entry_price=Decimal("50000"),
                stop_loss=Decimal("51000"),
                confidence=Decimal("1.0"),
            )

        # Edge case: Zero account balance
        with pytest.raises(ValueError, match="Account balance must be positive"):
            sizer.calculate_position_size(
                account_balance=Decimal("0"),
                entry_price=Decimal("50000"),
                stop_loss=Decimal("49000"),
                confidence=Decimal("1.0"),
            )

        # Edge case: Zero confidence
        position_size = sizer.calculate_position_size(
            account_balance=account_balance,
            entry_price=Decimal("50000"),
            stop_loss=Decimal("49000"),
            confidence=Decimal("0"),
        )
        assert position_size == sizer.config.min_position_size, \
            "Zero confidence should give minimum position"

    def test_futures_position_sizing_with_leverage(self, config):
        """Test position sizing for futures with leverage."""
        config.max_leverage = Decimal("3")  # 3x max leverage
        sizer = PositionSizer(config)

        account_balance = Decimal("100000")
        entry_price = Decimal("50000")
        stop_loss = Decimal("49000")

        position_size = sizer.calculate_futures_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=Decimal("1.0"),
            leverage=Decimal("3"),
        )

        # Risk should still be capped (and may be position-limited).
        stop_distance = entry_price - stop_loss
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / account_balance

        stop_pct = stop_distance / entry_price
        expected_risk_pct = min(config.fixed_risk_pct, config.max_position_pct * stop_pct)
        assert abs(risk_pct - expected_risk_pct) < Decimal("0.0001"), \
            f"Futures risk {risk_pct:.4%} != expected {expected_risk_pct:.4%}"

        # Verify leverage is applied correctly
        margin_required = (position_size * entry_price) / Decimal("3")
        assert margin_required <= account_balance * Decimal("0.02"), \
            "Margin should not exceed 2% of account"

    def test_position_size_decimal_precision(self, sizer):
        """Test position sizes are rounded to exchange precision."""
        account_balance = Decimal("10000")
        entry_price = Decimal("50123.45")
        stop_loss = Decimal("49234.56")

        position_size = sizer.calculate_position_size(
            account_balance=account_balance,
            entry_price=entry_price,
            stop_loss=stop_loss,
            confidence=Decimal("0.75"),
        )

        # Should be rounded to reasonable precision (e.g., 0.001)
        assert position_size == position_size.quantize(Decimal("0.001")), \
            f"Position size {position_size} not properly rounded"

        # Verify risk is still within limits after rounding
        stop_distance = entry_price - stop_loss
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / account_balance

        assert risk_pct <= Decimal("0.005"), \
            f"Risk {risk_pct:.4%} exceeds limit after rounding"


class TestPositionSizerIntegration:
    """Integration tests with other components."""

    def test_position_sizer_with_real_market_data(self):
        """Test with realistic market conditions."""
        config = PositionSizeConfig(
            fixed_risk_pct=Decimal("0.005"),
            max_position_pct=Decimal("0.02"),
            atr_multiplier=Decimal("1.5"),
            min_position_size=Decimal("0.001"),
        )
        sizer = PositionSizer(config)

        # Simulate volatile market conditions
        test_scenarios = [
            {
                "name": "Bitcoin bull market",
                "balance": Decimal("50000"),
                "entry": Decimal("65000"),
                "atr": Decimal("2500"),  # ~4% volatility
            },
            {
                "name": "Bitcoin bear market",
                "balance": Decimal("50000"),
                "entry": Decimal("20000"),
                "atr": Decimal("1500"),  # ~7.5% volatility
            },
            {
                "name": "Ethereum normal",
                "balance": Decimal("10000"),
                "entry": Decimal("3500"),
                "atr": Decimal("150"),   # ~4.3% volatility
            },
        ]

        for scenario in test_scenarios:
            position_size = sizer.calculate_position_size_with_atr(
                account_balance=scenario["balance"],
                entry_price=scenario["entry"],
                atr=scenario["atr"],
                confidence=Decimal("0.8"),
            )

            # Calculate risk
            stop_distance = scenario["atr"] * Decimal("1.5")
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / scenario["balance"]

            print(f"\n{scenario['name']}:")
            print(f"  Position size: {position_size:.4f}")
            print(f"  Risk amount: ${risk_amount:.2f}")
            print(f"  Risk percent: {risk_pct:.3%}")

            # Verify risk is within limits
            assert risk_pct <= Decimal("0.005"), \
                f"{scenario['name']}: Risk too high!"
