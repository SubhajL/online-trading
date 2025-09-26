"""
CRITICAL: Risk management guard tests to ensure all safety mechanisms work.

These guards prevent catastrophic losses from:
1. Daily loss limits
2. Maximum position counts
3. Drawdown limits
4. Correlation limits
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from app.engine.decision.risk_guards import (
    RiskGuardConfig,
    RiskGuardManager,
    DailyLossGuard,
    MaxPositionsGuard,
    DrawdownGuard,
    CorrelationGuard,
)


class TestDailyLossGuard:
    """Test daily loss limit enforcement."""

    @pytest.fixture
    def guard(self):
        """Create daily loss guard with 2% limit."""
        config = {
            "max_daily_loss_pct": Decimal("0.02"),  # 2% daily loss limit
            "lookback_hours": 24,
        }
        return DailyLossGuard(config)

    def test_blocks_trading_after_daily_loss_limit(self, guard):
        """CRITICAL: Must stop trading after 2% daily loss."""
        account_balance = Decimal("100000")

        # Simulate losses throughout the day
        losses = [
            {"amount": Decimal("-500"), "timestamp": datetime.now() - timedelta(hours=10)},
            {"amount": Decimal("-800"), "timestamp": datetime.now() - timedelta(hours=5)},
            {"amount": Decimal("-300"), "timestamp": datetime.now() - timedelta(hours=2)},
            {"amount": Decimal("-500"), "timestamp": datetime.now() - timedelta(hours=1)},
        ]

        # Add losses to guard
        for loss in losses:
            guard.add_trade_result(loss["amount"], loss["timestamp"])

        # Total loss: $2,100 (2.1% of account)
        total_loss = sum(l["amount"] for l in losses)
        loss_pct = abs(total_loss) / account_balance

        # Check if trading is blocked
        can_trade, reason = guard.can_trade(account_balance)

        assert can_trade is False, "Should block trading after 2% loss"
        assert "daily loss limit" in reason.lower()
        assert loss_pct > Decimal("0.02"), f"Loss {loss_pct:.2%} exceeds 2% limit"

    def test_allows_trading_within_limit(self, guard):
        """Test trading allowed when under daily limit."""
        account_balance = Decimal("100000")

        # Small losses under 2%
        losses = [
            {"amount": Decimal("-300"), "timestamp": datetime.now() - timedelta(hours=5)},
            {"amount": Decimal("-400"), "timestamp": datetime.now() - timedelta(hours=2)},
        ]

        for loss in losses:
            guard.add_trade_result(loss["amount"], loss["timestamp"])

        # Total: $700 (0.7% loss)
        can_trade, reason = guard.can_trade(account_balance)

        assert can_trade is True
        assert reason == "Within daily loss limit"

    def test_resets_after_24_hours(self, guard):
        """Test that losses older than 24 hours don't count."""
        account_balance = Decimal("100000")

        # Old loss (25 hours ago)
        old_loss = {"amount": Decimal("-3000"), "timestamp": datetime.now() - timedelta(hours=25)}
        guard.add_trade_result(old_loss["amount"], old_loss["timestamp"])

        # Recent small loss
        recent_loss = {"amount": Decimal("-100"), "timestamp": datetime.now()}
        guard.add_trade_result(recent_loss["amount"], recent_loss["timestamp"])

        can_trade, reason = guard.can_trade(account_balance)

        assert can_trade is True, "Old losses should not block trading"


class TestMaxPositionsGuard:
    """Test maximum concurrent positions limit."""

    @pytest.fixture
    def guard(self):
        """Create max positions guard."""
        config = {
            "max_positions": 5,
            "max_correlated_positions": 3,
        }
        return MaxPositionsGuard(config)

    def test_blocks_when_max_positions_reached(self, guard):
        """Test blocking new positions at limit."""
        # Add 5 open positions (at limit)
        open_positions = [
            {"symbol": "BTCUSDT", "correlation_group": "crypto"},
            {"symbol": "ETHUSDT", "correlation_group": "crypto"},
            {"symbol": "BNBUSDT", "correlation_group": "crypto"},
            {"symbol": "EURUSD", "correlation_group": "forex"},
            {"symbol": "GBPUSD", "correlation_group": "forex"},
        ]

        for pos in open_positions:
            guard.add_position(pos["symbol"], pos["correlation_group"])

        # Try to add 6th position
        can_trade, reason = guard.can_open_position("SOLUSDT", "crypto")

        assert can_trade is False
        assert "maximum positions" in reason.lower()

    def test_blocks_correlated_positions(self, guard):
        """Test blocking too many correlated positions."""
        # Add 3 crypto positions (at correlation limit)
        crypto_positions = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        for symbol in crypto_positions:
            guard.add_position(symbol, "crypto")

        # Try to add 4th crypto position
        can_trade, reason = guard.can_open_position("SOLUSDT", "crypto")

        assert can_trade is False
        assert "correlated positions" in reason.lower()

        # But can still add non-crypto position
        can_trade, reason = guard.can_open_position("EURUSD", "forex")
        assert can_trade is True

    def test_position_removal(self, guard):
        """Test that closed positions free up slots."""
        # Fill up positions with different groups to avoid correlation limit
        guard.add_position("SYMBOL0", "crypto")
        guard.add_position("SYMBOL1", "crypto")
        guard.add_position("SYMBOL2", "crypto")  # Max 3 in crypto group
        guard.add_position("SYMBOL3", "forex")
        guard.add_position("SYMBOL4", "forex")  # Total 5 positions (at max)

        # Should be blocked due to max positions
        can_trade, reason = guard.can_open_position("NEWSYMBOL", "stocks")
        assert can_trade is False
        assert "maximum positions" in reason.lower()

        # Close one position
        guard.remove_position("SYMBOL0")

        # Should now allow new position
        can_trade, reason = guard.can_open_position("NEWSYMBOL", "stocks")
        assert can_trade is True


class TestDrawdownGuard:
    """Test maximum drawdown protection."""

    @pytest.fixture
    def guard(self):
        """Create drawdown guard with 10% limit."""
        config = {
            "max_drawdown_pct": Decimal("0.10"),  # 10% max drawdown
            "lookback_days": 30,
        }
        return DrawdownGuard(config)

    def test_blocks_trading_during_drawdown(self, guard):
        """Test that trading stops during significant drawdown."""
        # Set peak balance
        peak_balance = Decimal("100000")
        guard.update_balance(peak_balance, datetime.now() - timedelta(days=10))

        # Simulate drawdown to 88k (12% drawdown)
        current_balance = Decimal("88000")

        can_trade, reason = guard.can_trade(current_balance)

        assert can_trade is False
        assert "drawdown limit" in reason.lower()

        drawdown_pct = (peak_balance - current_balance) / peak_balance
        assert drawdown_pct > Decimal("0.10"), "Drawdown exceeds 10% limit"

    def test_allows_trading_within_drawdown_limit(self, guard):
        """Test trading allowed with acceptable drawdown."""
        # Peak at 100k
        guard.update_balance(Decimal("100000"), datetime.now() - timedelta(days=5))

        # Current at 93k (7% drawdown)
        current_balance = Decimal("93000")

        can_trade, reason = guard.can_trade(current_balance)

        assert can_trade is True
        assert "within drawdown limit" in reason.lower()

    def test_tracks_new_highs(self, guard):
        """Test that guard tracks new account highs."""
        # Initial balance
        guard.update_balance(Decimal("100000"), datetime.now() - timedelta(days=10))

        # New high
        guard.update_balance(Decimal("110000"), datetime.now() - timedelta(days=5))

        # Small drawdown from new high
        current = Decimal("105000")  # 4.5% drawdown from 110k

        can_trade, reason = guard.can_trade(current)

        assert can_trade is True
        # Drawdown calculated from 110k, not 100k


class TestCorrelationGuard:
    """Test correlation-based position limits."""

    @pytest.fixture
    def guard(self):
        """Create correlation guard."""
        config = {
            "max_correlation": Decimal("0.7"),
            "lookback_periods": 20,
        }
        return CorrelationGuard(config)

    def test_blocks_highly_correlated_positions(self, guard):
        """Test blocking positions with high correlation to existing."""
        # Mock correlation data
        guard.get_correlation = Mock(return_value=Decimal("0.85"))

        # Add existing position
        guard.add_position("BTCUSDT")

        # Try to add highly correlated position
        can_trade, reason = guard.can_open_position("ETHUSDT")

        assert can_trade is False
        assert "correlation" in reason.lower()

    def test_allows_uncorrelated_positions(self, guard):
        """Test allowing positions with low correlation."""
        # Mock low correlation
        guard.get_correlation = Mock(return_value=Decimal("0.3"))

        # Add existing position
        guard.add_position("BTCUSDT")

        # Try to add uncorrelated position
        can_trade, reason = guard.can_open_position("EURUSD")

        assert can_trade is True


class TestRiskGuardManager:
    """Test the main risk guard manager that combines all guards."""

    @pytest.fixture
    def manager(self):
        """Create risk guard manager with all guards."""
        config = RiskGuardConfig(
            daily_loss_limit_pct=Decimal("0.02"),
            max_positions=5,
            max_correlated_positions=3,
            max_drawdown_pct=Decimal("0.10"),
            correlation_threshold=Decimal("0.7"),
        )
        return RiskGuardManager(config)

    def test_all_guards_must_pass(self, manager):
        """Test that ALL guards must approve before allowing trade."""
        account_balance = Decimal("100000")

        # Set up a scenario where daily loss guard would block
        manager.record_trade_result(
            symbol="BTCUSDT",
            pnl=Decimal("-2100"),  # 2.1% loss
            timestamp=datetime.now()
        )

        # Even if other guards would pass, should still block
        can_trade, reasons = manager.can_trade(
            symbol="ETHUSDT",
            account_balance=account_balance
        )

        assert can_trade is False
        assert any("daily loss" in r.lower() for r in reasons)

    def test_provides_all_failure_reasons(self, manager):
        """Test that manager returns all reasons when multiple guards fail."""
        account_balance = Decimal("100000")

        # Trigger multiple guard failures
        # 1. Daily loss
        manager.record_trade_result("TEST1", Decimal("-2100"), datetime.now())

        # 2. Max positions
        for i in range(5):
            manager.add_open_position(f"SYMBOL{i}", "group1")

        can_trade, reasons = manager.can_trade("NEWSYMBOL", account_balance)

        assert can_trade is False
        assert len(reasons) >= 2, "Should have multiple failure reasons"

    def test_critical_stop_trading_flag(self, manager):
        """Test emergency stop trading functionality."""
        account_balance = Decimal("100000")

        # Should allow trading normally
        can_trade, _ = manager.can_trade("BTCUSDT", account_balance)
        assert can_trade is True

        # Activate emergency stop
        manager.emergency_stop_trading("System maintenance")

        # Should now block all trading
        can_trade, reasons = manager.can_trade("BTCUSDT", account_balance)
        assert can_trade is False
        assert "emergency stop" in reasons[0].lower()

        # Resume trading
        manager.resume_trading()

        # Should allow again
        can_trade, _ = manager.can_trade("BTCUSDT", account_balance)
        assert can_trade is True


class TestRiskGuardPersistence:
    """Test that risk guard state persists across restarts."""

    def test_saves_and_loads_state(self, tmp_path):
        """Test saving and loading guard state."""
        # Create manager with temp storage
        config = RiskGuardConfig(
            daily_loss_limit_pct=Decimal("0.02"),
            state_file=tmp_path / "risk_state.json"
        )

        manager1 = RiskGuardManager(config)

        # Add some state
        manager1.record_trade_result("BTCUSDT", Decimal("-500"), datetime.now())
        manager1.add_open_position("BTCUSDT", "crypto")

        # Save state
        manager1.save_state()

        # Create new manager (simulating restart)
        manager2 = RiskGuardManager(config)
        manager2.load_state()

        # Should have same state
        assert manager2.get_daily_pnl() == Decimal("-500")
        assert manager2.get_open_position_count() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])