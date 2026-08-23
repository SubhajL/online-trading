from __future__ import annotations

import asyncio
from collections.abc import Mapping
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
from app.engine.contracts.contract_publisher import order_placed_event_to_order_update_payload
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
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)
from app.engine.resilience.backoff import BackoffConfig, ExponentialBackoff

if TYPE_CHECKING:
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
        success_delivery_poll_interval_seconds: float = 1.0,
        success_delivery_venues: tuple[str, ...] | None = None,
        execution_intent_recovery_poll_interval_seconds: float = 1.0,
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
        if success_delivery_poll_interval_seconds <= 0:
            raise ValueError("success_delivery_poll_interval_seconds must be > 0")
        self._success_delivery_poll_interval_seconds = success_delivery_poll_interval_seconds
        if execution_intent_recovery_poll_interval_seconds <= 0:
            raise ValueError("execution_intent_recovery_poll_interval_seconds must be > 0")
        self._execution_intent_recovery_poll_interval_seconds = (
            execution_intent_recovery_poll_interval_seconds
        )
        configured_delivery_venues = (
            (venue,) if success_delivery_venues is None else tuple(success_delivery_venues)
        )
        if not configured_delivery_venues or any(
            not isinstance(delivery_venue, str) or not delivery_venue
            for delivery_venue in configured_delivery_venues
        ):
            raise ValueError("success_delivery_venues must contain at least one venue")
        self._success_delivery_venues = tuple(dict.fromkeys(configured_delivery_venues))
        self._started = False
        self._lifecycle_lock = asyncio.Lock()
        self._subscription_id: str | None = None
        self._success_delivery_tasks: dict[str, asyncio.Task[None]] = {}
        self._execution_intent_recovery_task: asyncio.Task[None] | None = None
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
        async with self._lifecycle_lock:
            if self._started:
                return
            try:
                if self._execution_mode != ExecutionMode.DISABLED:
                    await self._verify_router_execution_env()
                    if await self._db_adapter.has_incomplete_execution_intent_outside_venue(
                        self._venue,
                    ):
                        raise RuntimeError(
                            f"Cannot start router execution for active venue {self._venue}: "
                            "incomplete execution intent exists for an inactive venue"
                        )

                    self._subscription_id = await self._bus.subscribe(
                        subscriber_id="router-execution",
                        handler=self._on_trading_decision,
                        event_types=[EventType.TRADING_DECISION],
                        priority=5,
                    )
                    self._execution_intent_recovery_task = asyncio.create_task(
                        self._run_execution_intent_recovery(self._venue),
                        name=f"router-execution-intent-recovery-{self._venue}",
                    )
                for delivery_venue in self._success_delivery_venues:
                    self._success_delivery_tasks[delivery_venue] = asyncio.create_task(
                        self._run_success_delivery_drain(delivery_venue),
                        name=f"router-execution-success-delivery-{delivery_venue}",
                    )
                self._started = True
            except BaseException:
                await self._stop_unlocked()
                raise

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
        async with self._lifecycle_lock:
            await self._stop_unlocked()

    async def _stop_unlocked(self) -> None:
        tasks = list(self._success_delivery_tasks.values())
        recovery_task = self._execution_intent_recovery_task
        self._execution_intent_recovery_task = None
        for task in tasks:
            task.cancel()
        if recovery_task is not None:
            recovery_task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if recovery_task is not None:
            await asyncio.gather(recovery_task, return_exceptions=True)
        self._success_delivery_tasks.clear()
        subscription_id = self._subscription_id
        self._subscription_id = None
        self._started = False
        if subscription_id is not None:
            await self._bus.unsubscribe(subscription_id)

    async def _run_success_delivery_drain(self, venue: str) -> None:
        claim_next = getattr(self._db_adapter, "claim_next_execution_success_delivery", None)
        if not callable(claim_next):
            return
        while True:
            try:
                claim = await claim_next(venue=venue)
                if claim is None:
                    await asyncio.sleep(self._success_delivery_poll_interval_seconds)
                    continue
                if isinstance(claim, dict):
                    claim = dict(claim)
                    claim.setdefault("venue", venue)
                delivered = await self._process_success_delivery_claim(claim, event=None)
                if not delivered:
                    await asyncio.sleep(self._success_delivery_poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Success delivery drain iteration failed for venue=%s", venue)
                await asyncio.sleep(self._success_delivery_poll_interval_seconds)

    async def _run_execution_intent_recovery(self, venue: str) -> None:
        claim_next = getattr(self._db_adapter, "claim_next_execution_intent_recovery", None)
        if not callable(claim_next):
            return
        while True:
            try:
                claim = await claim_next(venue=venue)
                if claim is None:
                    await self._wait_for_execution_intent_recovery_poll()
                    continue
                if not isinstance(claim, dict):
                    raise RuntimeError("execution intent recovery claim is malformed")
                event = self._build_execution_intent_recovery_event(claim)
                symbol_lock = self._get_symbol_lock(event.decision.symbol)
                async with symbol_lock:
                    await self._execute_decision(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Execution intent recovery iteration failed for venue=%s", venue)
            await self._wait_for_execution_intent_recovery_poll()

    async def _wait_for_execution_intent_recovery_poll(self) -> None:
        loop = asyncio.get_running_loop()
        wake = loop.create_future()
        timer = loop.call_later(
            self._execution_intent_recovery_poll_interval_seconds,
            wake.set_result,
            None,
        )
        try:
            await wake
        finally:
            timer.cancel()

    def _build_execution_intent_recovery_event(
        self,
        claim: dict[str, Any],
    ) -> TradingDecisionEvent:
        venue = claim.get("venue")
        idempotency_key = claim.get("idempotency_key")
        payload = claim.get("request_payload")
        state = claim.get("state")
        if venue != self._venue or not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("execution intent recovery claim identity is malformed")
        if state not in {"SUBMITTING", "AMBIGUOUS"} or not isinstance(payload, dict):
            raise ValueError("execution intent recovery claim state or payload is malformed")
        if payload.get("idempotency_key") != idempotency_key:
            raise ValueError("execution intent recovery payload key is malformed")

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("execution intent recovery metadata is malformed")
        metadata = dict(metadata)
        if metadata.get("venue") not in {None, venue}:
            raise ValueError("execution intent recovery venue is malformed")
        decision_source = metadata.get("decision_source")
        if decision_source != "retest_decision_publisher":
            raise ValueError("execution intent recovery decision source is malformed")

        symbol = payload.get("symbol")
        action = str(payload.get("side") or "").upper()
        order_type = str(payload.get("order_type") or "").upper()
        if not isinstance(symbol, str) or not symbol or action not in {"BUY", "SELL"}:
            raise ValueError("execution intent recovery decision identity is malformed")
        if order_type != "LIMIT":
            raise ValueError("execution intent recovery order type is malformed")

        def _positive_decimal(value: Any, field_name: str) -> Decimal:
            try:
                parsed = Decimal(str(value))
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ValueError(f"execution intent recovery {field_name} is malformed") from exc
            if not parsed.is_finite() or parsed <= 0:
                raise ValueError(f"execution intent recovery {field_name} is malformed")
            return parsed

        entry_price = _positive_decimal(payload.get("entry_price"), "entry price")
        stop_loss = _positive_decimal(payload.get("stop_loss_price"), "stop loss")
        quantity = _positive_decimal(payload.get("quantity"), "quantity")
        take_profit_prices = payload.get("take_profit_prices")
        if not isinstance(take_profit_prices, list) or len(take_profit_prices) != 1:
            raise ValueError("execution intent recovery take profit is malformed")
        take_profit = _positive_decimal(take_profit_prices[0], "take profit")

        decision_id_value = metadata.get("decision_id")
        try:
            decision_id = UUID(str(decision_id_value))
        except (AttributeError, ValueError) as exc:
            raise ValueError("execution intent recovery decision ID is malformed") from exc

        decision_timestamp_value = payload.get("decision_ts") or metadata.get("decision_time")
        if not isinstance(decision_timestamp_value, str):
            raise ValueError("execution intent recovery decision time is malformed")
        try:
            decision_timestamp = datetime.fromisoformat(decision_timestamp_value)
        except ValueError as exc:
            raise ValueError("execution intent recovery decision time is malformed") from exc
        if decision_timestamp.tzinfo is None:
            decision_timestamp = decision_timestamp.replace(tzinfo=UTC)

        raw_timeframe = metadata.get("timeframe")
        timeframe: TimeFrame | None = None
        if raw_timeframe not in {None, "", "unknown"}:
            try:
                timeframe = TimeFrame(str(raw_timeframe))
            except ValueError as exc:
                raise ValueError("execution intent recovery timeframe is malformed") from exc
        zone = metadata.get("zone")
        if zone is not None and not isinstance(zone, dict):
            raise ValueError("execution intent recovery zone is malformed")

        is_futures = self._execution_mode in {
            ExecutionMode.FUTURES_TESTNET,
            ExecutionMode.FUTURES_MAINNET,
        }
        if payload.get("is_futures") is not is_futures:
            raise ValueError("execution intent recovery execution mode is malformed")
        client_order_ids = payload.get("client_order_ids")
        expected_client_order_ids = _build_client_order_ids(
            key=idempotency_key,
            tp_count=len(take_profit_prices),
        )
        expected_client_order_ids_payload = {
            "main": expected_client_order_ids.main,
            "take_profits": expected_client_order_ids.take_profits,
            "stop_loss": expected_client_order_ids.stop_loss,
        }
        if client_order_ids != expected_client_order_ids_payload:
            raise ValueError("execution intent recovery client IDs are malformed")

        metadata.setdefault("venue", venue)
        metadata.setdefault("signal_id", None)
        metadata.setdefault("decision_id", str(decision_id))
        metadata.setdefault("timeframe", raw_timeframe)
        metadata.setdefault("zone", zone)
        metadata.setdefault("decision_time", decision_timestamp.isoformat())
        decision = TradingDecision(
            decision_id=decision_id,
            venue=venue,
            symbol=symbol,
            timestamp=decision_timestamp,
            action=action,
            entry_price=entry_price,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=self._min_confidence,
            reasoning="Recovered execution intent",
        )
        return TradingDecisionEvent(
            timestamp=decision_timestamp,
            symbol=symbol,
            timeframe=timeframe,
            decision=decision,
            metadata=metadata,
        )

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

        metadata_timeframe = event.metadata.get("timeframe")
        timeframe = (
            metadata_timeframe
            if isinstance(metadata_timeframe, str) and metadata_timeframe
            else (event.timeframe.value if event.timeframe else None)
        )
        zone = event.metadata.get("zone")
        zone_identity = extract_zone_identity(event.metadata)
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

        try:
            execution_intent = await self._db_adapter.get_execution_intent_for_request(
                idempotency_key,
                venue=self._venue,
                request_payload=payload,
            )
        except Exception as exc:
            logger.exception(
                "Execution intent lookup failed for idempotency_key=%s",
                idempotency_key,
            )
            await _emit_execution_error(
                self._bus,
                event,
                str(exc),
                "execution_intent_unavailable",
            )
            return

        recovery_mode = False
        if execution_intent is not None:
            if not isinstance(execution_intent, dict):
                await _emit_execution_error(
                    self._bus,
                    event,
                    "execution intent state or request payload is malformed",
                    "execution_intent_unavailable",
                )
                return
            intent_state = execution_intent.get("state")
            stored_payload = execution_intent.get("request_payload")
            valid_states = {
                "PREPARED",
                "SUBMITTING",
                "AMBIGUOUS",
                "ACKNOWLEDGED",
                "REJECTED",
            }
            if not isinstance(intent_state, str) or intent_state not in valid_states:
                await _emit_execution_error(
                    self._bus,
                    event,
                    "execution intent state or request payload is malformed",
                    "execution_intent_unavailable",
                )
                return
            if not isinstance(stored_payload, dict):
                await _emit_execution_error(
                    self._bus,
                    event,
                    "execution intent state or request payload is malformed",
                    "execution_intent_unavailable",
                )
                return
            if intent_state in {"SUBMITTING", "AMBIGUOUS"}:
                recovery_mode = True
                payload = stored_payload
            elif intent_state == "ACKNOWLEDGED":
                response_payload = execution_intent.get("response_payload")
                if not isinstance(response_payload, dict):
                    await _emit_execution_error(
                        self._bus,
                        event,
                        "execution intent response payload is malformed",
                        "execution_intent_unavailable",
                    )
                    return
                await self._resume_success_delivery(
                    event,
                    idempotency_key,
                )
                return
            elif intent_state == "REJECTED":
                await _emit_execution_error(
                    self._bus,
                    event,
                    f"execution intent is already {intent_state}",
                    "execution_intent_unavailable",
                )
                return

        if not recovery_mode:
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

            ok, reasons = evaluate_pretrade_risk(
                snapshot=snapshot,
                decision=decision,
                risk=self._risk,
            )
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

        if not recovery_mode:
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
            not recovery_mode
            and self._cooldown is not None
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

        submission_started = False
        ack_commit_started = False
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

            ack_commit_started = True
            order_rows = self._build_order_projection_rows(
                event,
                response_payload,
                client_ids,
                tp_prices,
                is_futures,
            )
            order_placed_event = self._build_order_placed_event(
                event,
                response_payload,
                client_ids.main,
                idempotency_key,
            )
            deliveries = [
                {
                    "delivery_kind": "ORDER_PLACED",
                    "delivery_payload": order_placed_event.model_dump(mode="json"),
                },
            ]
            if self._bff_client is not None:
                deliveries.insert(
                    0,
                    {
                        "delivery_kind": "SNAPSHOT",
                        "delivery_payload": self._build_snapshot_payload(
                            event,
                            idempotency_key,
                        ),
                    },
                )
            if not await self._db_adapter.commit_execution_ack(
                idempotency_key,
                venue=self._venue,
                response_payload=response_payload,
                order_rows=order_rows,
                deliveries=deliveries,
            ):
                raise RuntimeError("execution intent ACKNOWLEDGED state was not persisted")
            intent_acknowledged = True

            await self._resume_success_delivery(
                event,
                idempotency_key,
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
                    "AMBIGUOUS"
                    if ack_commit_started
                    else (
                        "REJECTED"
                        if isinstance(exc, RouterHTTPError) and not exc.retryable
                        else "AMBIGUOUS"
                    )
                )
                await self._db_adapter.transition_execution_intent(
                    idempotency_key,
                    failure_state,
                    venue=self._venue,
                    error_message=str(exc),
                )
            error_type = "router_exception"
            if ack_commit_started and not intent_acknowledged:
                error_type = "execution_intent_unavailable"
            elif isinstance(exc, RouterProtocolError):
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

    def _build_order_projection_rows(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_ids: _ClientOrderIDs,
        take_profit_prices: list[Decimal],
        is_futures: bool,
    ) -> list[dict[str, Any]]:
        """Build authoritative order-leg projections without database side effects."""
        decision = event.decision
        now = datetime.now(UTC)

        def _map_type(raw: str) -> str:
            typ = raw.strip().upper()
            # DB schema doesn't include STOP_MARKET; map to STOP_LOSS for audit purposes.
            if typ == "STOP_MARKET":
                return "STOP_LOSS"
            return typ

        action = str(decision.action).upper()
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
                    "exchange_order_id": None,
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
        return order_rows

    async def _persist_orders_to_db(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_ids: _ClientOrderIDs,
        take_profit_prices: list[Decimal],
        is_futures: bool,
    ) -> None:
        """Persist order legs for compatibility with direct callers and tests."""
        order_rows = self._build_order_projection_rows(
            event,
            response,
            client_ids,
            take_profit_prices,
            is_futures,
        )
        if not order_rows:
            return

        persisted = await asyncio.gather(
            *(self._db_adapter.upsert_order(row) for row in order_rows)
        )
        if not all(persisted):
            raise RuntimeError("failed to persist all order legs after exchange acknowledgment")

    async def _fail_success_delivery(
        self,
        event: TradingDecisionEvent | None,
        *,
        venue: str,
        idempotency_key: str,
        delivery_kind: str,
        lease_token: str,
        error_message: str,
    ) -> None:
        try:
            await self._db_adapter.fail_execution_success_delivery(
                idempotency_key,
                venue=venue,
                delivery_kind=delivery_kind,
                lease_token=lease_token,
                error_message=error_message,
            )
        except Exception:
            logger.exception(
                "Failed to return success delivery to pending: venue=%s idempotency_key=%s kind=%s",
                venue,
                idempotency_key,
                delivery_kind,
            )
        if event is not None:
            await _emit_execution_error(
                self._bus,
                event,
                error_message,
                "success_delivery_pending",
            )
        else:
            logger.error(
                "Success delivery remains pending: venue=%s idempotency_key=%s kind=%s error=%s",
                venue,
                idempotency_key,
                delivery_kind,
                error_message,
            )

    async def _process_success_delivery_claim(
        self,
        claim: dict[str, Any] | Any,
        *,
        event: TradingDecisionEvent | None,
    ) -> bool:
        if not isinstance(claim, dict):
            message = "success delivery claim is malformed"
            if event is not None:
                await _emit_execution_error(
                    self._bus,
                    event,
                    message,
                    "success_delivery_pending",
                )
            else:
                logger.error(message)
            return False

        idempotency_key = claim.get("idempotency_key")
        venue = claim.get("venue", self._venue)
        delivery_kind = claim.get("delivery_kind")
        lease_token = claim.get("lease_token")
        delivery_payload = claim.get("delivery_payload")
        if (
            not isinstance(idempotency_key, str)
            or not isinstance(venue, str)
            or not venue
            or not isinstance(delivery_kind, str)
            or delivery_kind not in {"SNAPSHOT", "ORDER_PLACED"}
            or not isinstance(lease_token, str)
            or not isinstance(delivery_payload, dict)
        ):
            message = "success delivery claim is malformed"
            if event is not None:
                await _emit_execution_error(
                    self._bus,
                    event,
                    message,
                    "success_delivery_pending",
                )
            else:
                logger.error(message)
            return False

        try:
            if delivery_kind == "SNAPSHOT":
                if not await self._notify_snapshot_payload(delivery_payload):
                    raise RuntimeError("snapshot delivery was not acknowledged")
            else:
                order_event = OrderPlacedEvent.model_validate(delivery_payload)
                if self._bff_client is None:
                    raise RuntimeError("order placement delivery was not durably acknowledged")
                try:
                    bff_response = await self._bff_client.post(
                        "/api/internal/trading/order-update",
                        order_placed_event_to_order_update_payload(order_event),
                    )
                except Exception as exc:
                    raise RuntimeError(
                        "order placement delivery was not durably acknowledged"
                    ) from exc
                if not isinstance(bff_response, dict) or bff_response.get("ok") is not True:
                    raise RuntimeError("order placement delivery was not durably acknowledged")
                await self._emit_order_placed_payload(delivery_payload)
        except Exception as exc:
            await self._fail_success_delivery(
                event,
                venue=venue,
                idempotency_key=idempotency_key,
                delivery_kind=delivery_kind,
                lease_token=lease_token,
                error_message=str(exc),
            )
            return False

        try:
            await self._db_adapter.complete_execution_success_delivery(
                idempotency_key,
                venue=venue,
                delivery_kind=delivery_kind,
                lease_token=lease_token,
            )
        except Exception as exc:
            await self._fail_success_delivery(
                event,
                venue=venue,
                idempotency_key=idempotency_key,
                delivery_kind=delivery_kind,
                lease_token=lease_token,
                error_message=str(exc),
            )
            return False
        return True

    async def _resume_success_delivery(
        self,
        event: TradingDecisionEvent,
        idempotency_key: str,
        venue: str | None = None,
    ) -> None:
        delivery_venue = venue or self._venue
        completed_any = False
        while True:
            try:
                claim = await self._db_adapter.claim_execution_success_delivery(
                    idempotency_key,
                    venue=delivery_venue,
                )
            except Exception as exc:
                await _emit_execution_error(
                    self._bus,
                    event,
                    str(exc),
                    "success_delivery_pending",
                )
                return

            if claim is None:
                try:
                    has_pending = await self._db_adapter.has_pending_execution_success_delivery(
                        idempotency_key,
                        venue=delivery_venue,
                    )
                except Exception as exc:
                    await _emit_execution_error(
                        self._bus,
                        event,
                        str(exc),
                        "success_delivery_pending",
                    )
                    return
                if not has_pending and completed_any:
                    decision = event.decision
                    logger.info(
                        "Order placed successfully for %s %s",
                        str(decision.action).upper(),
                        decision.symbol,
                    )
                return

            if not isinstance(claim, dict):
                await _emit_execution_error(
                    self._bus,
                    event,
                    "success delivery claim is malformed",
                    "success_delivery_pending",
                )
                return
            claim = dict(claim)
            claim.setdefault("idempotency_key", idempotency_key)
            claim.setdefault("venue", delivery_venue)
            if not await self._process_success_delivery_claim(claim, event=event):
                return
            completed_any = True

    def _execution_identity_digest(self, domain: str, idempotency_key: str) -> str:
        identity = f"{domain}:{self._venue.upper()}:{idempotency_key}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _snapshot_id(self, idempotency_key: str) -> str:
        return f"exec_{self._execution_identity_digest('snapshot', idempotency_key)[:32]}"

    def _build_snapshot_payload(
        self,
        event: TradingDecisionEvent,
        idempotency_key: str,
    ) -> dict[str, Any]:
        decision = event.decision
        timestamp = decision.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        metadata_timeframe = event.metadata.get("timeframe")
        timeframe = (
            metadata_timeframe
            if isinstance(metadata_timeframe, str) and metadata_timeframe
            else (event.timeframe.value if event.timeframe else "unknown")
        )

        def _json_number(value: Decimal | None) -> float:
            if value is None or not value.is_finite():
                return 0.0
            return float(value)

        return {
            "signalId": self._snapshot_id(idempotency_key),
            "symbol": decision.symbol,
            "venue": self._venue,
            "side": "BUY" if str(decision.action).upper() == "BUY" else "SELL",
            "entry": _json_number(decision.entry_price),
            "stopLoss": _json_number(decision.stop_loss),
            "takeProfit": _json_number(decision.take_profit),
            "confidence": _json_number(decision.confidence),
            "reasons": decision.reasoning.split("; ") if decision.reasoning else [],
            "timeframe": timeframe,
            "signalTime": timestamp.isoformat(),
        }

    async def _notify_snapshot_payload(self, payload: dict[str, Any]) -> bool:
        if self._bff_client is None:
            return False
        response = await self._bff_client.post("/api/signals/alert", payload)
        return isinstance(response, Mapping) and response.get("ok") is True

    async def _notify_snapshot(self, event: TradingDecisionEvent, idempotency_key: str) -> bool:
        """Trigger snapshot generation via the persisted BFF payload shape."""
        return await self._notify_snapshot_payload(
            self._build_snapshot_payload(event, idempotency_key),
        )

    def _build_order_placed_event(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_order_id: str,
        idempotency_key: str,
    ) -> OrderPlacedEvent:
        decision = event.decision
        raw_signal_id = event.metadata.get("signal_id")
        metadata = dict(event.metadata)
        metadata["signal_id"] = self._snapshot_id(idempotency_key)
        metadata["venue"] = self._venue
        if isinstance(raw_signal_id, str) and raw_signal_id:
            metadata["source_signal_id"] = raw_signal_id

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
        event_digest = self._execution_identity_digest("order_placed", idempotency_key)
        return OrderPlacedEvent(
            event_id=UUID(bytes=bytes.fromhex(event_digest[:32])),
            timestamp=datetime.now(UTC),
            symbol=decision.symbol,
            timeframe=event.timeframe,
            metadata=metadata,
            order=order,
            decision=decision,
            router_response=response,
        )

    async def _emit_order_placed_payload(self, payload: dict[str, Any]) -> None:
        order_event = OrderPlacedEvent.model_validate(payload)
        if not await self._bus.publish_and_wait(order_event, priority=7):
            raise RuntimeError("event bus did not acknowledge OrderPlacedEvent delivery")

    async def _emit_order_placed(
        self,
        event: TradingDecisionEvent,
        response: dict[str, Any],
        client_order_id: str,
        idempotency_key: str,
    ) -> None:
        """Emit an enriched, venue-scoped OrderPlacedEvent for alerts."""
        await self._emit_order_placed_payload(
            self._build_order_placed_event(
                event,
                response,
                client_order_id,
                idempotency_key,
            ).model_dump(mode="json"),
        )
