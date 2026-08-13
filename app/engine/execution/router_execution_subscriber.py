from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import enum
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, cast
from uuid import UUID

from app.engine.adapters.router_client.http_client import (
    BracketPlacementResult,
    RouterCircuitOpenError,
    RouterHTTPError,
    RouterProtocolError,
    RouterTransportError,
)
from app.engine.core.zone_identity import extract_zone_identity
from app.engine.decision.pretrade_risk import (
    build_pretrade_risk_debug_metadata,
    evaluate_pretrade_risk,
)
from app.engine.decision.risk_state import build_risk_snapshot
from app.engine.execution.order_update_correlation import OrderUpdateCorrelationStore
from app.engine.models import (
    BaseEvent,
    ErrorEvent,
    EventType,
    Order,
    OrderPlacedEvent,
    OrderSide,
    OrderStatus,
    OrderType,
    TradingDecisionEvent,
)
from app.engine.resilience.backoff import BackoffConfig, ExponentialBackoff

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter
    from app.engine.core.signal_cooldown import SignalCooldown
    from app.engine.models import RiskParameters


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
    SPOT_TESTNET = "spot_testnet"
    SPOT_MAINNET = "spot_mainnet"
    FUTURES_TESTNET = "futures_testnet"
    FUTURES_MAINNET = "futures_mainnet"


def execution_mode_from_env(environ: Mapping[str, str]) -> ExecutionMode:
    raw = environ.get("EXECUTION_MODE", ExecutionMode.DISABLED.value).strip().lower()
    try:
        mode = ExecutionMode(raw)
    except ValueError as exc:
        raise RuntimeError(f"Unknown EXECUTION_MODE: {raw}") from exc

    # Require safety acknowledgment for mainnet trading (both spot and futures)
    mainnet_modes = {ExecutionMode.SPOT_MAINNET, ExecutionMode.FUTURES_MAINNET}
    if mode in mainnet_modes and environ.get("I_UNDERSTAND_LIVE_TRADING") != "1":
        raise RuntimeError(
            f"Refusing to enable {mode.value} execution without I_UNDERSTAND_LIVE_TRADING=1",
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

    async def publish_and_wait(self, event: BaseEvent, priority: int = 0) -> bool: ...


def validate_bracket_placement(
    result: BracketPlacementResult,
    payload: dict[str, Any],
) -> None:
    if result.partial_failure or result.errors:
        raise RouterProtocolError(
            f"Router returned partial bracket placement: {', '.join(result.errors) or 'unknown'}"
        )
    if result.symbol != str(payload.get("symbol", "")).upper():
        raise RouterProtocolError("Router placement symbol does not match the request")
    if result.side != str(payload.get("side", "")).upper():
        raise RouterProtocolError("Router placement side does not match the request")
    try:
        expected_quantity = Decimal(str(payload["quantity"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise RouterProtocolError("Placement request has invalid quantity") from exc
    if (
        not result.quantity.is_finite()
        or result.quantity <= 0
        or result.quantity != expected_quantity
    ):
        raise RouterProtocolError("Router placement quantity does not match the request")
    raw_expected_ids = payload.get("client_order_ids")
    if not isinstance(raw_expected_ids, dict):
        raise RouterProtocolError("Placement request missing client_order_ids")
    expected_take_profits = raw_expected_ids.get("take_profits")
    if not isinstance(expected_take_profits, list):
        raise RouterProtocolError("Placement request has invalid take-profit client IDs")
    actual_ids = result.client_order_ids
    if (
        actual_ids.main != raw_expected_ids.get("main")
        or actual_ids.stop_loss != raw_expected_ids.get("stop_loss")
        or actual_ids.take_profits != tuple(expected_take_profits)
    ):
        raise RouterProtocolError("Router placement client IDs do not match the request")


async def _emit_execution_error(
    bus: _EventBus,
    event: TradingDecisionEvent,
    error_message: str,
    error_type: str,
    *,
    extra_metadata: dict[str, object] | None = None,
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
    if extra_metadata:
        error_event.metadata.update(extra_metadata)
    try:
        await bus.publish(error_event)
    except Exception:
        logger.exception("Failed to publish execution error event")


class _RouterClient(Protocol):
    async def place_bracket_order(self, payload: dict[str, Any]) -> BracketPlacementResult: ...


class _BffClient(Protocol):
    async def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]: ...


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
    def __init__(  # noqa: PLR0913
        self,
        *,
        bus: _EventBus,
        router_client: _RouterClient,
        db_adapter: TimescaleDBAdapter,
        risk: RiskParameters,
        venue: str,
        execution_mode: ExecutionMode,
        order_update_correlation_store: OrderUpdateCorrelationStore,
        cooldown: SignalCooldown | None = None,
        bff_client: _BffClient | None = None,
        min_confidence: Decimal = Decimal("0.70"),
        max_position_size: Decimal | None = None,
        execution_readiness_check: Callable[
            [], Awaitable[tuple[bool, str | None, dict[str, object]]]
        ]
        | None = None,
        router_max_attempts: int = 3,
        router_backoff_config: BackoffConfig | None = None,
        router_env_probe_attempts: int = 1,
        router_env_probe_delay_seconds: float = 3.0,
    ) -> None:
        self._bus = bus
        self._router_client = router_client
        self._db_adapter = db_adapter
        self._risk = risk
        self._venue = venue
        self._execution_mode = execution_mode
        self._order_update_correlation_store = order_update_correlation_store
        self._cooldown = cooldown
        self._bff_client = bff_client
        self._min_confidence = min_confidence
        self._max_position_size = max_position_size
        self._execution_readiness_check = execution_readiness_check
        if router_max_attempts < 1:
            raise ValueError("router_max_attempts must be >= 1")
        self._router_max_attempts = router_max_attempts
        self._router_backoff_config = router_backoff_config
        if router_env_probe_attempts < 1:
            raise ValueError("router_env_probe_attempts must be >= 1")
        self._router_env_probe_attempts = router_env_probe_attempts
        self._router_env_probe_delay_seconds = router_env_probe_delay_seconds
        self._subscription_id: str | None = None
        self._symbol_locks: dict[str, asyncio.Lock] = {}

    async def _find_duplicate_execution_reason(
        self,
        *,
        symbol: str,
        side: str,
        timeframe: str | None,
        zone_identity: Any,
    ) -> str | None:
        get_active_position_for_setup = getattr(
            self._db_adapter, "get_active_position_for_setup", None
        )
        get_active_positions = getattr(self._db_adapter, "get_active_positions", None)
        get_active_order_for_setup = getattr(self._db_adapter, "get_active_order_for_setup", None)
        if timeframe is not None and zone_identity is not None:
            lookup_tasks: dict[str, asyncio.Task[Any]] = {}
            if callable(get_active_position_for_setup):
                lookup_tasks["setup_position"] = asyncio.create_task(
                    get_active_position_for_setup(
                        venue=self._venue,
                        symbol=symbol,
                        side=side,
                        timeframe=timeframe,
                        zone_id=zone_identity.zone_id,
                    ),
                )
            if callable(get_active_positions):
                lookup_tasks["active_positions"] = asyncio.create_task(
                    get_active_positions(self._venue),
                )
            if callable(get_active_order_for_setup):
                lookup_tasks["setup_order"] = asyncio.create_task(
                    get_active_order_for_setup(
                        venue=self._venue,
                        symbol=symbol,
                        side=side,
                        timeframe=timeframe,
                        zone_id=zone_identity.zone_id,
                    ),
                )
            lookup_results = dict(
                zip(
                    lookup_tasks,
                    await asyncio.gather(*lookup_tasks.values(), return_exceptions=True),
                    strict=True,
                ),
            )

            active_position = lookup_results.get("setup_position")
            if isinstance(active_position, Exception):
                logger.error(
                    "Duplicate guard setup-position lookup failed for %s %s %s %s",
                    symbol,
                    timeframe,
                    zone_identity.zone_id,
                    side,
                    exc_info=active_position,
                )
                return f"Duplicate guard state unavailable for {symbol}"
            if active_position is not None:
                return (
                    f"Active setup position already exists for "
                    f"{symbol} {timeframe} {zone_identity.zone_id} {side}"
                )

            active_positions = lookup_results.get("active_positions")
            if isinstance(active_positions, Exception):
                logger.error(
                    "Duplicate guard active-position lookup failed for %s",
                    symbol,
                    exc_info=active_positions,
                )
                return f"Duplicate guard state unavailable for {symbol}"
            active_position_rows = cast(list[dict[str, Any]] | None, active_positions)
            if active_position_rows is not None:
                for position in active_position_rows:
                    if str(position.get("symbol")) != symbol:
                        continue
                    position_side = str(position.get("side") or "").strip().upper()
                    if position_side and position_side != side:
                        return f"Active opposite-side position already exists for {symbol}"
                    entry_order_id = str(position.get("entry_order_id") or "").strip()
                    if not entry_order_id:
                        return f"Active position already exists for {symbol}"

            active_order = lookup_results.get("setup_order")
            if isinstance(active_order, Exception):
                logger.error(
                    "Duplicate guard setup-order lookup failed for %s %s %s %s",
                    symbol,
                    timeframe,
                    zone_identity.zone_id,
                    side,
                    exc_info=active_order,
                )
                return f"Duplicate guard state unavailable for {symbol}"
            if active_order is None:
                return None
            return f"Active setup already exists for {symbol} {timeframe} {zone_identity.zone_id} {side}"

        if callable(get_active_positions):
            try:
                active_positions = await get_active_positions(self._venue)
            except Exception:
                logger.exception(
                    "Duplicate guard active-position lookup failed for %s",
                    symbol,
                )
                return f"Duplicate guard state unavailable for {symbol}"
            if any(str(position.get("symbol")) == symbol for position in active_positions):
                return f"Active position already exists for {symbol}"
        return None

    async def _place_bracket_with_retries(self, payload: dict[str, Any]) -> BracketPlacementResult:
        backoff = ExponentialBackoff(
            self._router_backoff_config
            or BackoffConfig(
                base_delay_s=0.5,
                max_delay_s=5.0,
                multiplier=2.0,
                jitter_pct=0.1,
            ),
        )
        last_exc: Exception | None = None

        for attempt in range(1, self._router_max_attempts + 1):
            try:
                return await self._router_client.place_bracket_order(payload)
            except (RouterTransportError, RouterHTTPError) as exc:
                if isinstance(exc, RouterHTTPError) and not exc.retryable:
                    raise
                last_exc = exc
                if attempt >= self._router_max_attempts:
                    break
                delay = backoff.next_delay()
                logger.warning(
                    "Router call failed (attempt %s/%s); retrying in %.2fs: %s",
                    attempt,
                    self._router_max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        assert last_exc is not None
        raise last_exc

    async def start(self) -> None:
        if self._execution_mode == ExecutionMode.DISABLED:
            return

        await self._verify_router_execution_env()

        self._subscription_id = await self._bus.subscribe(
            subscriber_id="router-execution",
            handler=self._on_trading_decision,
            event_types=[EventType.TRADING_DECISION],
            priority=5,
        )

    async def _verify_router_execution_env(self) -> None:
        """Cross-check EXECUTION_MODE against the router's execution env.

        Hard-fails only on a confirmed mismatch; an unreachable router or an
        older router without the health field logs a warning and proceeds.
        Probes retry so a router still booting (compose starts it after the
        engine) can be observed before giving up.
        """
        health_check = getattr(self._router_client, "health_check", None)
        if health_check is None:
            return

        router_env: str | None = None
        last_health: dict[str, Any] | None = None
        for attempt in range(self._router_env_probe_attempts):
            try:
                health = await health_check()
            except Exception as exc:
                health = {"status": "unreachable", "error": str(exc)}
            if isinstance(health, dict):
                last_health = health
                value = health.get("execution_env")
                if isinstance(value, str):
                    router_env = value.strip().lower()
                    break
            if attempt < self._router_env_probe_attempts - 1:
                await asyncio.sleep(self._router_env_probe_delay_seconds)

        if router_env not in {"testnet", "mainnet"}:
            detail = ""
            if isinstance(last_health, dict):
                detail = (
                    f" (last status={last_health.get('status')!r},"
                    f" error={last_health.get('error')!r})"
                )
            logger.warning(
                "Router execution env unverified after %d probe(s)%s; EXECUTION_MODE=%s",
                self._router_env_probe_attempts,
                detail,
                self._execution_mode.value,
            )
            return

        mode_is_mainnet = self._execution_mode in {
            ExecutionMode.SPOT_MAINNET,
            ExecutionMode.FUTURES_MAINNET,
        }
        router_is_mainnet = router_env == "mainnet"
        if mode_is_mainnet != router_is_mainnet:
            raise RuntimeError(
                f"EXECUTION_MODE={self._execution_mode.value} but the router at "
                f"ROUTER_URL reports execution_env={router_env}; refusing to start "
                "execution against the wrong venue",
            )

    async def stop(self) -> None:
        if self._subscription_id is None:
            return
        await self._bus.unsubscribe(self._subscription_id)
        self._subscription_id = None

    def _get_symbol_lock(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
        return self._symbol_locks[symbol]

    async def _on_trading_decision(self, event: TradingDecisionEvent) -> None:  # noqa: C901
        decision_source = event.metadata.get("decision_source")
        if decision_source != "retest_decision_publisher":
            await _emit_execution_error(
                self._bus,
                event,
                f"Rejected trading decision with decision_source={decision_source!r}",
                "invalid_decision_source",
            )
            return

        decision = event.decision
        symbol_lock = self._get_symbol_lock(decision.symbol)
        async with symbol_lock:
            await self._execute_decision(event)

    async def _execute_decision(self, event: TradingDecisionEvent) -> None:  # noqa: C901
        decision = event.decision
        decision_source = event.metadata.get("decision_source")
        action = str(decision.action).upper()
        if action not in {"BUY", "SELL"}:
            return

        entry_price = decision.entry_price
        stop_loss = decision.stop_loss
        take_profit = decision.take_profit
        quantity = decision.quantity
        if entry_price is None or stop_loss is None or take_profit is None or quantity is None:
            return

        if self._max_position_size is not None and quantity > self._max_position_size:
            await _emit_execution_error(
                self._bus,
                event,
                (
                    f"Rejected quantity={quantity} > max_position_size={self._max_position_size} "
                    f"for {decision.symbol}"
                ),
                "risk_limit_exceeded",
            )
            return

        snapshot, errors = await build_risk_snapshot(
            db_adapter=self._db_adapter,
            venue=self._venue,
            now=datetime.now(UTC),
            risk=self._risk,
        )
        if snapshot is None:
            message = (
                "; ".join(f"{e.error_type}:{e.message}" for e in errors)
                or "risk snapshot unavailable"
            )
            await _emit_execution_error(
                self._bus,
                event,
                message,
                "risk_snapshot_unavailable",
            )
            return

        ok, reasons = evaluate_pretrade_risk(snapshot=snapshot, decision=decision, risk=self._risk)
        if not ok:
            debug_meta = build_pretrade_risk_debug_metadata(
                snapshot=snapshot,
                decision=decision,
                risk=self._risk,
            )
            await _emit_execution_error(
                self._bus,
                event,
                "; ".join(reasons),
                "risk_limit_exceeded",
                extra_metadata=debug_meta,
            )
            return

        # Check confidence threshold
        if decision.confidence is not None and decision.confidence < self._min_confidence:
            logger.info(
                "Skipping low-confidence decision for %s: %s < %s",
                decision.symbol,
                decision.confidence,
                self._min_confidence,
            )
            return
        if self._execution_readiness_check is not None:
            ready, reason, metadata = await self._execution_readiness_check()
            if not ready:
                await _emit_execution_error(
                    self._bus,
                    event,
                    reason or "Execution blocked: ingest health unavailable",
                    "execution_blocked_unhealthy_ingest",
                    extra_metadata=metadata,
                )
                return

        metadata_timeframe = event.metadata.get("timeframe")
        timeframe = (
            metadata_timeframe
            if isinstance(metadata_timeframe, str) and metadata_timeframe
            else (event.timeframe.value if event.timeframe else None)
        )
        zone = event.metadata.get("zone")
        zone_identity = extract_zone_identity(event.metadata)
        duplicate_reason = await self._find_duplicate_execution_reason(
            symbol=decision.symbol,
            side=action,
            timeframe=timeframe,
            zone_identity=zone_identity,
        )
        if duplicate_reason is not None:
            await _emit_execution_error(
                self._bus,
                event,
                duplicate_reason,
                "duplicate_active_setup",
            )
            return

        timeframe_str = timeframe or "unknown"
        cooldown_acquired = False

        # Check cooldown atomically (only if cooldown configured and zone_id extractable)
        if (
            self._cooldown is not None
            and zone_identity is not None
            and not (
                cooldown_acquired := await self._cooldown.try_acquire_async(
                    decision.symbol,
                    timeframe_str,
                    zone_identity.zone_id,
                    action,
                    venue=self._venue,
                )
            )
        ):
            logger.info(
                "Skipping signal in cooldown: %s %s %s %s",
                decision.symbol,
                timeframe_str,
                zone_identity.zone_id,
                action,
            )
            return

        is_futures = self._execution_mode in {
            ExecutionMode.FUTURES_TESTNET,
            ExecutionMode.FUTURES_MAINNET,
        }

        signal_id = event.metadata.get("signal_id")

        tp_prices = [take_profit]
        client_ids = _build_client_order_ids(
            key=str(signal_id) if isinstance(signal_id, str) else str(decision.decision_id),
            tp_count=len(tp_prices),
        )
        idempotency_key = (
            str(signal_id) if isinstance(signal_id, str) else str(decision.decision_id)
        )

        # Sanitize metadata to ensure JSON serialization works
        raw_metadata = {
            "signal_id": signal_id if isinstance(signal_id, str) else None,
            "decision_id": str(decision.decision_id),
            "decision_source": decision_source,
            "timeframe": timeframe,
            "zone": zone if isinstance(zone, dict) else None,
            "venue": self._venue,
            "decision_time": decision.timestamp.replace(tzinfo=UTC).isoformat()
            if decision.timestamp.tzinfo is None
            else decision.timestamp.isoformat(),
        }
        sanitized_metadata = _sanitize_value_for_json(raw_metadata)
        try:
            for client_order_id in (
                [client_ids.main]
                + list(client_ids.take_profits)
                + ([client_ids.stop_loss] if client_ids.stop_loss else [])
            ):
                if not client_order_id:
                    continue
                await self._order_update_correlation_store.register(
                    client_order_id=client_order_id,
                    metadata=sanitized_metadata,
                )
        except Exception:
            logger.exception(
                "Failed to register order update correlation for symbol=%s",
                decision.symbol,
            )

        decision_ts = decision.timestamp
        if decision_ts.tzinfo is None:
            decision_ts = decision_ts.replace(tzinfo=UTC)

        payload: dict[str, Any] = {
            "symbol": decision.symbol,
            "side": action,
            "quantity": _maybe_decimal_to_str(quantity),
            "entry_price": _maybe_decimal_to_str(entry_price),
            "take_profit_prices": [_maybe_decimal_to_str(tp) for tp in tp_prices],
            "stop_loss_price": _maybe_decimal_to_str(stop_loss),
            "order_type": "LIMIT",
            "is_futures": is_futures,
            "decision_ts": decision_ts.isoformat(),
            "expected_price": _maybe_decimal_to_str(entry_price),
            "metadata": sanitized_metadata,
            "client_order_ids": {
                "main": client_ids.main,
                "take_profits": client_ids.take_profits,
                "stop_loss": client_ids.stop_loss,
            },
            "idempotency_key": idempotency_key,
        }

        submission_started = False
        intent_acknowledged = False
        try:
            prepared = await self._db_adapter.prepare_execution_intent(
                {
                    "idempotency_key": idempotency_key,
                    "decision_id": str(decision.decision_id),
                    "signal_id": signal_id if isinstance(signal_id, str) else None,
                    "venue": self._venue,
                    "symbol": decision.symbol,
                    "request_payload": payload,
                    "state": "PREPARED",
                },
            )
            if not prepared:
                raise RuntimeError("execution intent PREPARED state was not persisted")
            if not await self._db_adapter.transition_execution_intent(
                idempotency_key,
                "SUBMITTING",
                venue=self._venue,
            ):
                raise RuntimeError("execution intent SUBMITTING state was not persisted")
            submission_started = True
            response = await self._place_bracket_with_retries(payload)
            if not isinstance(response, BracketPlacementResult):
                raise RouterProtocolError("Router client returned an untyped placement response")
            validate_bracket_placement(response, payload)
            response_payload = response.to_dict()

            await self._persist_orders_to_db(
                event, response_payload, client_ids, tp_prices, is_futures
            )
            await self._notify_snapshot(event, idempotency_key)
            await self._emit_order_placed(
                event,
                response_payload,
                client_ids.main,
                idempotency_key,
            )
            if not await self._db_adapter.transition_execution_intent(
                idempotency_key,
                "ACKNOWLEDGED",
                venue=self._venue,
                response_payload=response_payload,
            ):
                raise RuntimeError("execution intent ACKNOWLEDGED state was not persisted")
            intent_acknowledged = True

            logger.info(
                "Order placed successfully for %s %s",
                action,
                decision.symbol,
            )
        except Exception as exc:
            logger.exception(
                "Exception placing bracket order for %s %s",
                action,
                decision.symbol,
            )
            if (
                cooldown_acquired
                and not submission_started
                and self._cooldown is not None
                and zone_identity is not None
            ):
                await self._cooldown.release_async(
                    decision.symbol,
                    timeframe_str,
                    zone_identity.zone_id,
                    action,
                    venue=self._venue,
                )
            if submission_started and not intent_acknowledged:
                failure_state = (
                    "REJECTED"
                    if isinstance(exc, RouterHTTPError) and not exc.retryable
                    else "AMBIGUOUS"
                )
                await self._db_adapter.transition_execution_intent(
                    idempotency_key,
                    failure_state,
                    venue=self._venue,
                    error_message=str(exc),
                )
            error_type = "router_exception"
            if isinstance(exc, RouterProtocolError):
                error_type = "router_protocol_error"
            elif isinstance(exc, RouterHTTPError):
                error_type = "router_http_error"
            elif isinstance(exc, RouterCircuitOpenError):
                error_type = "router_circuit_open"
            elif isinstance(exc, RouterTransportError):
                error_type = "router_transport_error"
            elif "execution intent" in str(exc):
                error_type = "execution_intent_unavailable"
            await _emit_execution_error(self._bus, event, str(exc), error_type)

    async def _persist_orders_to_db(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_ids: _ClientOrderIDs,
        take_profit_prices: list[Decimal],
        is_futures: bool,
    ) -> None:
        """Persist order legs to DB before emitting event to prevent orphaned exchange orders."""
        decision = event.decision
        now = datetime.now(UTC)

        def _map_type(raw: str) -> str:
            typ = raw.strip().upper()
            # DB schema doesn't include STOP_MARKET; map to STOP_LOSS for audit purposes.
            if typ == "STOP_MARKET":
                return "STOP_LOSS"
            return typ

        action = str(decision.action).upper()
        bracket_order_id = response.get("bracket_order_id")

        qty = decision.quantity or Decimal(0)
        entry_price = decision.entry_price
        stop_loss = decision.stop_loss
        signal_id = event.metadata.get("signal_id")
        metadata_timeframe = event.metadata.get("timeframe")
        timeframe = (
            metadata_timeframe
            if isinstance(metadata_timeframe, str) and metadata_timeframe
            else (event.timeframe.value if event.timeframe else None)
        )
        zone = event.metadata.get("zone")
        sanitized_zone = _sanitize_value_for_json(zone) if isinstance(zone, dict) else None

        order_rows: list[dict[str, Any]] = []

        # Main order (always present)
        if entry_price is not None and qty > 0 and client_ids.main:
            order_rows.append(
                {
                    "client_order_id": client_ids.main,
                    "venue": self._venue,
                    "symbol": decision.symbol,
                    "side": action,
                    "type": _map_type("LIMIT"),
                    "quantity": str(qty),
                    "price": str(entry_price),
                    "status": "NEW",
                    "created_at": now,
                    "decision_id": str(decision.decision_id),
                    "exchange_order_id": bracket_order_id,
                    "signal_id": signal_id if isinstance(signal_id, str) else None,
                    "timeframe": timeframe,
                    "zone": sanitized_zone,
                },
            )

        # Take profit legs
        if take_profit_prices and qty > 0:
            tp_qty = qty / Decimal(len(take_profit_prices))
            for i, tp_price in enumerate(take_profit_prices):
                if i >= len(client_ids.take_profits):
                    break
                tp_client_id = client_ids.take_profits[i]
                if not tp_client_id:
                    continue
                order_rows.append(
                    {
                        "client_order_id": tp_client_id,
                        "venue": self._venue,
                        "symbol": decision.symbol,
                        "side": "SELL" if action == "BUY" else "BUY",
                        "type": _map_type("LIMIT"),
                        "quantity": str(tp_qty),
                        "price": str(tp_price),
                        "status": "NEW",
                        "created_at": now,
                        "decision_id": str(decision.decision_id),
                        "signal_id": signal_id if isinstance(signal_id, str) else None,
                        "timeframe": timeframe,
                        "zone": sanitized_zone,
                    },
                )

        # Stop loss leg
        if stop_loss is not None and qty > 0 and client_ids.stop_loss:
            if is_futures:
                order_rows.append(
                    {
                        "client_order_id": client_ids.stop_loss,
                        "venue": self._venue,
                        "symbol": decision.symbol,
                        "side": "SELL" if action == "BUY" else "BUY",
                        "type": _map_type("STOP_LOSS"),
                        "quantity": str(qty),
                        "price": None,
                        "stop_price": str(stop_loss),
                        "status": "NEW",
                        "created_at": now,
                        "decision_id": str(decision.decision_id),
                        "signal_id": signal_id if isinstance(signal_id, str) else None,
                        "timeframe": timeframe,
                        "zone": sanitized_zone,
                    },
                )
        if not order_rows:
            return

        persisted = await asyncio.gather(
            *(self._db_adapter.upsert_order(row) for row in order_rows)
        )
        if not all(persisted):
            raise RuntimeError("failed to persist all order legs after exchange acknowledgment")

    async def _emit_order_placed(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_order_id: str,
        idempotency_key: str,
    ) -> None:
        """Emit enriched OrderPlacedEvent for alerts."""
        decision = event.decision

        # Create Order object for the event
        order = Order(
            symbol=decision.symbol,
            side=OrderSide(str(decision.action).upper()),
            type=OrderType.LIMIT,
            quantity=decision.quantity or Decimal(0),
            price=decision.entry_price,
            status=OrderStatus.NEW,
            client_order_id=client_order_id,
            created_at=datetime.now(UTC),
        )

        order_event = OrderPlacedEvent(
            event_id=UUID(bytes=hashlib.sha256(idempotency_key.encode("utf-8")).digest()[:16]),
            timestamp=datetime.now(UTC),
            symbol=decision.symbol,
            timeframe=event.timeframe,
            metadata=event.metadata,
            order=order,
            decision=decision,
            router_response=response,
        )

        if not await self._bus.publish_and_wait(order_event, priority=7):
            raise RuntimeError("event bus did not acknowledge OrderPlacedEvent delivery")

    async def _notify_snapshot(self, event: TradingDecisionEvent, idempotency_key: str) -> None:
        """Trigger snapshot generation via BFF client."""
        if self._bff_client is None:
            return

        decision = event.decision
        side = "BUY" if str(decision.action).upper() == "BUY" else "SELL"

        payload = {
            "idempotencyKey": idempotency_key,
            "signalId": event.metadata.get("signal_id"),
            "symbol": decision.symbol,
            "venue": event.metadata.get("venue", "SPOT"),
            "side": side,
            "entry": str(decision.entry_price) if decision.entry_price else None,
            "stopLoss": str(decision.stop_loss) if decision.stop_loss else None,
            "takeProfit": str(decision.take_profit) if decision.take_profit else None,
            "confidence": str(decision.confidence) if decision.confidence else None,
            "reasons": decision.reasoning.split("; ") if decision.reasoning else [],
            "timeframe": event.timeframe.value if event.timeframe else None,
            "signalTime": decision.timestamp.isoformat() if decision.timestamp else None,
        }

        await self._bff_client.post("/api/signals/alert", payload)
