"""
Decision Engine

Main decision-making component that evaluates signals, applies risk management,
and generates trading decisions based on multiple inputs and filters.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from .risk_manager import RiskManager, RiskCheckResult
from ..types import (
    BaseEvent,
    TradingDecision,
    TradingDecisionEvent,
    SMCSignal,
    SMCSignalEvent,
    RetestSignal,
    RetestSignalEvent,
    TechnicalIndicators,
    FeaturesCalculatedEvent,
    OrderSide,
    OrderType,
    PositionSizing,
    MarketRegime,
    Position,
)
from ..bus import get_event_bus
from ..adapters import RouterHTTPClient


logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Main trading decision engine that:
    - Processes signals from various sources
    - Applies risk management rules
    - Generates final trading decisions
    - Manages position sizing and risk parameters
    - Coordinates with router for execution
    """

    def __init__(
        self,
        risk_manager: RiskManager,
        router_client: RouterHTTPClient,
        config: Dict = None,
    ):
        self.risk_manager = risk_manager
        self.router_client = router_client
        self.config = config or {}

        # Signal processing configuration
        self.min_signal_confidence = self.config.get("min_signal_confidence", 0.7)
        self.max_signals_per_decision = self.config.get("max_signals_per_decision", 3)
        self.decision_timeout_minutes = self.config.get("decision_timeout_minutes", 15)

        # Signal storage
        self._pending_signals: Dict[str, List[SMCSignal]] = {}  # symbol -> signals
        self._retest_signals: Dict[str, List[RetestSignal]] = {}
        self._latest_indicators: Dict[str, TechnicalIndicators] = {}

        # Decision tracking
        self._recent_decisions: List[TradingDecision] = []
        self._execution_queue: List[TradingDecision] = []

        # Market state
        self._market_regime: Dict[str, MarketRegime] = {}
        self._account_balance = Decimal("100000")  # Default
        self._current_positions: List[Position] = []

        self._event_bus = get_event_bus()
        self._running = False
        self._subscription_ids: List[str] = []

        # Statistics
        self._decisions_generated = 0
        self._decisions_executed = 0
        self._signals_processed = 0

        logger.info("DecisionEngine initialized")

    async def start(self):
        """Start the decision engine"""
        if self._running:
            logger.warning("DecisionEngine is already running")
            return

        self._running = True

        # Subscribe to relevant events
        subscription_configs = [
            (
                "smc_signal_handler",
                self._handle_smc_signal,
                [BaseEvent.EventType.SMC_SIGNAL],
            ),
            (
                "retest_signal_handler",
                self._handle_retest_signal,
                [BaseEvent.EventType.RETEST_SIGNAL],
            ),
            (
                "features_handler",
                self._handle_features_calculated,
                [BaseEvent.EventType.FEATURES_CALCULATED],
            ),
        ]

        for subscriber_id, handler, event_types in subscription_configs:
            sub_id = await self._event_bus.subscribe(
                subscriber_id=subscriber_id,
                handler=handler,
                event_types=event_types,
                priority=2,  # Lower priority to process after feature calculation
            )
            self._subscription_ids.append(sub_id)

        # Start background tasks
        asyncio.create_task(self._decision_processor())
        asyncio.create_task(self._execution_processor())
        asyncio.create_task(self._signal_cleanup())

        # Update account state
        await self._update_account_state()

        logger.info("DecisionEngine started")

    async def stop(self):
        """Stop the decision engine"""
        if not self._running:
            return

        self._running = False

        # Unsubscribe from events
        for sub_id in self._subscription_ids:
            await self._event_bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

        logger.info("DecisionEngine stopped")

    async def _handle_smc_signal(self, event: SMCSignalEvent):
        """Handle SMC signal events"""
        try:
            signal = event.signal
            symbol = signal.symbol

            # Add to pending signals
            if symbol not in self._pending_signals:
                self._pending_signals[symbol] = []

            self._pending_signals[symbol].append(signal)
            self._signals_processed += 1

            # Limit number of signals per symbol
            if len(self._pending_signals[symbol]) > self.max_signals_per_decision:
                self._pending_signals[symbol] = self._pending_signals[symbol][
                    -self.max_signals_per_decision :
                ]

            logger.debug(f"Added SMC signal for {symbol}: {signal.signal_type}")

        except Exception as e:
            logger.error(f"Error handling SMC signal: {e}")

    async def _handle_retest_signal(self, event: RetestSignalEvent):
        """Handle retest signal events"""
        try:
            signal = event.signal
            symbol = signal.symbol

            # Add to retest signals
            if symbol not in self._retest_signals:
                self._retest_signals[symbol] = []

            self._retest_signals[symbol].append(signal)

            # Limit number of retest signals
            if len(self._retest_signals[symbol]) > 5:
                self._retest_signals[symbol] = self._retest_signals[symbol][-5:]

            logger.debug(f"Added retest signal for {symbol}")

        except Exception as e:
            logger.error(f"Error handling retest signal: {e}")

    async def _handle_features_calculated(self, event: FeaturesCalculatedEvent):
        """Handle features calculated events"""
        try:
            indicators = event.features
            symbol = indicators.symbol

            # Store latest indicators
            self._latest_indicators[f"{symbol}_{indicators.timeframe.value}"] = (
                indicators
            )

            logger.debug(
                f"Updated indicators for {symbol} {indicators.timeframe.value}"
            )

        except Exception as e:
            logger.error(f"Error handling features calculated: {e}")

    async def _decision_processor(self):
        """Background task to process signals and generate decisions"""
        while self._running:
            try:
                await self._process_pending_signals()
                await asyncio.sleep(5)  # Process every 5 seconds

            except Exception as e:
                logger.error(f"Error in decision processor: {e}")
                await asyncio.sleep(10)

    async def _execution_processor(self):
        """Background task to execute approved decisions"""
        while self._running:
            try:
                await self._process_execution_queue()
                await asyncio.sleep(2)  # Process every 2 seconds

            except Exception as e:
                logger.error(f"Error in execution processor: {e}")
                await asyncio.sleep(5)

    async def _signal_cleanup(self):
        """Background task to clean up old signals"""
        while self._running:
            try:
                cutoff_time = datetime.utcnow() - timedelta(
                    minutes=self.decision_timeout_minutes
                )

                # Clean up SMC signals
                for symbol in list(self._pending_signals.keys()):
                    self._pending_signals[symbol] = [
                        s
                        for s in self._pending_signals[symbol]
                        if s.timestamp > cutoff_time
                    ]
                    if not self._pending_signals[symbol]:
                        del self._pending_signals[symbol]

                # Clean up retest signals
                for symbol in list(self._retest_signals.keys()):
                    self._retest_signals[symbol] = [
                        s
                        for s in self._retest_signals[symbol]
                        if s.timestamp > cutoff_time
                    ]
                    if not self._retest_signals[symbol]:
                        del self._retest_signals[symbol]

                await asyncio.sleep(60)  # Clean up every minute

            except Exception as e:
                logger.error(f"Error in signal cleanup: {e}")
                await asyncio.sleep(60)

    async def _process_pending_signals(self):
        """Process pending signals and generate decisions"""
        try:
            for symbol in list(self._pending_signals.keys()):
                signals = self._pending_signals[symbol]

                if not signals:
                    continue

                # Check if we have sufficient signals for decision
                high_confidence_signals = [
                    s for s in signals if s.confidence >= self.min_signal_confidence
                ]

                if high_confidence_signals:
                    decision = await self._generate_decision(
                        symbol, high_confidence_signals
                    )
                    if decision:
                        await self._evaluate_and_queue_decision(decision)

        except Exception as e:
            logger.error(f"Error processing pending signals: {e}")

    async def _generate_decision(
        self, symbol: str, signals: List[SMCSignal]
    ) -> Optional[TradingDecision]:
        """Generate trading decision from signals"""
        try:
            if not signals:
                return None

            # Determine consensus direction
            buy_signals = [s for s in signals if s.direction == OrderSide.BUY]
            sell_signals = [s for s in signals if s.direction == OrderSide.SELL]

            if len(buy_signals) > len(sell_signals):
                action = "BUY"
                relevant_signals = buy_signals
            elif len(sell_signals) > len(buy_signals):
                action = "SELL"
                relevant_signals = sell_signals
            else:
                # No consensus, skip
                return None

            # Calculate decision parameters
            strongest_signal = max(relevant_signals, key=lambda s: s.confidence)
            avg_confidence = sum(s.confidence for s in relevant_signals) / len(
                relevant_signals
            )

            # Get current market price
            market_prices = await self.router_client.get_market_prices([symbol])
            current_price = market_prices.get(symbol)

            if not current_price:
                logger.warning(f"No market price available for {symbol}")
                return None

            # Calculate position sizing
            position_sizing = self.risk_manager.calculate_position_size(
                decision=TradingDecision(
                    symbol=symbol,
                    timestamp=datetime.utcnow(),
                    action=action,
                    entry_price=strongest_signal.entry_price,
                    stop_loss=strongest_signal.stop_loss,
                    take_profit=strongest_signal.take_profit,
                    confidence=avg_confidence,
                    reasoning="Initial calculation",
                ),
                account_balance=self._account_balance,
                current_price=current_price,
            )

            # Get latest technical indicators
            indicators_key = f"{symbol}_1h"  # Default to 1h timeframe
            indicators = self._latest_indicators.get(indicators_key)

            # Compile reasoning
            signal_descriptions = [
                f"{s.signal_type}({s.confidence:.2f})" for s in relevant_signals
            ]
            reasoning = f"Decision based on {len(relevant_signals)} signals: {', '.join(signal_descriptions)}"

            # Add confluence factors
            confluence_factors = []
            if indicators:
                if indicators.rsi_14:
                    if action == "BUY" and indicators.rsi_14 < 40:
                        confluence_factors.append("RSI oversold")
                    elif action == "SELL" and indicators.rsi_14 > 60:
                        confluence_factors.append("RSI overbought")

                if indicators.ema_21 and indicators.ema_50:
                    if action == "BUY" and indicators.ema_21 > indicators.ema_50:
                        confluence_factors.append("EMA bullish")
                    elif action == "SELL" and indicators.ema_21 < indicators.ema_50:
                        confluence_factors.append("EMA bearish")

            if confluence_factors:
                reasoning += f". Confluence: {', '.join(confluence_factors)}"

            # Create trading decision
            decision = TradingDecision(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                action=action,
                entry_price=strongest_signal.entry_price,
                quantity=position_sizing.position_size,
                order_type=OrderType.LIMIT,
                stop_loss=strongest_signal.stop_loss,
                take_profit=strongest_signal.take_profit,
                position_sizing=position_sizing,
                signals=relevant_signals,
                technical_indicators=indicators,
                market_regime=self._market_regime.get(symbol),
                confidence=avg_confidence,
                reasoning=reasoning,
                risk_reward_ratio=self._calculate_risk_reward_ratio(
                    strongest_signal.entry_price,
                    strongest_signal.stop_loss,
                    strongest_signal.take_profit,
                ),
                volatility_filter=True,
            )

            self._decisions_generated += 1
            logger.info(
                f"Generated decision for {symbol}: {action} at {strongest_signal.entry_price}"
            )

            return decision

        except Exception as e:
            logger.error(f"Error generating decision for {symbol}: {e}")
            return None

    def _calculate_risk_reward_ratio(
        self,
        entry_price: Decimal,
        stop_loss: Optional[Decimal],
        take_profit: Optional[Decimal],
    ) -> Optional[Decimal]:
        """Calculate risk-reward ratio"""
        try:
            if not stop_loss or not take_profit:
                return None

            risk = abs(entry_price - stop_loss)
            reward = abs(take_profit - entry_price)

            if risk > 0:
                return reward / risk
            else:
                return None

        except Exception as e:
            logger.error(f"Error calculating risk-reward ratio: {e}")
            return None

    async def _evaluate_and_queue_decision(self, decision: TradingDecision):
        """Evaluate decision through risk management and queue for execution"""
        try:
            # Perform comprehensive risk check
            risk_result = self.risk_manager.check_risk_limits(
                decision=decision,
                account_balance=self._account_balance,
                current_positions=self._current_positions,
            )

            if risk_result.approved:
                # Additional checks with router service
                router_risk_check = await self.router_client.check_risk_limits(decision)

                if router_risk_check.get("approved", False):
                    # Add to execution queue
                    self._execution_queue.append(decision)

                    # Publish decision event
                    event = TradingDecisionEvent(
                        timestamp=datetime.utcnow(),
                        symbol=decision.symbol,
                        decision=decision,
                    )
                    await self._event_bus.publish(event, priority=8)

                    logger.info(
                        f"Decision approved and queued for execution: {decision.symbol} {decision.action}"
                    )
                else:
                    logger.warning(
                        f"Decision rejected by router risk check: {router_risk_check}"
                    )
            else:
                logger.warning(
                    f"Decision rejected by risk manager: {risk_result.reasons}"
                )

            # Store decision for analysis
            self._recent_decisions.append(decision)

            # Keep only recent decisions
            if len(self._recent_decisions) > 100:
                self._recent_decisions = self._recent_decisions[-100:]

        except Exception as e:
            logger.error(f"Error evaluating decision: {e}")

    async def _process_execution_queue(self):
        """Process execution queue and send orders to router"""
        try:
            while self._execution_queue:
                decision = self._execution_queue.pop(0)

                try:
                    # Send order to router
                    order_result = await self.router_client.place_order(decision)

                    if order_result.get("success", False):
                        self._decisions_executed += 1
                        logger.info(
                            f"Successfully executed decision: {decision.symbol} {decision.action}"
                        )

                        # Remove processed signals
                        if decision.symbol in self._pending_signals:
                            del self._pending_signals[decision.symbol]

                    else:
                        logger.error(f"Failed to execute decision: {order_result}")

                except Exception as e:
                    logger.error(f"Error executing decision: {e}")

        except Exception as e:
            logger.error(f"Error processing execution queue: {e}")

    async def _update_account_state(self):
        """Update account state from router"""
        try:
            # Get account balance
            balance_info = await self.router_client.get_balance()
            if balance_info:
                self._account_balance = Decimal(str(balance_info.get("total", 100000)))

            # Get current positions
            positions_data = await self.router_client.get_positions()
            self._current_positions = []

            for pos_data in positions_data:
                # Convert to Position object (simplified)
                position = Position(
                    symbol=pos_data["symbol"],
                    side=OrderSide(pos_data["side"]),
                    size=Decimal(str(pos_data["size"])),
                    entry_price=Decimal(str(pos_data["entry_price"])),
                    current_price=Decimal(str(pos_data["current_price"])),
                    unrealized_pnl=Decimal(str(pos_data["unrealized_pnl"])),
                    margin_used=Decimal(str(pos_data["margin_used"])),
                    opened_at=datetime.fromisoformat(pos_data["opened_at"]),
                )
                self._current_positions.append(position)

                # Update risk manager
                self.risk_manager.update_position(position)

        except Exception as e:
            logger.error(f"Error updating account state: {e}")

    def force_decision(
        self, symbol: str, action: str, reasoning: str = "Manual decision"
    ) -> Optional[TradingDecision]:
        """Force a trading decision (for manual intervention)"""
        try:
            # Get current market price
            # This would need to be made async, simplified for now
            current_price = Decimal("50000")  # Placeholder

            decision = TradingDecision(
                symbol=symbol,
                timestamp=datetime.utcnow(),
                action=action,
                entry_price=current_price,
                confidence=Decimal("1.0"),
                reasoning=f"Manual: {reasoning}",
            )

            self._recent_decisions.append(decision)
            logger.info(f"Forced decision: {symbol} {action}")

            return decision

        except Exception as e:
            logger.error(f"Error creating forced decision: {e}")
            return None

    async def get_status(self) -> Dict[str, Any]:
        """Get current status of the decision engine"""
        return {
            "running": self._running,
            "pending_signals": {
                symbol: len(signals)
                for symbol, signals in self._pending_signals.items()
            },
            "execution_queue_size": len(self._execution_queue),
            "recent_decisions": len(self._recent_decisions),
            "decisions_generated": self._decisions_generated,
            "decisions_executed": self._decisions_executed,
            "signals_processed": self._signals_processed,
            "account_balance": float(self._account_balance),
            "open_positions": len(self._current_positions),
            "risk_metrics": self.risk_manager.get_risk_metrics(),
        }

    async def health_check(self) -> Dict[str, Any]:
        """Health check for the decision engine"""
        try:
            router_health = await self.router_client.health_check()
            status = await self.get_status()

            return {
                "status": "healthy" if self._running else "stopped",
                "router_connection": router_health.get("status", "unknown"),
                "engine_status": status,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Decision engine health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
