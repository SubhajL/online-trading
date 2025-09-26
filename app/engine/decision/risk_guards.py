"""
Risk management guards to prevent catastrophic losses.

CRITICAL: These guards are the last line of defense against account destruction.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass
class RiskGuardConfig:
    """Configuration for risk guards."""
    # Daily loss limit
    daily_loss_limit_pct: Decimal = Decimal("0.02")  # 2% max daily loss

    # Position limits
    max_positions: int = 5
    max_correlated_positions: int = 3

    # Drawdown limit
    max_drawdown_pct: Decimal = Decimal("0.10")  # 10% max drawdown
    lookback_days: int = 30

    # Correlation limit
    correlation_threshold: Decimal = Decimal("0.7")

    # State persistence
    state_file: Optional[Path] = None


class DailyLossGuard:
    """Prevents excessive daily losses."""

    def __init__(self, config: dict) -> None:
        self.max_daily_loss_pct = config["max_daily_loss_pct"]
        self.lookback_hours = config.get("lookback_hours", 24)
        self.trades: List[Dict] = []

    def add_trade_result(self, pnl: Decimal, timestamp: datetime) -> None:
        """Record a trade result."""
        self.trades.append({
            "pnl": pnl,
            "timestamp": timestamp
        })
        self._cleanup_old_trades()

    def can_trade(self, account_balance: Decimal) -> Tuple[bool, str]:
        """Check if trading is allowed based on daily losses."""
        self._cleanup_old_trades()

        # Calculate total P&L for the day
        total_pnl = sum(trade["pnl"] for trade in self.trades)

        if total_pnl >= 0:
            return True, "Within daily loss limit"

        # Check if loss exceeds limit
        loss_pct = abs(total_pnl) / account_balance

        if loss_pct >= self.max_daily_loss_pct:
            return False, f"Daily loss limit exceeded: {loss_pct:.2%} >= {self.max_daily_loss_pct:.2%}"

        return True, "Within daily loss limit"

    def _cleanup_old_trades(self) -> None:
        """Remove trades older than lookback period."""
        cutoff = datetime.now() - timedelta(hours=self.lookback_hours)
        self.trades = [t for t in self.trades if t["timestamp"] > cutoff]

    def get_daily_pnl(self) -> Decimal:
        """Get total P&L for the day."""
        self._cleanup_old_trades()
        return sum(trade["pnl"] for trade in self.trades)


class MaxPositionsGuard:
    """Limits the number of concurrent positions."""

    def __init__(self, config: dict) -> None:
        self.max_positions = config["max_positions"]
        self.max_correlated_positions = config["max_correlated_positions"]
        self.open_positions: Dict[str, str] = {}  # symbol -> correlation_group
        self.correlation_groups: Dict[str, List[str]] = defaultdict(list)

    def add_position(self, symbol: str, correlation_group: str) -> None:
        """Add an open position."""
        if symbol not in self.open_positions:
            self.open_positions[symbol] = correlation_group
            self.correlation_groups[correlation_group].append(symbol)

    def remove_position(self, symbol: str) -> None:
        """Remove a closed position."""
        if symbol in self.open_positions:
            group = self.open_positions[symbol]
            del self.open_positions[symbol]
            self.correlation_groups[group].remove(symbol)
            if not self.correlation_groups[group]:
                del self.correlation_groups[group]

    def can_open_position(self, symbol: str, correlation_group: str) -> Tuple[bool, str]:
        """Check if a new position can be opened."""
        # Check total positions
        if len(self.open_positions) >= self.max_positions:
            return False, f"Maximum positions reached: {len(self.open_positions)}/{self.max_positions}"

        # Check correlated positions
        group_positions = len(self.correlation_groups.get(correlation_group, []))
        if group_positions >= self.max_correlated_positions:
            return False, f"Maximum correlated positions in {correlation_group}: {group_positions}/{self.max_correlated_positions}"

        return True, "Position limits OK"

    def get_open_position_count(self) -> int:
        """Get number of open positions."""
        return len(self.open_positions)


class DrawdownGuard:
    """Prevents trading during excessive drawdown."""

    def __init__(self, config: dict) -> None:
        self.max_drawdown_pct = config["max_drawdown_pct"]
        self.lookback_days = config.get("lookback_days", 30)
        self.balance_history: List[Dict] = []
        self.peak_balance = Decimal("0")

    def update_balance(self, balance: Decimal, timestamp: datetime) -> None:
        """Update balance history and track peak."""
        self.balance_history.append({
            "balance": balance,
            "timestamp": timestamp
        })
        self._cleanup_old_history()

        # Update peak balance
        if balance > self.peak_balance:
            self.peak_balance = balance
            logger.info(f"New peak balance: ${self.peak_balance:,.2f}")

    def can_trade(self, current_balance: Decimal) -> Tuple[bool, str]:
        """Check if trading allowed based on drawdown."""
        if self.peak_balance == 0:
            # No history yet
            self.peak_balance = current_balance
            return True, "No drawdown history"

        # Calculate current drawdown
        drawdown = (self.peak_balance - current_balance) / self.peak_balance

        if drawdown >= self.max_drawdown_pct:
            return False, f"Drawdown limit exceeded: {drawdown:.2%} >= {self.max_drawdown_pct:.2%}"

        return True, f"Within drawdown limit: {drawdown:.2%}"

    def _cleanup_old_history(self) -> None:
        """Remove old balance history."""
        cutoff = datetime.now() - timedelta(days=self.lookback_days)
        self.balance_history = [h for h in self.balance_history if h["timestamp"] > cutoff]

        # Recalculate peak from remaining history
        if self.balance_history:
            self.peak_balance = max(h["balance"] for h in self.balance_history)


class CorrelationGuard:
    """Prevents opening too many correlated positions."""

    def __init__(self, config: dict) -> None:
        self.max_correlation = config["max_correlation"]
        self.lookback_periods = config.get("lookback_periods", 20)
        self.open_positions: List[str] = []

    def add_position(self, symbol: str) -> None:
        """Add an open position."""
        if symbol not in self.open_positions:
            self.open_positions.append(symbol)

    def remove_position(self, symbol: str) -> None:
        """Remove a closed position."""
        if symbol in self.open_positions:
            self.open_positions.remove(symbol)

    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """Check if position can be opened based on correlation."""
        for existing_symbol in self.open_positions:
            correlation = self.get_correlation(symbol, existing_symbol)

            if correlation > self.max_correlation:
                return False, f"High correlation ({correlation:.2f}) with {existing_symbol}"

        return True, "Correlation check passed"

    def get_correlation(self, symbol1: str, symbol2: str) -> Decimal:
        """Get correlation between two symbols."""
        # This would normally calculate actual correlation from price data
        # For now, use simple rules

        # Same base currency = high correlation
        base1 = symbol1[:3]
        base2 = symbol2[:3]

        if base1 == base2:
            return Decimal("0.9")

        # Crypto correlation
        crypto_symbols = ["BTC", "ETH", "BNB", "SOL"]
        if any(s in symbol1 for s in crypto_symbols) and any(s in symbol2 for s in crypto_symbols):
            return Decimal("0.7")

        # Default low correlation
        return Decimal("0.3")


class RiskGuardManager:
    """Main risk guard manager that combines all guards."""

    def __init__(self, config: RiskGuardConfig) -> None:
        self.config = config

        # Initialize guards
        self.daily_loss_guard = DailyLossGuard({
            "max_daily_loss_pct": config.daily_loss_limit_pct,
            "lookback_hours": 24
        })

        self.positions_guard = MaxPositionsGuard({
            "max_positions": config.max_positions,
            "max_correlated_positions": config.max_correlated_positions
        })

        self.drawdown_guard = DrawdownGuard({
            "max_drawdown_pct": config.max_drawdown_pct,
            "lookback_days": config.lookback_days
        })

        self.correlation_guard = CorrelationGuard({
            "max_correlation": config.correlation_threshold,
            "lookback_periods": 20
        })

        # Emergency stop flag
        self.emergency_stop = False
        self.emergency_reason = ""

        # Account balance tracking
        self._account_balance = Decimal("100000")  # Default starting balance

        # Load saved state if available
        if config.state_file:
            self.load_state()

    def can_trade(self, symbol: str, account_balance: Decimal) -> Tuple[bool, List[str]]:
        """Check if trading is allowed by ALL guards."""
        reasons = []
        can_trade = True

        # Check emergency stop
        if self.emergency_stop:
            return False, [f"Emergency stop active: {self.emergency_reason}"]

        # Check daily loss
        daily_ok, daily_reason = self.daily_loss_guard.can_trade(account_balance)
        if not daily_ok:
            can_trade = False
            reasons.append(daily_reason)

        # Check drawdown
        drawdown_ok, drawdown_reason = self.drawdown_guard.can_trade(account_balance)
        if not drawdown_ok:
            can_trade = False
            reasons.append(drawdown_reason)

        # Check position limits (assuming default correlation group)
        positions_ok, positions_reason = self.positions_guard.can_open_position(symbol, "default")
        if not positions_ok:
            can_trade = False
            reasons.append(positions_reason)

        # Check correlation
        correlation_ok, correlation_reason = self.correlation_guard.can_open_position(symbol)
        if not correlation_ok:
            can_trade = False
            reasons.append(correlation_reason)

        if can_trade:
            reasons = ["All risk guards passed"]

        # Log decision
        logger.info(f"Risk guards for {symbol}: {can_trade} - {', '.join(reasons)}")

        return can_trade, reasons

    def record_trade_result(self, symbol: str, pnl: Decimal, timestamp: datetime) -> None:
        """Record a completed trade."""
        self.daily_loss_guard.add_trade_result(pnl, timestamp)

        if pnl < 0:
            logger.warning(f"Loss recorded: {symbol} ${pnl:.2f}")

    def add_open_position(self, symbol: str, correlation_group: str = "default") -> None:
        """Add a new open position."""
        self.positions_guard.add_position(symbol, correlation_group)
        self.correlation_guard.add_position(symbol)

    def close_position(self, symbol: str) -> None:
        """Remove a closed position."""
        self.positions_guard.remove_position(symbol)
        self.correlation_guard.remove_position(symbol)

    def update_account_balance(self, balance: Decimal) -> None:
        """Update account balance for drawdown tracking."""
        self._account_balance = balance
        self.drawdown_guard.update_balance(balance, datetime.now())

    def get_account_balance(self) -> Decimal:
        """Get current account balance."""
        return self._account_balance

    def emergency_stop_trading(self, reason: str) -> None:
        """Emergency stop all trading."""
        self.emergency_stop = True
        self.emergency_reason = reason
        logger.critical(f"EMERGENCY STOP ACTIVATED: {reason}")

    def resume_trading(self) -> None:
        """Resume trading after emergency stop."""
        self.emergency_stop = False
        self.emergency_reason = ""
        logger.info("Trading resumed after emergency stop")

    def get_daily_pnl(self) -> Decimal:
        """Get current daily P&L."""
        return self.daily_loss_guard.get_daily_pnl()

    def get_open_position_count(self) -> int:
        """Get number of open positions."""
        return self.positions_guard.get_open_position_count()

    def save_state(self) -> None:
        """Save current state to file."""
        if not self.config.state_file:
            return

        state = {
            "daily_trades": [
                {
                    "pnl": str(t["pnl"]),
                    "timestamp": t["timestamp"].isoformat()
                }
                for t in self.daily_loss_guard.trades
            ],
            "open_positions": dict(self.positions_guard.open_positions),
            "peak_balance": str(self.drawdown_guard.peak_balance),
            "emergency_stop": self.emergency_stop,
            "emergency_reason": self.emergency_reason,
            "saved_at": datetime.now().isoformat()
        }

        with open(self.config.state_file, 'w') as f:
            json.dump(state, f, indent=2)

        logger.debug(f"Risk guard state saved to {self.config.state_file}")

    def load_state(self) -> None:
        """Load state from file."""
        if not self.config.state_file or not self.config.state_file.exists():
            return

        try:
            with open(self.config.state_file, 'r') as f:
                state = json.load(f)

            # Restore daily trades
            self.daily_loss_guard.trades = [
                {
                    "pnl": Decimal(t["pnl"]),
                    "timestamp": datetime.fromisoformat(t["timestamp"])
                }
                for t in state.get("daily_trades", [])
            ]

            # Restore open positions
            for symbol, group in state.get("open_positions", {}).items():
                self.positions_guard.add_position(symbol, group)

            # Restore peak balance
            self.drawdown_guard.peak_balance = Decimal(state.get("peak_balance", "0"))

            # Restore emergency stop
            self.emergency_stop = state.get("emergency_stop", False)
            self.emergency_reason = state.get("emergency_reason", "")

            logger.info(f"Risk guard state loaded from {self.config.state_file}")

        except Exception as e:
            logger.error(f"Failed to load risk guard state: {e}")

    def get_status_report(self) -> dict:
        """Get comprehensive status report."""
        return {
            "emergency_stop": self.emergency_stop,
            "daily_pnl": float(self.get_daily_pnl()),
            "open_positions": self.get_open_position_count(),
            "max_positions": self.config.max_positions,
            "daily_loss_limit": float(self.config.daily_loss_limit_pct),
            "max_drawdown": float(self.config.max_drawdown_pct),
            "guards": {
                "daily_loss": self.daily_loss_guard.can_trade(Decimal("100000"))[0],
                "positions": self.positions_guard.can_open_position("TEST", "default")[0],
                "drawdown": self.drawdown_guard.can_trade(Decimal("100000"))[0],
            }
        }