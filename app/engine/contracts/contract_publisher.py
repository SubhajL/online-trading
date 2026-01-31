from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any, Protocol

from app.engine.contracts.mappers import CandleEventMapper, SMCEventMapper, ZoneEventMapper
from app.engine.contracts.topics import ContractTopic
from app.engine.models import (
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    RetestSignalEvent,
    TradingDecisionEvent,
)
from app.engine.models import OrderUpdateEvent
from app.engine.smc_types import StructureBreakEvent, ZoneEvent

logger = logging.getLogger(__name__)


class _RedisPublisher(Protocol):
    async def publish(self, channel: str, message: Any) -> int: ...


class _EventBus(Protocol):
    async def subscribe(
        self,
        subscriber_id: str,
        handler: Any,
        event_types: list[Any] | None = None,
        priority: int = 0,
        max_retries: int = 3,
        *,
        serialize_by_key: bool = False,
        key_extractor: Callable[[Any], str] | None = None,
    ) -> str: ...

    async def unsubscribe(self, subscription_id: str) -> bool: ...


def _format_datetime_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    iso_str = dt.isoformat()
    if iso_str.endswith("+00:00"):
        iso_str = iso_str.replace("+00:00", "Z")
    return iso_str


def _dec_to_float(v: Decimal | None) -> float | None:
    if v is None:
        return None
    return float(v)


class ContractPublisher:
    """Publishes contract-topic payloads to Redis for BFF/UI consumption."""

    def __init__(self, *, bus: _EventBus, redis: _RedisPublisher) -> None:
        self._bus = bus
        self._redis = redis
        self._subs: list[str] = []

    async def start(self) -> None:
        """Subscribe to internal events and publish contract topics to Redis."""
        if self._subs:
            return

        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:candles",
                handler=self.on_candle_update,
                event_types=[EventType.CANDLE_UPDATE],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:features",
                handler=self.on_features_calculated,
                event_types=[EventType.FEATURES_CALCULATED],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:signals",
                handler=self.on_retest_signal,
                event_types=[EventType.RETEST_SIGNAL],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:decisions",
                handler=self.on_trading_decision,
                event_types=[EventType.TRADING_DECISION],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:order-updates",
                handler=self.on_order_update,
                event_types=[EventType.ORDER_UPDATE],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:smc-events",
                handler=self.on_smc_event,
                event_types=[EventType.SMC_EVENT],
                priority=1,
            ),
        )
        self._subs.append(
            await self._bus.subscribe(
                subscriber_id="contract-publisher:zones",
                handler=self.on_zone_event,
                event_types=[EventType.ZONE_UPDATE],
                priority=1,
            ),
        )

        logger.info("ContractPublisher started (subscribed=%s)", len(self._subs))

    async def stop(self) -> None:
        for sub_id in self._subs:
            try:
                await self._bus.unsubscribe(sub_id)
            except Exception:
                logger.exception("Failed to unsubscribe ContractPublisher subscription %s", sub_id)
        self._subs.clear()

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        channel = f"engine:{topic}"
        await self._redis.publish(channel, payload)

    async def on_candle_update(self, event: CandleUpdateEvent) -> None:
        if event.origin != CandleOrigin.REALTIME:
            return
        candle = event.candle
        payload = CandleEventMapper.to_schema(candle, venue=candle.venue, is_closed=True)
        await self._publish(ContractTopic.CANDLES_V1, payload)

    async def on_features_calculated(self, event: FeaturesCalculatedEvent) -> None:
        features = event.features
        meta = event.metadata or {}
        venue = str(meta.get("venue") or "SPOT")
        open_time_raw = meta.get("open_time")
        close_time_raw = meta.get("close_time")
        if isinstance(open_time_raw, str):
            open_time = open_time_raw
        elif isinstance(open_time_raw, datetime):
            open_time = _format_datetime_iso_z(open_time_raw)
        else:
            open_time = _format_datetime_iso_z(features.timestamp)

        if isinstance(close_time_raw, str):
            close_time = close_time_raw
        elif isinstance(close_time_raw, datetime):
            close_time = _format_datetime_iso_z(close_time_raw)
        else:
            close_time = _format_datetime_iso_z(features.timestamp)

        payload: dict[str, Any] = {
            "version": "1.0.0",
            "venue": venue,
            "symbol": features.symbol,
            "timeframe": features.timeframe.value,
            "open_time": open_time,
            "close_time": close_time,
            "ema_short": _dec_to_float(features.ema_21),
            "ema_long": _dec_to_float(features.ema_200),
            "rsi": _dec_to_float(features.rsi_14),
            "macd": _dec_to_float(features.macd_line),
            "macd_signal": _dec_to_float(features.macd_signal),
            "macd_histogram": _dec_to_float(features.macd_histogram),
            "atr": None if features.atr_14 is None else str(features.atr_14),
            "bb_upper": _dec_to_float(features.bb_upper),
            "bb_middle": _dec_to_float(features.bb_middle),
            "bb_lower": _dec_to_float(features.bb_lower),
            "volume_ma": None,
        }
        await self._publish(ContractTopic.FEATURES_V1, payload)

    async def on_retest_signal(self, event: RetestSignalEvent) -> None:
        sig = event.signal
        payload: dict[str, Any] = {
            "version": "1.0.0",
            "venue": sig.venue,
            "symbol": sig.symbol,
            "timeframe": sig.timeframe.value,
            "signal_id": str(sig.signal_id),
            "signal_time": _format_datetime_iso_z(sig.timestamp),
            "signal_type": "long" if sig.direction == "BUY" else "short",
            "source": "smc_retest",
            "entry_price": str(sig.level_price),
            "stop_loss": str(sig.stop_loss),
            "take_profit_1": str(sig.take_profit) if sig.take_profit else None,
            "take_profit_2": str(sig.take_profit_2) if sig.take_profit_2 else None,
            "take_profit_3": str(sig.take_profit_3) if sig.take_profit_3 else None,
            "confidence": float(sig.success_probability),
            "metadata": {
                "retest_type": sig.retest_type,
                "confluence_factors": list(sig.confluence_factors),
                **(event.metadata or {}),
            },
        }
        await self._publish(ContractTopic.SIGNALS_RAW_V1, payload)

    async def on_trading_decision(self, event: TradingDecisionEvent) -> None:
        decision = event.decision

        action = decision.action.upper()
        if action == "BUY":
            contract_action = "open_long"
        elif action == "SELL":
            contract_action = "open_short"
        elif action == "CLOSE":
            contract_action = "close_position"
        else:
            contract_action = "no_action"

        signal_ids: list[str] = []
        for sig in decision.signals:
            try:
                signal_ids.append(str(sig.signal_id))
            except Exception:
                continue

        payload: dict[str, Any] = {
            "version": "1.0.0",
            "venue": decision.venue,
            "symbol": decision.symbol,
            "decision_id": str(decision.decision_id),
            "decision_time": _format_datetime_iso_z(decision.timestamp),
            "action": contract_action,
            "signal_ids": signal_ids,
            "entry_price": str(decision.entry_price) if decision.entry_price else None,
            "stop_loss": str(decision.stop_loss) if decision.stop_loss else None,
            "take_profit": str(decision.take_profit) if decision.take_profit else None,
            "position_size": str(decision.quantity) if decision.quantity else None,
            "risk_amount": None,
            "risk_percentage": None,
            "leverage": "1" if decision.venue == "SPOT" else None,
            "confidence": float(decision.confidence),
            "reason": decision.reasoning,
        }
        await self._publish(ContractTopic.DECISION_V1, payload)

    async def on_smc_event(self, event: StructureBreakEvent) -> None:
        payload = SMCEventMapper.to_schema(
            event=event.smc_event,
            venue=event.venue,
            symbol=event.symbol,
            timeframe=event.timeframe.value if event.timeframe else "",
        )
        await self._publish(ContractTopic.SMC_EVENTS_V1, payload)

    async def on_zone_event(self, event: ZoneEvent) -> None:
        payload = ZoneEventMapper.to_schema(
            zone=event.zone,
            venue=event.venue,
            is_active=(event.action != "expired"),
            candle_count=1,
        )
        await self._publish(ContractTopic.ZONES_V1, payload)

    async def on_order_update(self, event: OrderUpdateEvent) -> None:
        update = event.update
        metadata = event.metadata or {}

        decision_id = metadata.get("decision_id") or metadata.get("decisionId")
        if not isinstance(decision_id, str) or not decision_id:
            logger.warning("Skipping order_update.v1 publish: missing decision_id metadata")
            return

        venue = update.venue or metadata.get("venue") or "SPOT"

        def map_status(raw: str) -> str:
            v = raw.strip().upper()
            return {
                "PENDING": "pending",
                "NEW": "new",
                "PARTIALLY_FILLED": "partially_filled",
                "FILLED": "filled",
                "CANCELED": "cancelled",
                "CANCELLED": "cancelled",
                "REJECTED": "rejected",
                "EXPIRED": "expired",
            }.get(v, "pending")

        def map_side(raw: str | None) -> str:
            v = (raw or "").strip().upper()
            return "buy" if v == "BUY" else "sell"

        def map_order_type(raw: str | None) -> str:
            v = (raw or "").strip().upper()
            return {
                "MARKET": "market",
                "LIMIT": "limit",
                "STOP_MARKET": "stop_market",
                "STOP_LOSS": "stop_market",
                "STOP_LOSS_LIMIT": "stop_limit",
                "TAKE_PROFIT": "limit",
                "TAKE_PROFIT_LIMIT": "limit",
            }.get(v, "market")

        update_time = update.update_time or event.timestamp
        payload: dict[str, Any] = {
            "version": "1.0.0",
            "venue": str(venue),
            "symbol": update.symbol,
            "order_id": str(update.order_id or ""),
            "client_order_id": update.client_order_id,
            "decision_id": decision_id,
            "update_time": _format_datetime_iso_z(update_time),
            "status": map_status(update.status),
            "side": map_side(update.side),
            "order_type": map_order_type(update.order_type),
            "price": None if update.price is None else str(update.price),
            "stop_price": None,
            "quantity": str(update.quantity or "0"),
            "filled_quantity": str(update.executed_qty or "0"),
            "average_fill_price": None,
            "commission": None,
            "commission_asset": None,
            "error_message": update.reason,
            "is_reduce_only": bool(metadata.get("reduce_only", False)),
        }
        await self._publish(ContractTopic.ORDER_UPDATE_V1, payload)
