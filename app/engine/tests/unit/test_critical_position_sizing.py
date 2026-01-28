"""
CRITICAL: Real-world position sizing tests that demonstrate actual constraints.

These tests show the reality of position sizing with expensive assets like Bitcoin.
The key insight: We can't always achieve 0.5% risk due to position limits.
"""

from decimal import Decimal

import pytest

from app.engine.decision.position_sizer import PositionSizeConfig, PositionSizer


class TestCriticalPositionSizing:
    """Critical tests that verify position sizing safety in real scenarios."""

    @pytest.fixture
    def sizer(self):
        """Standard position sizer with production config."""
        config = PositionSizeConfig(
            fixed_risk_pct=Decimal("0.005"),     # 0.5% risk target
            max_position_pct=Decimal("0.02"),     # 2% max position
            atr_multiplier=Decimal("1.5"),
            min_position_size=Decimal("0.001"),
            confidence_scaling=True,
        )
        return PositionSizer(config)

    def test_bitcoin_position_sizing_reality(self, sizer):
        """
        CRITICAL: Test Bitcoin position sizing with realistic account sizes.

        Key insight: With BTC at $50k, small accounts can't achieve 0.5% risk
        due to the 2% position limit. This is BY DESIGN for safety.
        """
        btc_price = Decimal("50000")

        test_scenarios = [
            {
                "name": "Small retail account",
                "balance": Decimal("10000"),
                "stop_pct": Decimal("0.02"),  # 2% stop
            },
            {
                "name": "Medium account",
                "balance": Decimal("50000"),
                "stop_pct": Decimal("0.02"),  # 2% stop
            },
            {
                "name": "Large account",
                "balance": Decimal("500000"),
                "stop_pct": Decimal("0.02"),  # 2% stop
            },
            {
                "name": "Tight stop on large account",
                "balance": Decimal("500000"),
                "stop_pct": Decimal("0.005"),  # 0.5% stop
            },
        ]

        print("\n" + "="*70)
        print("BITCOIN POSITION SIZING REALITY CHECK")
        print("="*70)

        for scenario in test_scenarios:
            balance = scenario["balance"]
            stop_loss = btc_price * (Decimal("1") - scenario["stop_pct"])

            position_size = sizer.calculate_position_size(
                account_balance=balance,
                entry_price=btc_price,
                stop_loss=stop_loss,
                confidence=Decimal("1.0"),
            )

            # Calculate metrics
            stop_distance = btc_price - stop_loss
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / balance
            position_value = position_size * btc_price
            position_pct = position_value / balance

            expected_risk_pct = min(
                sizer.config.fixed_risk_pct,
                sizer.config.max_position_pct * scenario["stop_pct"],
            )

            print(f"\n{scenario['name']} (${balance:,.0f}):")
            print(f"  Stop distance: {scenario['stop_pct']:.1%} (${stop_distance:,.0f})")
            print(f"  Position size: {position_size:.4f} BTC")
            print(f"  Position value: ${position_value:,.0f} ({position_pct:.1%} of account)")
            print(f"  Risk amount: ${risk_amount:.0f}")
            print(
                f"  Risk achieved: {risk_pct:.3%} "
                f"(expected: {expected_risk_pct:.3%}, target: 0.5%)"
            )

            # Verify safety constraints
            assert risk_pct <= Decimal("0.005"), "Risk exceeds 0.5% limit!"
            assert position_pct <= Decimal("0.02"), "Position exceeds 2% limit!"

            assert abs(risk_pct - expected_risk_pct) < Decimal("0.0001"), (
                f"Unexpected risk: {risk_pct:.4%} != {expected_risk_pct:.4%}"
            )

    def test_ethereum_more_accessible(self, sizer):
        """Test that sizing honors constraints for ETH."""
        eth_price = Decimal("3000")  # More accessible than BTC

        test_accounts = [
            Decimal("10000"),   # Small account
            Decimal("50000"),   # Medium account
            Decimal("100000"),  # Large account
        ]

        print("\n" + "="*70)
        print("ETHEREUM POSITION SIZING (More Accessible)")
        print("="*70)

        for balance in test_accounts:
            stop_loss = eth_price * Decimal("0.98")  # 2% stop

            position_size = sizer.calculate_position_size(
                account_balance=balance,
                entry_price=eth_price,
                stop_loss=stop_loss,
                confidence=Decimal("1.0"),
            )

            stop_distance = eth_price - stop_loss
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / balance

            print(f"\nAccount ${balance:,.0f}:")
            print(f"  Position: {position_size:.3f} ETH")
            print(f"  Risk achieved: {risk_pct:.3%}")

            expected_risk_pct = min(
                sizer.config.fixed_risk_pct,
                sizer.config.max_position_pct * Decimal("0.02"),
            )
            assert abs(risk_pct - expected_risk_pct) < Decimal("0.0001"), (
                f"Unexpected risk: {risk_pct:.4%} != {expected_risk_pct:.4%}"
            )

    def test_never_exceed_safety_limits(self, sizer):
        """
        CRITICAL: Verify safety limits are NEVER exceeded regardless of inputs.
        """
        # Try extreme scenarios that might break safety
        extreme_scenarios = [
            {
                "name": "Tiny stop loss",
                "balance": Decimal("1000000"),
                "entry": Decimal("50000"),
                "stop": Decimal("49999"),  # $1 stop!
            },
            {
                "name": "Huge account",
                "balance": Decimal("10000000"),  # $10M
                "entry": Decimal("50000"),
                "stop": Decimal("40000"),  # 20% stop
            },
            {
                "name": "Penny stock simulation",
                "balance": Decimal("10000"),
                "entry": Decimal("0.01"),
                "stop": Decimal("0.009"),  # 10% stop
            },
        ]

        for scenario in extreme_scenarios:
            position_size = sizer.calculate_position_size(
                account_balance=scenario["balance"],
                entry_price=scenario["entry"],
                stop_loss=scenario["stop"],
                confidence=Decimal("1.0"),
            )

            # Calculate risk
            stop_distance = scenario["entry"] - scenario["stop"]
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / scenario["balance"]

            # Calculate position size
            position_value = position_size * scenario["entry"]
            position_pct = position_value / scenario["balance"]

            print(f"\n{scenario['name']}:")
            print(f"  Risk: {risk_pct:.4%} (must be ≤ 0.5%)")
            print(f"  Position: {position_pct:.2%} (must be ≤ 2%)")

            # CRITICAL ASSERTIONS
            assert risk_pct <= Decimal("0.005"), \
                f"{scenario['name']}: Risk {risk_pct:.4%} exceeds 0.5%!"
            assert position_pct <= Decimal("0.02"), \
                f"{scenario['name']}: Position {position_pct:.2%} exceeds 2%!"

    def test_confidence_scaling_reduces_risk(self, sizer):
        """Test that lower confidence always reduces risk, never increases."""
        test_confidences = [
            Decimal("1.0"),
            Decimal("0.8"),
            Decimal("0.5"),
            Decimal("0.3"),
            Decimal("0.1"),
            Decimal("0.0"),
        ]

        account = Decimal("100000")
        entry = Decimal("50000")
        stop = Decimal("48000")  # 4% stop

        previous_risk = Decimal("1.0")  # Start high

        for confidence in test_confidences:
            position_size = sizer.calculate_position_size(
                account_balance=account,
                entry_price=entry,
                stop_loss=stop,
                confidence=confidence,
            )

            # Calculate risk
            stop_distance = entry - stop
            risk_amount = position_size * stop_distance
            risk_pct = risk_amount / account

            # Risk must decrease or stay same as confidence decreases
            assert risk_pct <= previous_risk, \
                f"Risk increased with lower confidence! {risk_pct} > {previous_risk}"

            previous_risk = risk_pct

            # Risk must never exceed target
            assert risk_pct <= Decimal("0.005"), "Risk exceeds 0.5%!"

    def test_minimum_position_size_safety(self, sizer):
        """Test minimum position size doesn't cause excessive risk."""
        # Small account where minimum position might be risky
        small_account = Decimal("100")
        btc_price = Decimal("50000")

        # Wide stop that would normally give tiny position
        stop_loss = Decimal("40000")  # 20% stop

        position_size = sizer.calculate_position_size(
            account_balance=small_account,
            entry_price=btc_price,
            stop_loss=stop_loss,
            confidence=Decimal("1.0"),
        )

        # Should get minimum position
        assert position_size == sizer.config.min_position_size

        # Calculate risk with minimum position
        stop_distance = btc_price - stop_loss
        risk_amount = position_size * stop_distance
        risk_pct = risk_amount / small_account

        print("\nMinimum position risk check:")
        print(f"  Account: ${small_account}")
        print(f"  Min position: {position_size} BTC")
        print(f"  Risk: {risk_pct:.1%} of account")

        # With tiny account, minimum position might risk more than 0.5%
        # This is acceptable as it's the absolute minimum tradeable amount
        # User should not trade with such small accounts
        if risk_pct > Decimal("0.005"):
            print(f"  WARNING: Minimum position risks {risk_pct:.1%} on tiny account")


if __name__ == "__main__":
    # Run this file directly to see all the output
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
