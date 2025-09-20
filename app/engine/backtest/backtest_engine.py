"""
Backtesting engine for strategy validation.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from ..types import (
    Candle,
    TradingDecision,
    TechnicalIndicators,
    TimeFrame,
    OrderSide,
    TradingMetrics,
)
from ..features.indicators import IndicatorCalculator
from ..smc.smc_service import SMCService
from ..decision.decision_engine import DecisionEngine


class BacktestEngine:
    """
    Backtesting engine with vectorized and event-driven modes.
    """

    def __init__(
        self,
        initial_balance: Decimal = Decimal("10000"),
        commission: Decimal = Decimal("0.001"),
        slippage: Decimal = Decimal("0.001"),
    ):
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage

        # Components
        self.indicator_calculator = IndicatorCalculator()
        self.smc_service = SMCService()
        self.decision_engine = DecisionEngine()

        # Results storage
        self.trades: List[Dict] = []
        self.equity_curve: List[Tuple[datetime, Decimal]] = []
        self.positions: Dict[str, Dict] = {}

    async def run_backtest(
        self, candles: pd.DataFrame, symbol: str, timeframe: TimeFrame
    ) -> TradingMetrics:
        """
        Run backtest on historical data.
        """
        # Reset state
        self.trades = []
        self.equity_curve = []
        self.positions = {}
        balance = self.initial_balance

        # Calculate indicators for all candles
        indicators_df = await self._calculate_all_indicators(candles)

        # Detect SMC patterns
        smc_signals = await self._detect_smc_patterns(candles, symbol, timeframe)

        # Iterate through candles
        for i in range(50, len(candles)):  # Start after warmup period
            candle = candles.iloc[i]
            timestamp = candle["close_time"]

            # Update open positions
            balance = self._update_positions(candle, balance)

            # Check for signals
            if i in smc_signals:
                signal = smc_signals[i]

                # Get current indicators
                current_indicators = self._get_indicators_at(indicators_df, i)

                # Make trading decision
                decision = await self._make_decision(
                    candle, signal, current_indicators, balance
                )

                if decision:
                    # Execute trade
                    trade = self._execute_trade(decision, candle, balance)
                    if trade:
                        self.trades.append(trade)
                        balance -= trade["cost"]

            # Record equity
            total_equity = balance + sum(
                p["unrealized_pnl"] for p in self.positions.values()
            )
            self.equity_curve.append((timestamp, total_equity))

        # Close remaining positions
        final_balance = self._close_all_positions(candles.iloc[-1], balance)

        # Calculate metrics
        return self._calculate_metrics(final_balance)

    async def _calculate_all_indicators(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all technical indicators for the dataset.
        """
        df = candles.copy()

        # EMAs
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        # RSI
        df["rsi_14"] = self._calculate_rsi(df["close"], 14)

        # MACD
        exp1 = df["close"].ewm(span=12, adjust=False).mean()
        exp2 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = exp1 - exp2
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        # ATR
        df["atr_14"] = self._calculate_atr(df, 14)

        # Bollinger Bands
        df["bb_middle"] = df["close"].rolling(window=20).mean()
        std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_middle"] + (std * 2)
        df["bb_lower"] = df["bb_middle"] - (std * 2)

        return df

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate RSI indicator.
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate ATR indicator.
        """
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr

    async def _detect_smc_patterns(
        self, candles: pd.DataFrame, symbol: str, timeframe: TimeFrame
    ) -> Dict[int, Dict]:
        """
        Detect SMC patterns in historical data.
        """
        signals = {}

        # Simplified SMC detection for backtesting
        for i in range(10, len(candles) - 10):
            # Detect pivot highs and lows
            window = 5
            high_pivot = self._is_pivot_high(candles, i, window)
            low_pivot = self._is_pivot_low(candles, i, window)

            if high_pivot or low_pivot:
                # Check for structure break
                if i > 50:  # Need history for structure
                    structure = self._check_structure_break(candles, i)
                    if structure:
                        signals[i] = {
                            "type": "structure_break",
                            "direction": structure["direction"],
                            "entry_price": candles.iloc[i]["close"],
                            "stop_loss": self._calculate_stop_loss(
                                candles.iloc[i], structure["direction"]
                            ),
                        }

        return signals

    def _is_pivot_high(self, df: pd.DataFrame, index: int, window: int) -> bool:
        """
        Check if index is a pivot high.
        """
        if index < window or index >= len(df) - window:
            return False

        high = df.iloc[index]["high"]
        for i in range(index - window, index + window + 1):
            if i != index and df.iloc[i]["high"] >= high:
                return False
        return True

    def _is_pivot_low(self, df: pd.DataFrame, index: int, window: int) -> bool:
        """
        Check if index is a pivot low.
        """
        if index < window or index >= len(df) - window:
            return False

        low = df.iloc[index]["low"]
        for i in range(index - window, index + window + 1):
            if i != index and df.iloc[i]["low"] <= low:
                return False
        return True

    def _check_structure_break(self, df: pd.DataFrame, index: int) -> Optional[Dict]:
        """
        Check for market structure break.
        """
        # Simplified structure break detection
        lookback = 20
        current_price = df.iloc[index]["close"]

        # Find recent highs and lows
        recent_data = df.iloc[max(0, index - lookback) : index]
        recent_high = recent_data["high"].max()
        recent_low = recent_data["low"].min()

        # Check for break
        if current_price > recent_high:
            return {"direction": "bullish", "level": recent_high}
        elif current_price < recent_low:
            return {"direction": "bearish", "level": recent_low}

        return None

    def _calculate_stop_loss(self, candle: pd.Series, direction: str) -> Decimal:
        """
        Calculate stop loss for a position.
        """
        atr = Decimal(str(candle.get("atr_14", 0)))
        if atr == 0:
            atr = Decimal(str((candle["high"] - candle["low"]) * 1.5))

        if direction == "bullish":
            return Decimal(str(candle["close"])) - (atr * 2)
        else:
            return Decimal(str(candle["close"])) + (atr * 2)

    def _get_indicators_at(self, df: pd.DataFrame, index: int) -> TechnicalIndicators:
        """
        Get technical indicators at a specific index.
        """
        row = df.iloc[index]
        return TechnicalIndicators(
            symbol="",
            timeframe=TimeFrame.M15,
            timestamp=datetime.now(),
            ema_9=Decimal(str(row.get("ema_9", 0))),
            ema_21=Decimal(str(row.get("ema_21", 0))),
            ema_50=Decimal(str(row.get("ema_50", 0))),
            ema_200=Decimal(str(row.get("ema_200", 0))),
            rsi_14=Decimal(str(row.get("rsi_14", 50))),
            macd_line=Decimal(str(row.get("macd", 0))),
            macd_signal=Decimal(str(row.get("macd_signal", 0))),
            macd_histogram=Decimal(str(row.get("macd_histogram", 0))),
            atr_14=Decimal(str(row.get("atr_14", 0))),
            bb_upper=Decimal(str(row.get("bb_upper", 0))),
            bb_middle=Decimal(str(row.get("bb_middle", 0))),
            bb_lower=Decimal(str(row.get("bb_lower", 0))),
        )

    async def _make_decision(
        self,
        candle: pd.Series,
        signal: Dict,
        indicators: TechnicalIndicators,
        balance: Decimal,
    ) -> Optional[TradingDecision]:
        """
        Make trading decision based on signals and indicators.
        """
        # Check if we have enough balance
        min_trade_size = Decimal("100")
        if balance < min_trade_size:
            return None

        # Position sizing (1% risk)
        risk_amount = balance * Decimal("0.01")
        stop_distance = abs(Decimal(str(candle["close"])) - signal["stop_loss"])

        if stop_distance == 0:
            return None

        position_size = risk_amount / stop_distance

        # Create decision
        return TradingDecision(
            symbol="",
            timestamp=datetime.now(),
            action="BUY" if signal["direction"] == "bullish" else "SELL",
            entry_price=Decimal(str(signal["entry_price"])),
            quantity=position_size,
            stop_loss=signal["stop_loss"],
            take_profit=Decimal(str(signal["entry_price"]))
            + (
                stop_distance * 2
                if signal["direction"] == "bullish"
                else -stop_distance * 2
            ),
            confidence=Decimal("0.7"),
            reasoning=f"Structure break {signal['direction']}",
        )

    def _execute_trade(
        self, decision: TradingDecision, candle: pd.Series, balance: Decimal
    ) -> Optional[Dict]:
        """
        Execute a trade in backtest.
        """
        # Apply slippage
        if decision.action == "BUY":
            entry_price = decision.entry_price * (Decimal("1") + self.slippage)
        else:
            entry_price = decision.entry_price * (Decimal("1") - self.slippage)

        # Calculate cost
        cost = decision.quantity * entry_price
        commission_cost = cost * self.commission
        total_cost = cost + commission_cost

        if total_cost > balance:
            return None

        # Create trade record
        trade = {
            "timestamp": candle["close_time"],
            "symbol": decision.symbol,
            "side": decision.action,
            "entry_price": entry_price,
            "quantity": decision.quantity,
            "stop_loss": decision.stop_loss,
            "take_profit": decision.take_profit,
            "cost": total_cost,
            "status": "open",
            "unrealized_pnl": Decimal("0"),
        }

        # Add to positions
        position_key = f"{decision.symbol}_{candle['close_time']}"
        self.positions[position_key] = trade

        return trade

    def _update_positions(self, candle: pd.Series, balance: Decimal) -> Decimal:
        """
        Update open positions with current prices.
        """
        current_price = Decimal(str(candle["close"]))

        for key, position in list(self.positions.items()):
            if position["status"] == "open":
                # Check stop loss
                if position["side"] == "BUY":
                    if current_price <= position["stop_loss"]:
                        balance = self._close_position(
                            position, position["stop_loss"], balance, "stop_loss"
                        )
                    elif current_price >= position["take_profit"]:
                        balance = self._close_position(
                            position, position["take_profit"], balance, "take_profit"
                        )
                    else:
                        # Update unrealized P&L
                        position["unrealized_pnl"] = position["quantity"] * (
                            current_price - position["entry_price"]
                        )
                else:  # SELL
                    if current_price >= position["stop_loss"]:
                        balance = self._close_position(
                            position, position["stop_loss"], balance, "stop_loss"
                        )
                    elif current_price <= position["take_profit"]:
                        balance = self._close_position(
                            position, position["take_profit"], balance, "take_profit"
                        )
                    else:
                        # Update unrealized P&L
                        position["unrealized_pnl"] = position["quantity"] * (
                            position["entry_price"] - current_price
                        )

        return balance

    def _close_position(
        self, position: Dict, exit_price: Decimal, balance: Decimal, exit_reason: str
    ) -> Decimal:
        """
        Close a position and update balance.
        """
        # Calculate P&L
        if position["side"] == "BUY":
            pnl = position["quantity"] * (exit_price - position["entry_price"])
        else:
            pnl = position["quantity"] * (position["entry_price"] - exit_price)

        # Apply commission
        exit_cost = position["quantity"] * exit_price * self.commission
        net_pnl = pnl - exit_cost

        # Update position
        position["status"] = "closed"
        position["exit_price"] = exit_price
        position["exit_reason"] = exit_reason
        position["realized_pnl"] = net_pnl

        # Update balance
        if position["side"] == "BUY":
            balance += position["quantity"] * exit_price - exit_cost
        else:
            balance += position["cost"] + net_pnl

        return balance

    def _close_all_positions(self, last_candle: pd.Series, balance: Decimal) -> Decimal:
        """
        Close all remaining positions at market.
        """
        current_price = Decimal(str(last_candle["close"]))

        for position in self.positions.values():
            if position["status"] == "open":
                balance = self._close_position(
                    position, current_price, balance, "end_of_backtest"
                )

        return balance

    def _calculate_metrics(self, final_balance: Decimal) -> TradingMetrics:
        """
        Calculate trading metrics from results.
        """
        if not self.trades:
            return TradingMetrics(
                timestamp=datetime.now(),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=Decimal("0"),
                total_pnl=final_balance - self.initial_balance,
                max_drawdown=Decimal("0"),
                average_win=Decimal("0"),
                average_loss=Decimal("0"),
                largest_win=Decimal("0"),
                largest_loss=Decimal("0"),
            )

        # Calculate trade statistics
        closed_trades = [t for t in self.trades if t.get("status") == "closed"]
        winning_trades = [t for t in closed_trades if t.get("realized_pnl", 0) > 0]
        losing_trades = [t for t in closed_trades if t.get("realized_pnl", 0) <= 0]

        # Calculate drawdown
        equity_values = [e[1] for e in self.equity_curve]
        peak = self.initial_balance
        max_drawdown = Decimal("0")

        for equity in equity_values:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Calculate averages
        avg_win = (
            sum(t["realized_pnl"] for t in winning_trades) / len(winning_trades)
            if winning_trades
            else Decimal("0")
        )
        avg_loss = (
            sum(abs(t["realized_pnl"]) for t in losing_trades) / len(losing_trades)
            if losing_trades
            else Decimal("0")
        )

        return TradingMetrics(
            timestamp=datetime.now(),
            total_trades=len(closed_trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=Decimal(len(winning_trades)) / Decimal(len(closed_trades))
            if closed_trades
            else Decimal("0"),
            total_pnl=final_balance - self.initial_balance,
            max_drawdown=max_drawdown,
            average_win=avg_win,
            average_loss=avg_loss,
            largest_win=max(
                (t["realized_pnl"] for t in winning_trades), default=Decimal("0")
            ),
            largest_loss=min(
                (t["realized_pnl"] for t in losing_trades), default=Decimal("0")
            ),
        )
