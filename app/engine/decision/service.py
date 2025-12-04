"""
Decision service wrapper providing DecisionEngine interface.

This wraps the functional decision engine to provide the class-based
interface expected by main.py.
"""

import logging
from typing import Any

from ..adapters import RouterHTTPClient
from .engine import fuse_signals, generate_decision
from .risk_guards import RiskGuardManager

logger = logging.getLogger(__name__)


class DecisionEngine:
    """Decision engine service that integrates signal fusion and risk management."""

    def __init__(self, risk_manager: RiskGuardManager, router_client: RouterHTTPClient):
        """Initialize decision engine with required dependencies.

        Args:
            risk_manager: Risk management component
            router_client: Client for sending orders to router
        """
        self.risk_manager = risk_manager
        self.router_client = router_client
        self._running = False
        logger.info("DecisionEngine initialized")

    async def start(self):
        """Start the decision engine service."""
        self._running = True
        logger.info("DecisionEngine started")

    async def stop(self):
        """Stop the decision engine service."""
        self._running = False
        logger.info("DecisionEngine stopped")

    def process_signals(
        self, signals_raw: list[dict[str, Any]], regime: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Process raw signals with regime context.

        Args:
            signals_raw: Raw trading signals
            regime: Current market regime

        Returns:
            Fused signals with confidence scores
        """
        return fuse_signals(signals_raw, regime)

    def make_decision(
        self,
        signal: dict[str, Any],
        current_positions: list[dict[str, Any]],
        news_window: dict[str, Any] | None = None,
        funding_window: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make trading decision based on signal and current state.

        Args:
            signal: Trading signal to evaluate
            current_positions: Current open positions
            news_window: News event data if any
            funding_window: Funding rate data if any

        Returns:
            Trading decision or None if no action
        """
        # Check risk guards
        symbol = signal.get("symbol", "UNKNOWN")
        account_balance = self.risk_manager.get_account_balance()
        can_trade, reasons = self.risk_manager.can_trade(symbol, account_balance)

        if not can_trade:
            logger.warning(f"Signal rejected by risk guards: {reasons}")
            return None

        # Create decision
        return generate_decision(
            signal,
            self.risk_manager.get_account_balance(),
            current_positions,
            news_window,
            funding_window,
        )


class RiskManager:
    """Adapter to create RiskGuardManager from RiskParameters."""

    def __init__(self, risk_params):
        """Initialize with RiskParameters and create RiskGuardManager."""
        from .risk_guards import RiskGuardConfig

        # Map RiskParameters to RiskGuardConfig
        config = RiskGuardConfig(
            daily_loss_limit_pct=risk_params.max_daily_loss,
            max_positions=risk_params.max_open_positions,
            max_correlated_positions=max(1, risk_params.max_open_positions // 2),
            max_drawdown_pct=risk_params.max_drawdown,
            correlation_threshold=risk_params.max_correlation,
        )

        # Create the actual risk guard manager
        self._manager = RiskGuardManager(config)

    def __getattr__(self, name):
        """Forward all attribute access to the wrapped manager."""
        return getattr(self._manager, name)
