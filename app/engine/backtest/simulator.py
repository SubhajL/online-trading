"""
Event-driven backtesting simulator.

Runs the real strategy pipeline per closed bar: SMC structure/zones captured
through the global event bus, retest analysis, live sizing and pretrade risk
gates, signal cooldown, next-bar-open fills and OCO bracket exits.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Any, cast

from ..bus import set_event_bus
from ..core.signal_cooldown import SignalCooldown
from ..decision.pretrade_risk import evaluate_pretrade_risk
from ..decision.risk_state import RiskSnapshot
from ..decision.sizing import size_with_exposure_caps
from ..features.indicators import TechnicalIndicatorsCalculator
from ..models import Candle, RiskParameters, TimeFrame, TradingDecision
from ..retest.engine import analyze_retest
from ..smc.engine import SMCEngine
from ..smc_types import StructureBreakEvent
from .capture_bus import CapturingEventBus
from .costs import CostCalculator
from .fills import FillEngine
from .policies import TradingPolicyManager
from .types import (
    BacktestConfig,
    BacktestFill,
    BacktestOrder,
    BacktestPosition,
    BacktestTrade,
    ExitReason,
    FillReason,
    OrderSide,
    OrderStatus,
    OrderType,
)

if TYPE_CHECKING:
    from uuid import UUID

    from ..bus import EventBus

logger = logging.getLogger(__name__)

_BAR_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

_EXIT_REASONS: dict[FillReason, ExitReason] = {
    FillReason.STOP: ExitReason.SL,
    FillReason.LIMIT: ExitReason.TP,
}


class _SimClock:
    def __init__(self) -> None:
        self._now = 0.0

    def set_time(self, now: float) -> None:
        self._now = now

    def monotonic(self) -> float:
        return self._now


@dataclass(frozen=True)
class _BracketSpec:
    stop_loss: Decimal
    take_profit: Decimal
    direction: str


class BacktestSimulator:
    def __init__(
        self,
        config: BacktestConfig,
        initial_balance: Decimal = Decimal(10000),
    ):
        self.config = config
        self.initial_balance = initial_balance
        self.current_balance = initial_balance

        # SMCEngine resolves the global bus in its constructor, so the
        # capturing bus must be installed first.
        self._capture_bus = CapturingEventBus()
        set_event_bus(cast("EventBus", self._capture_bus))
        self.smc_engine = SMCEngine(pivot_n=config.pivot_n, db_adapter=None)

        self.indicators_calc = TechnicalIndicatorsCalculator()
        self.fill_engine = FillEngine(config.slippage_bps)
        self.cost_calculator = CostCalculator(
            fee_bps_spot=config.fee_bps_spot,
            funding_model=config.funding_model,
        )
        self.policy_manager = TradingPolicyManager()
        self._clock = _SimClock()
        self.cooldown = SignalCooldown(
            cooldown_seconds=config.cooldown_seconds,
            clock=self._clock,
        )
        # Notional/symbol-exposure/open-position caps mirror the live engine
        # defaults (main.py risk_parameters); daily-loss/drawdown gates and
        # max_position_size deliberately stay disabled here.
        self._risk = RiskParameters(
            max_position_size=Decimal(1_000_000_000),
            max_daily_loss=Decimal(1),
            max_drawdown=Decimal(1),
            risk_per_trade=config.risk_per_trade,
            max_correlation=Decimal(1),
            max_open_positions=5,
            max_total_exposure_leverage=Decimal(3),
            max_symbol_exposure_pct=Decimal("0.25"),
            max_position_notional_pct=Decimal("0.10"),
            risk_data_max_age_seconds=86400,
            drawdown_lookback_days=30,
        )

        self.current_time: datetime | None = None
        self.active_orders: list[BacktestOrder] = []
        self.positions: dict[str, BacktestPosition] = {}
        self.completed_trades: list[BacktestTrade] = []
        self.equity_history: list[tuple[datetime, Decimal]] = []
        self.drawdown_history: list[tuple[datetime, Decimal]] = []

        self.peak_balance = initial_balance
        self.total_fees = Decimal(0)
        self.total_slippage = Decimal(0)
        self.total_funding = Decimal(0)

        self._candles: deque[Candle] = deque(maxlen=200)
        self._bos_events: list[dict[str, Any]] = []
        self._prev_macd_hist: Decimal | None = None
        self._pending_brackets: dict[UUID, _BracketSpec] = {}
        self._oco_pairs: dict[UUID, UUID] = {}
        self._day_start_equity = initial_balance
        self._current_day: date | None = None

    async def process_candle(self, candle: Candle) -> None:
        self.current_time = candle.close_time
        self._clock.set_time(candle.close_time.timestamp())
        self._roll_trading_day(candle)

        self._process_order_fills(candle)
        self._update_positions(candle)
        self._process_funding(candle)

        self._candles.append(candle)
        features = self._calculate_features()

        await self.smc_engine.process_candle(candle, emit_events=True)
        self._capture_structure_breaks()
        self._prune_bos_events(candle)

        if features is not None:
            signal = await analyze_retest(
                venue=candle.venue,
                symbol=candle.symbol,
                timeframe=candle.timeframe.value,
                candles=[self._candle_to_dict(c) for c in self._candles],
                zones=self._zones_as_dicts(candle.symbol, candle.timeframe),
                bos_events=self._bos_events,
                features=features,
            )
            if signal:
                await self._execute_signal(signal, candle)

        self._update_equity_curve()

    def _calculate_features(self) -> dict[str, Decimal] | None:
        if len(self._candles) < self.config.warmup_bars:
            return None

        indicators = self.indicators_calc.calculate_all_indicators(
            list(self._candles),
            ema_periods=[9, 21, 50],
            rsi_period=14,
            macd_params=(12, 26, 9),
            atr_period=14,
            bb_period=20,
            bb_std_dev=2.0,
        )

        macd_hist = indicators.macd_histogram
        macd_hist_prev = self._prev_macd_hist
        self._prev_macd_hist = macd_hist

        if (
            macd_hist is None
            or macd_hist_prev is None
            or indicators.atr_14 is None
            or indicators.rsi_14 is None
        ):
            return None

        return {
            "atr": indicators.atr_14,
            "macd_hist": macd_hist,
            "macd_hist_prev": macd_hist_prev,
            "rsi": indicators.rsi_14,
        }

    def _capture_structure_breaks(self) -> None:
        for event in self._capture_bus.drain():
            if not isinstance(event, StructureBreakEvent):
                continue
            smc_event = event.smc_event
            if smc_event.kind.value not in {"BOS", "CHOCH"}:
                continue
            is_bullish = event.current_state.value == "BULLISH"
            self._bos_events.append(
                {
                    "timestamp": smc_event.timestamp,
                    "type": ("BULLISH_BOS" if is_bullish else "BEARISH_BOS")
                    if smc_event.kind.value == "BOS"
                    else ("BULLISH_CHOCH" if is_bullish else "BEARISH_CHOCH"),
                    "level": smc_event.price,
                    "strength": smc_event.strength,
                },
            )

    def _prune_bos_events(self, candle: Candle) -> None:
        bar_minutes = _BAR_MINUTES.get(candle.timeframe.value, 5)
        max_age_seconds = bar_minutes * 60 * min(self.config.retest_max_wait_bars, 8)
        self._bos_events = [
            bos
            for bos in self._bos_events
            if (candle.open_time - bos["timestamp"]).total_seconds() <= max_age_seconds
        ]

    def _zones_as_dicts(self, symbol: str, timeframe: TimeFrame) -> list[dict[str, Any]]:
        return [
            {
                "zone_id": str(zone.zone_id),
                "zone_type": zone.zone_type,
                "side": zone.side.value,
                "top_price": zone.top_price,
                "bottom_price": zone.bottom_price,
                "created_at": zone.created_at,
                "strength": zone.strength,
            }
            for zone in self.smc_engine.get_zones(symbol, timeframe)
        ]

    def _candle_to_dict(self, candle: Candle) -> dict[str, Any]:
        return {
            "open_time": candle.open_time,
            "close": candle.close_price,
            "open": candle.open_price,
            "high": candle.high_price,
            "low": candle.low_price,
            "volume": candle.volume,
        }

    async def _execute_signal(self, signal: dict[str, Any], candle: Candle) -> None:
        direction = signal["direction"]

        allowed, reasons = self.policy_manager.is_trading_allowed(
            candle.close_time,
            candle.symbol,
            direction,
            None,
            None,
        )
        if not allowed:
            logger.debug(f"Signal blocked by policies: {reasons}")
            return

        equity = self._current_equity()
        symbol_exposure = self._symbol_exposure_usd()
        total_exposure = sum(symbol_exposure.values(), Decimal(0))

        sized = size_with_exposure_caps(
            equity=equity,
            entry_price=signal["entry"],
            stop_loss=signal["stop_loss"],
            risk=self._risk,
            existing_symbol_exposure_usd=symbol_exposure.get(candle.symbol, Decimal(0)),
            existing_total_exposure_usd=total_exposure,
        )
        if sized is None or sized.quantity <= 0:
            return

        decision = TradingDecision(
            venue=candle.venue,
            symbol=candle.symbol,
            timestamp=signal["timestamp"],
            action="BUY" if direction == "LONG" else "SELL",
            entry_price=signal["entry"],
            quantity=sized.quantity,
            stop_loss=signal["stop_loss"],
            take_profit=signal["tp1"],
            confidence=Decimal("0.7"),
            reasoning="bos_confirmation; macd_uptick; rsi_bounce",
        )
        snapshot = RiskSnapshot(
            equity=equity,
            equity_ts=candle.close_time,
            start_of_day_equity=self._day_start_equity,
            peak_equity=self.peak_balance,
            open_positions_count=len(symbol_exposure),
            total_exposure_usd=total_exposure,
            symbol_exposure_usd=symbol_exposure,
        )
        ok, reasons = evaluate_pretrade_risk(
            snapshot=snapshot,
            decision=decision,
            risk=self._risk,
        )
        if not ok:
            logger.debug(f"Signal blocked by pretrade risk: {reasons}")
            return

        acquired = await self.cooldown.try_acquire_async(
            candle.symbol,
            candle.timeframe.value,
            str(signal["zone_id"]),
            direction,
            venue=candle.venue,
        )
        if not acquired:
            logger.debug(f"Signal blocked by cooldown: {signal['zone_id']}")
            return

        order = BacktestOrder(
            symbol=candle.symbol,
            side=OrderSide.BUY if direction == "LONG" else OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=sized.quantity,
            order_time=candle.close_time,
        )
        self.active_orders.append(order)
        self._pending_brackets[order.id] = _BracketSpec(
            stop_loss=signal["stop_loss"],
            take_profit=signal["tp1"],
            direction=direction,
        )
        logger.info(
            f"Signal executed: {direction} {candle.symbol} size={sized.quantity}",
        )

    def _process_order_fills(self, candle: Candle) -> None:
        fills = self.fill_engine.process_order_fills(self.active_orders, candle)
        for fill in self._stop_first(fills):
            self._execute_fill(fill, candle)

    def _stop_first(self, fills: list[BacktestFill]) -> list[BacktestFill]:
        stop_filled_orders = {
            fill.order_id for fill in fills if fill.fill_reason == FillReason.STOP
        }
        return [
            fill
            for fill in fills
            if not (
                fill.fill_reason == FillReason.LIMIT
                and self._oco_pairs.get(fill.order_id) in stop_filled_orders
            )
        ]

    def _execute_fill(self, fill: BacktestFill, candle: Candle) -> None:
        order = next((o for o in self.active_orders if o.id == fill.order_id), None)
        if order is None:
            return

        fee = self.cost_calculator.calculate_fill_fee(fill)
        fill.fee = fee
        self.total_fees += fee
        # fill.slippage is a per-unit price delta; cost is per-unit × quantity
        self.total_slippage += fill.slippage * fill.quantity
        self.current_balance -= fee

        order.filled_quantity += fill.quantity
        order.remaining_quantity -= fill.quantity
        order.fill_time = fill.fill_time
        if order.remaining_quantity <= Decimal(0):
            order.status = OrderStatus.FILLED
            self.active_orders.remove(order)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED

        bracket = self._pending_brackets.pop(order.id, None)
        if bracket is not None:
            self._open_position(fill, candle, bracket)
            self._place_bracket_orders(fill, bracket)
            return

        sibling_id = self._oco_pairs.pop(order.id, None)
        if sibling_id is not None:
            self._oco_pairs.pop(sibling_id, None)
            self._cancel_order(sibling_id)
        self._close_position(
            fill,
            exit_reason=_EXIT_REASONS.get(fill.fill_reason, ExitReason.MANUAL),
        )

    def _cancel_order(self, order_id: UUID) -> None:
        order = next((o for o in self.active_orders if o.id == order_id), None)
        if order is None:
            return
        order.status = OrderStatus.CANCELLED
        self.active_orders.remove(order)

    def _open_position(
        self,
        fill: BacktestFill,
        candle: Candle,
        bracket: _BracketSpec,
    ) -> None:
        side = "LONG" if fill.side == OrderSide.BUY else "SHORT"
        position = self.positions.get(fill.symbol)

        if position is None or not position.side or position.quantity <= 0:
            position = BacktestPosition(
                symbol=fill.symbol,
                side=side,
                quantity=fill.quantity,
                entry_quantity=fill.quantity,
                entry_price=fill.price,
                opened_at=fill.fill_time,
            )
            self.positions[fill.symbol] = position
        elif position.side == side:
            old_value = position.quantity * position.entry_price
            new_quantity = position.quantity + fill.quantity
            position.entry_price = (old_value + fill.quantity * fill.price) / new_quantity
            position.quantity = new_quantity
            position.entry_quantity += fill.quantity
        else:
            logger.warning(
                f"Opposite-side entry fill ignored for {fill.symbol}; netting unsupported",
            )
            return

        position.mark_price = candle.close_price
        position.total_fees += fill.fee
        position.total_slippage += fill.slippage * fill.quantity
        position.risked_amount += fill.quantity * abs(fill.price - bracket.stop_loss)
        position.stop_loss = bracket.stop_loss
        position.take_profit = bracket.take_profit

    def _place_bracket_orders(self, fill: BacktestFill, bracket: _BracketSpec) -> None:
        exit_side = OrderSide.SELL if fill.side == OrderSide.BUY else OrderSide.BUY
        stop_order = BacktestOrder(
            symbol=fill.symbol,
            side=exit_side,
            type=OrderType.STOP_MARKET,
            quantity=fill.quantity,
            stop_price=bracket.stop_loss,
            reduce_only=True,
            order_time=fill.fill_time,
        )
        tp_order = BacktestOrder(
            symbol=fill.symbol,
            side=exit_side,
            type=OrderType.LIMIT,
            quantity=fill.quantity,
            price=bracket.take_profit,
            reduce_only=True,
            order_time=fill.fill_time,
        )
        self.active_orders.append(stop_order)
        self.active_orders.append(tp_order)
        self._oco_pairs[stop_order.id] = tp_order.id
        self._oco_pairs[tp_order.id] = stop_order.id

    def _close_position(self, fill: BacktestFill, exit_reason: ExitReason) -> None:
        position = self.positions.get(fill.symbol)
        if position is None or not position.side or position.quantity <= 0:
            return

        position.total_fees += fill.fee
        position.total_slippage += fill.slippage * fill.quantity
        close_quantity = min(fill.quantity, position.quantity)

        if close_quantity >= position.quantity:
            pnl = self._calculate_position_pnl(position, fill.price)
            position.realized_pnl += pnl
            self.current_balance += pnl
            self._record_completed_trade(position, fill.price, exit_reason)
            position.quantity = Decimal(0)
            position.side = None
            position.unrealized_pnl = Decimal(0)
        else:
            close_ratio = close_quantity / position.quantity
            partial_pnl = self._calculate_position_pnl(position, fill.price) * close_ratio
            position.realized_pnl += partial_pnl
            position.quantity -= close_quantity
            self.current_balance += partial_pnl

    def _calculate_position_pnl(
        self,
        position: BacktestPosition,
        current_price: Decimal,
    ) -> Decimal:
        if position.quantity == Decimal(0) or not position.side:
            return Decimal(0)

        price_diff = current_price - position.entry_price

        if position.side == "LONG":
            return position.quantity * price_diff
        return position.quantity * -price_diff

    def _record_completed_trade(
        self,
        position: BacktestPosition,
        exit_price: Decimal,
        exit_reason: ExitReason,
    ) -> None:
        if not position.opened_at or not position.side:
            return

        trade = BacktestTrade(
            symbol=position.symbol,
            side=position.side.lower(),
            entry_time=position.opened_at,
            exit_time=self.current_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size=position.entry_quantity,
            fees=position.total_fees,
            slippage=position.total_slippage,
            funding=position.total_funding,
            stop_loss=position.stop_loss,
            exit_reason=exit_reason,
        )

        trade.gross_pnl = position.realized_pnl
        trade.net_pnl = trade.gross_pnl - trade.fees - trade.funding

        # Initial risk summed per entry fill against its own bracket's stop
        if position.risked_amount > 0:
            trade.gross_pnl_r = trade.gross_pnl / position.risked_amount
            trade.net_pnl_r = trade.net_pnl / position.risked_amount

        self.completed_trades.append(trade)

    def _update_positions(self, candle: Candle) -> None:
        for symbol, position in self.positions.items():
            if symbol == candle.symbol and position.side and position.quantity > 0:
                position.mark_price = candle.close_price
                position.unrealized_pnl = self._calculate_position_pnl(
                    position,
                    candle.close_price,
                )

    def _process_funding(self, candle: Candle) -> None:
        if self.config.funding_model == "disabled":
            return

        for symbol, position in self.positions.items():
            if position.quantity == Decimal(0) or not position.side:
                continue
            if not position.opened_at:
                continue

            if self.cost_calculator.should_charge_funding(
                candle.close_time,
                position.opened_at,
            ):
                funding_rate = self.cost_calculator.get_funding_rate(
                    symbol,
                    candle.close_time,
                )
                funding_payment = self.cost_calculator.calculate_funding_payment(
                    position.quantity,
                    position.side,
                    position.mark_price,
                    funding_rate,
                )

                position.total_funding += funding_payment
                self.total_funding += funding_payment
                self.current_balance -= funding_payment

                logger.debug(f"Funding payment: {symbol} {funding_payment}")

    def _current_equity(self) -> Decimal:
        return self.current_balance + sum(
            (position.unrealized_pnl for position in self.positions.values()),
            Decimal(0),
        )

    def _symbol_exposure_usd(self) -> dict[str, Decimal]:
        return {
            symbol: abs(position.quantity * position.mark_price)
            for symbol, position in self.positions.items()
            if position.side and position.quantity > 0
        }

    def _roll_trading_day(self, candle: Candle) -> None:
        day = candle.close_time.date()
        if self._current_day != day:
            self._current_day = day
            self._day_start_equity = self._current_equity()

    def _update_equity_curve(self) -> None:
        if not self.current_time:
            return

        current_equity = self._current_equity()
        self.equity_history.append((self.current_time, current_equity))

        self.peak_balance = max(self.peak_balance, current_equity)

        drawdown = (self.peak_balance - current_equity) / self.peak_balance
        self.drawdown_history.append((self.current_time, drawdown))

    def get_current_state(self) -> dict[str, Any]:
        return {
            "current_time": self.current_time,
            "balance": self.current_balance,
            "positions": len([p for p in self.positions.values() if p.quantity > 0]),
            "active_orders": len(self.active_orders),
            "completed_trades": len(self.completed_trades),
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "total_funding": self.total_funding,
            "current_equity": self._current_equity(),
        }
