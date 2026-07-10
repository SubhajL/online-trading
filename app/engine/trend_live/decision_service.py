"""
TrendDecisionService — live desired-state diff for the daily trend co-primaries.

Mirrors the simulator's `_apply_trend_target`: every closed D1 candle first
updates the PaperBroker (so resting stops fill against the same bar), then each
(strategy × symbol) sleeve diffs its engine's desired state against its own
bracket. All broker writes are bracket-scoped and idempotent via deterministic
client order ids; any blocked action self-heals on the next daily bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from app.engine.backtest.position_sizing import notional_quantity
from app.engine.backtest.trend_signals import create_trend_engine
from app.engine.decision.sizing import cap_quantity_with_exposure_caps
from app.engine.models import TimeFrame, TradingDecision
from app.engine.paper.broker import ClientOrderIDs, PlaceBracketRequest

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence
    from datetime import datetime

    from app.engine.backtest.trend_signals import TrendEngine, TrendTarget
    from app.engine.models import Candle, RiskParameters
    from app.engine.paper.broker import PaperPosition, PlaceBracketResponse

    from .config import TrendLiveConfig, TrendStrategySpec

    EquityProvider = Callable[[], Awaitable[Decimal | None]]
    DecisionRecorder = Callable[[TradingDecision], Awaitable[bool]]

logger = logging.getLogger(__name__)

LONG = "LONG"
SHORT = "SHORT"
FLAT = "FLAT"

_TREND_NAMESPACE = uuid5(NAMESPACE_URL, "app.engine.trend_live")


def trend_client_order_id(
    strategy_id: str,
    symbol: str,
    open_time: datetime,
    action: str,
) -> str:
    """Deterministic id from (strategy, symbol, 1d, candle open, action) so a
    restarted engine reproduces — never duplicates — its orders."""
    return f"trend-{strategy_id}-{symbol}-1d-{open_time:%Y%m%d}-{action}"


def trend_decision_id(client_order_id: str) -> UUID:
    return uuid5(_TREND_NAMESPACE, client_order_id)


class TrendPaperBroker(Protocol):
    """The PaperBroker surface the trend path relies on (structural)."""

    positions: dict[tuple[str, UUID], PaperPosition]
    current_prices: dict[str, Decimal]

    async def update_market_data(self, candle: Candle) -> None: ...

    async def place_bracket_order(
        self,
        request: PlaceBracketRequest,
    ) -> PlaceBracketResponse: ...

    async def close_position(
        self,
        symbol: str,
        bracket_id: UUID,
        client_order_id: str | None = None,
    ) -> dict[str, str]: ...


@dataclass(frozen=True)
class OpenSleeve:
    """A recovered open position, mapped back to its sleeve after restart."""

    strategy_id: str
    symbol: str
    bracket_id: UUID
    side: str


@dataclass
class _SleeveState:
    spec: TrendStrategySpec
    engine: TrendEngine
    bracket_id: UUID | None = None
    side: str | None = None
    last_open_time: datetime | None = None


class TrendDecisionService:
    """Desired-state diff per (strategy × symbol) sleeve onto the PaperBroker."""

    def __init__(
        self,
        *,
        config: TrendLiveConfig,
        broker: TrendPaperBroker,
        equity_provider: EquityProvider,
        risk: RiskParameters,
        decision_recorder: DecisionRecorder | None = None,
    ) -> None:
        self._broker = broker
        self._equity_provider = equity_provider
        self._risk = risk
        self._decision_recorder = decision_recorder
        self._sleeves: dict[tuple[str, str], _SleeveState] = {
            (spec.strategy_id, symbol): _SleeveState(
                spec=spec,
                engine=create_trend_engine(spec.config),
            )
            for spec in config.strategies
            for symbol in config.symbols
        }

    def warmup(self, symbol: str, candles: Sequence[Candle]) -> None:
        """Replay historical D1 candles through the engines WITHOUT trading."""
        for (_strategy_id, sleeve_symbol), sleeve in self._sleeves.items():
            if sleeve_symbol != symbol:
                continue
            for candle in candles:
                sleeve.engine.on_bar(candle)
            if candles:
                sleeve.last_open_time = candles[-1].open_time
        logger.info("Warmed up %s with %d daily candles", symbol, len(candles))

    def restore_open_sleeves(self, open_sleeves: Iterable[OpenSleeve]) -> None:
        """Attach recovered paper positions to their sleeves before the first diff."""
        for open_sleeve in open_sleeves:
            sleeve = self._sleeves.get((open_sleeve.strategy_id, open_sleeve.symbol))
            if sleeve is None:
                logger.warning(
                    "Recovered position for unknown sleeve %s/%s; ignoring",
                    open_sleeve.strategy_id,
                    open_sleeve.symbol,
                )
                continue
            sleeve.bracket_id = open_sleeve.bracket_id
            sleeve.side = open_sleeve.side

    async def on_daily_candle(self, candle: Candle) -> None:
        if candle.timeframe != TimeFrame.D1:
            logger.warning(
                "Trend path received non-D1 candle %s/%s; ignoring",
                candle.symbol,
                candle.timeframe.value,
            )
            return

        # Broker first: resting stops must fill against this bar before the diff.
        await self._broker.update_market_data(candle)

        for (strategy_id, symbol), sleeve in self._sleeves.items():
            if symbol != candle.symbol:
                continue
            if sleeve.last_open_time is not None and candle.open_time <= sleeve.last_open_time:
                logger.info(
                    "Skipping replayed candle %s for sleeve %s/%s",
                    candle.open_time,
                    strategy_id,
                    symbol,
                )
                continue
            target = sleeve.engine.on_bar(candle)
            sleeve.last_open_time = candle.open_time
            try:
                await self._apply_target(sleeve, target, candle)
            except Exception:
                logger.exception(
                    "Trend sleeve %s/%s failed; desired state re-diffs next bar",
                    strategy_id,
                    symbol,
                )

    async def _apply_target(
        self,
        sleeve: _SleeveState,
        target: TrendTarget,
        candle: Candle,
    ) -> None:
        if not target.ready:
            return
        desired = target.desired
        if desired == SHORT and not sleeve.spec.config.allow_short:
            desired = FLAT

        self._sync_sleeve_with_broker(sleeve, candle.symbol)
        current = sleeve.side
        if current == desired or (current is None and desired == FLAT):
            return

        if current is not None:
            await self._close_sleeve(sleeve, candle)
        if desired == FLAT:
            return
        await self._open_long(sleeve, target, candle)

    def _sync_sleeve_with_broker(self, sleeve: _SleeveState, symbol: str) -> None:
        """A filled stop empties the bracket's position; reflect that here."""
        if sleeve.bracket_id is None:
            sleeve.side = None
            return
        position = self._broker.positions.get((symbol, sleeve.bracket_id))
        if position is None or position.net_quantity.is_zero():
            sleeve.bracket_id = None
            sleeve.side = None

    async def _close_sleeve(self, sleeve: _SleeveState, candle: Candle) -> None:
        bracket_id = sleeve.bracket_id
        if bracket_id is None:
            return
        strategy_id = sleeve.spec.strategy_id
        client_order_id = trend_client_order_id(
            strategy_id,
            candle.symbol,
            candle.open_time,
            "close",
        )
        await self._record_decision(
            action="CLOSE",
            candle=candle,
            strategy_id=strategy_id,
            client_order_id=client_order_id,
        )
        await self._broker.close_position(
            candle.symbol,
            bracket_id,
            client_order_id=client_order_id,
        )
        sleeve.bracket_id = None
        sleeve.side = None

    async def _open_long(
        self,
        sleeve: _SleeveState,
        target: TrendTarget,
        candle: Candle,
    ) -> None:
        strategy_id = sleeve.spec.strategy_id
        entry = target.entry
        stop = target.stop_loss
        if entry is None or stop is None or stop >= entry:
            logger.warning(
                "Sleeve %s/%s: invalid stop %s for entry %s; failing closed",
                strategy_id,
                candle.symbol,
                stop,
                entry,
            )
            return

        equity = await self._equity_provider()
        if equity is None or equity <= 0:
            logger.warning(
                "Sleeve %s/%s: paper equity unavailable (%s); failing closed",
                strategy_id,
                candle.symbol,
                equity,
            )
            return

        quantity_target = notional_quantity(
            equity=equity,
            entry_price=entry,
            notional_pct=sleeve.spec.config.notional_pct,
        )
        if quantity_target is None or quantity_target <= 0:
            return

        symbol_exposure, total_exposure = self._current_exposures(candle.symbol)
        sized = cap_quantity_with_exposure_caps(
            quantity=quantity_target,
            equity=equity,
            entry_price=entry,
            risk=self._risk,
            existing_symbol_exposure_usd=symbol_exposure,
            existing_total_exposure_usd=total_exposure,
        )
        if sized.quantity <= 0:
            return

        main_id = trend_client_order_id(strategy_id, candle.symbol, candle.open_time, "long")
        await self._record_decision(
            action="BUY",
            candle=candle,
            strategy_id=strategy_id,
            client_order_id=main_id,
            quantity=sized.quantity,
            entry_price=entry,
            stop_loss=stop,
        )
        response = await self._broker.place_bracket_order(
            PlaceBracketRequest(
                symbol=candle.symbol,
                side="BUY",
                quantity=sized.quantity,
                take_profit_prices=[],
                stop_loss_price=stop,
                order_type="MARKET",
                is_futures=False,
                client_order_ids=ClientOrderIDs(
                    main=main_id,
                    take_profits=[],
                    stop_loss=f"{main_id}-sl",
                ),
            ),
        )
        sleeve.bracket_id = UUID(response.bracket_order_id)
        sleeve.side = LONG

    def _current_exposures(self, symbol: str) -> tuple[Decimal, Decimal]:
        symbol_exposure = Decimal(0)
        total_exposure = Decimal(0)
        for (position_symbol, _bracket_id), position in self._broker.positions.items():
            if position.net_quantity.is_zero():
                continue
            price = self._broker.current_prices.get(
                position_symbol,
                position.avg_entry_price,
            )
            notional = abs(position.net_quantity) * price
            total_exposure += notional
            if position_symbol == symbol:
                symbol_exposure += notional
        return symbol_exposure, total_exposure

    async def _record_decision(
        self,
        *,
        action: str,
        candle: Candle,
        strategy_id: str,
        client_order_id: str,
        quantity: Decimal | None = None,
        entry_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
    ) -> None:
        """Best-effort audit row; a failed write never blocks the paper order."""
        if self._decision_recorder is None:
            return
        decision = TradingDecision(
            decision_id=trend_decision_id(client_order_id),
            venue=candle.venue,
            symbol=candle.symbol,
            timestamp=candle.close_time,
            action=action,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            confidence=Decimal(1),
            reasoning=(
                f"trend_live {strategy_id} desired-state {action} "
                f"on {candle.open_time:%Y-%m-%d} daily close"
            ),
        )
        try:
            await self._decision_recorder(decision)
        except Exception:
            logger.exception(
                "Decision audit failed (client_order_id=%s)",
                client_order_id,
            )
