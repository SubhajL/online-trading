from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import enum
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Protocol

from app.engine.models import BaseEvent, ErrorEvent, EventType, TradingDecisionEvent

if TYPE_CHECKING:
    from collections.abc import Mapping


logger = logging.getLogger(__name__)


def _sanitize_value_for_json(value: Any) -> Any:
    """Recursively convert non-JSON-serializable values to JSON-safe forms.

    Converts:
    - Decimal -> str (preserves precision)
    - datetime -> ISO 8601 string (assumes UTC if naive)
    - dict -> recursively sanitized dict
    - list -> recursively sanitized list
    - Other types pass through unchanged
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_value_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value_for_json(v) for v in value]
    return value


class ExecutionMode(str, enum.Enum):
    DISABLED = "disabled"
    FUTURES_TESTNET = "futures_testnet"
    FUTURES_MAINNET = "futures_mainnet"


def execution_mode_from_env(environ: Mapping[str, str]) -> ExecutionMode:
    raw = environ.get("EXECUTION_MODE", ExecutionMode.DISABLED.value).strip().lower()
    try:
        mode = ExecutionMode(raw)
    except ValueError as exc:
        raise RuntimeError(f"Unknown EXECUTION_MODE: {raw}") from exc

    if mode == ExecutionMode.FUTURES_MAINNET and environ.get("I_UNDERSTAND_LIVE_TRADING") != "1":
        raise RuntimeError(
            "Refusing to enable futures_mainnet execution without I_UNDERSTAND_LIVE_TRADING=1",
        )

    return mode


class _EventBus(Protocol):
    async def subscribe(
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[EventType] | None = None,
        priority: int = 0,
    ) -> str: ...

    async def unsubscribe(self, subscription_id: str) -> bool: ...

    async def publish(self, event: BaseEvent, priority: int = 0) -> bool: ...


def _check_router_response(response: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if router response indicates success.

    Returns:
        Tuple of (is_success, error_message). error_message is None if successful.
    """
    if response.get("success") is False:
        error_msg = response.get("error", "Unknown router error")
        return False, str(error_msg)
    return True, None


async def _emit_execution_error(
    bus: _EventBus,
    event: TradingDecisionEvent,
    error_message: str,
    error_type: str,
) -> None:
    """Emit an ErrorEvent for execution failures."""
    decision = event.decision
    error_event = ErrorEvent(
        event_type=EventType.ERROR,
        timestamp=datetime.now(UTC),
        symbol=decision.symbol,
        timeframe=event.timeframe,
        error_type=error_type,
        error_message=error_message,
        component="router_execution_subscriber",
        metadata={
            "decision_id": str(decision.decision_id),
            "signal_id": event.metadata.get("signal_id"),
            "action": str(decision.action),
        },
    )
    try:
        await bus.publish(error_event)
    except Exception:
        logger.exception("Failed to publish execution error event")


class _RouterClient(Protocol):
    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _ClientOrderIDs:
    main: str
    take_profits: list[str]
    stop_loss: str


def _stable_id_token(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:16]


def _build_client_order_ids(*, key: str, tp_count: int) -> _ClientOrderIDs:
    token = _stable_id_token(key)
    main = f"{token}_entry"
    stop_loss = f"{token}_sl"
    take_profits = [f"{token}_tp{i + 1}" for i in range(tp_count)]
    return _ClientOrderIDs(main=main, take_profits=take_profits, stop_loss=stop_loss)


def _maybe_decimal_to_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


class RouterExecutionSubscriber:
    def __init__(
        self,
        *,
        bus: _EventBus,
        router_client: _RouterClient,
        execution_mode: ExecutionMode,
    ) -> None:
        self._bus = bus
        self._router_client = router_client
        self._execution_mode = execution_mode
        self._subscription_id: str | None = None

    async def start(self) -> None:
        if self._execution_mode == ExecutionMode.DISABLED:
            return

        self._subscription_id = await self._bus.subscribe(
            subscriber_id="router-execution",
            handler=self._on_trading_decision,
            event_types=[EventType.TRADING_DECISION],
            priority=5,
        )

    async def stop(self) -> None:
        if self._subscription_id is None:
            return
        await self._bus.unsubscribe(self._subscription_id)
        self._subscription_id = None

    async def _on_trading_decision(self, event: TradingDecisionEvent) -> None:
        decision = event.decision
        action = str(decision.action).upper()
        if action not in {"BUY", "SELL"}:
            return

        entry_price = decision.entry_price
        stop_loss = decision.stop_loss
        take_profit = decision.take_profit
        quantity = decision.quantity
        if entry_price is None or stop_loss is None or take_profit is None or quantity is None:
            return

        is_futures = self._execution_mode in {
            ExecutionMode.FUTURES_TESTNET,
            ExecutionMode.FUTURES_MAINNET,
        }

        metadata_timeframe = event.metadata.get("timeframe")
        timeframe = (
            metadata_timeframe
            if isinstance(metadata_timeframe, str) and metadata_timeframe
            else (event.timeframe.value if event.timeframe else None)
        )
        signal_id = event.metadata.get("signal_id")
        zone = event.metadata.get("zone")

        tp_prices = [take_profit]
        client_ids = _build_client_order_ids(
            key=str(signal_id) if isinstance(signal_id, str) else str(decision.decision_id),
            tp_count=len(tp_prices),
        )

        # Sanitize metadata to ensure JSON serialization works
        raw_metadata = {
            "signal_id": signal_id if isinstance(signal_id, str) else None,
            "timeframe": timeframe,
            "zone": zone if isinstance(zone, dict) else None,
            "decision_time": decision.timestamp.replace(tzinfo=UTC).isoformat()
            if decision.timestamp.tzinfo is None
            else decision.timestamp.isoformat(),
        }
        sanitized_metadata = _sanitize_value_for_json(raw_metadata)

        payload: dict[str, Any] = {
            "symbol": decision.symbol,
            "side": action,
            "quantity": _maybe_decimal_to_str(quantity),
            "entry_price": _maybe_decimal_to_str(entry_price),
            "take_profit_prices": [_maybe_decimal_to_str(tp) for tp in tp_prices],
            "stop_loss_price": _maybe_decimal_to_str(stop_loss),
            "order_type": "LIMIT",
            "is_futures": is_futures,
            "metadata": sanitized_metadata,
            "client_order_ids": {
                "main": client_ids.main,
                "take_profits": client_ids.take_profits,
                "stop_loss": client_ids.stop_loss,
            },
        }

        try:
            response = await self._router_client.place_bracket_order(payload)
            success, error_msg = _check_router_response(response)
            if not success:
                logger.error(
                    "Router returned error for %s %s: %s",
                    action,
                    decision.symbol,
                    error_msg,
                )
                await _emit_execution_error(
                    self._bus, event, error_msg or "Unknown router error", "router_error",
                )
        except Exception as exc:
            logger.exception(
                "Exception placing bracket order for %s %s",
                action,
                decision.symbol,
            )
            await _emit_execution_error(self._bus, event, str(exc), "router_exception")
