from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from typing import Any, Protocol

from app.engine.models import ErrorEvent

logger = logging.getLogger(__name__)


class _EventBus(Protocol):
    async def publish(self, event: Any, priority: int = 0) -> bool: ...


class _IngestService(Protocol):
    async def health_check(self) -> dict[str, object]: ...


_TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}


@dataclass(frozen=True)
class PipelineHealthThresholds:
    stale_ws_seconds: int = 120
    candle_lag_multiplier: float = 2.2
    candle_lag_grace_seconds: int = 60
    min_alert_interval_seconds: int = 300
    poll_interval_seconds: int = 30
    startup_grace_seconds: int = 120  # Suppress alerts during startup/backfill


@dataclass(frozen=True)
class PipelineHealthIssue:
    key: str
    symbol: str
    error_type: str
    message: str
    details: dict[str, object]


def _max_allowed_candle_age_seconds(
    *,
    timeframe: str,
    thresholds: PipelineHealthThresholds,
) -> float | None:
    seconds = _TIMEFRAME_SECONDS.get(timeframe)
    if seconds is None:
        return None
    return seconds * thresholds.candle_lag_multiplier + thresholds.candle_lag_grace_seconds


def _recovery_context(websocket: dict[str, object]) -> dict[str, object]:
    details: dict[str, object] = {}

    for key in (
        "last_connect_error_kind",
        "last_connect_error",
        "last_connect_error_ago_seconds",
        "consecutive_failures",
        "consecutive_dns_failures",
        "last_subscribe_ok_ago_seconds",
        "last_subscribe_error_ago_seconds",
        "last_subscribe_error",
        "backoff_attempt",
        "max_reconnect_attempts",
        "dispatch_queue_size",
        "dispatch_queue_max",
    ):
        value = websocket.get(key)
        if isinstance(value, (str, int, float)) and value != "":
            details[key] = value

    return details


def evaluate_pipeline_health(
    *,
    ingest_health: dict[str, object],
    now: datetime,
    thresholds: PipelineHealthThresholds,
) -> list[PipelineHealthIssue]:
    websocket = ingest_health.get("websocket")
    issues: list[PipelineHealthIssue] = []
    suppress_candle_stale = False

    if isinstance(websocket, dict):
        ws_open = websocket.get("open")
        if isinstance(ws_open, bool):
            ws_is_open = ws_open
        else:
            # Backward compat: older health payloads only exposed "connected".
            ws_is_open = websocket.get("connected") is True

        ws_connected = websocket.get("connected") is True
        ws_stale = websocket.get("stale") is True
        ws_last_ago = websocket.get("last_message_ago_seconds")
        ws_last_closed_kline_ago = websocket.get("last_closed_kline_ago_seconds")
        consecutive_failures = websocket.get("consecutive_failures")
        recovery_details = _recovery_context(websocket)

        if not ws_is_open:
            # Hard disconnect — report as root cause (supersedes stale and kline_stream_stale)
            details: dict[str, object] = {
                "last_message_ago_seconds": ws_last_ago,
                "consecutive_failures": consecutive_failures,
                **recovery_details,
            }
            last_connect_error_kind = websocket.get("last_connect_error_kind")
            if isinstance(last_connect_error_kind, str) and last_connect_error_kind:
                details["last_connect_error_kind"] = last_connect_error_kind
            last_connect_error = websocket.get("last_connect_error")
            if isinstance(last_connect_error, str) and last_connect_error:
                details["last_connect_error"] = last_connect_error
            last_connect_error_ago = websocket.get("last_connect_error_ago_seconds")
            if isinstance(last_connect_error_ago, (int, float)):
                details["last_connect_error_ago_seconds"] = last_connect_error_ago
            consecutive_dns_failures = websocket.get("consecutive_dns_failures")
            if isinstance(consecutive_dns_failures, int) and consecutive_dns_failures > 0:
                details["consecutive_dns_failures"] = consecutive_dns_failures
            if last_connect_error_kind == "dns" or (
                isinstance(consecutive_dns_failures, int) and consecutive_dns_failures > 0
            ):
                details["recovery_stage"] = "dns_recovery"
            elif isinstance(websocket.get("backoff_attempt"), int) and websocket.get("backoff_attempt", 0) > 0:
                details["recovery_stage"] = "reconnect_backoff"
            else:
                details["recovery_stage"] = "reconnect_pending"

            # Include a small summary of candle ages so operators don't lose context,
            # but suppress per-symbol candle_stale spam while WS is down.
            latest_candle_ago_seconds = ingest_health.get("latest_candle_ago_seconds")
            worst: list[dict[str, object]] = []
            if isinstance(latest_candle_ago_seconds, dict):
                for symbol, by_tf in latest_candle_ago_seconds.items():
                    if not isinstance(symbol, str) or not isinstance(by_tf, dict):
                        continue
                    for timeframe, age in by_tf.items():
                        if not isinstance(timeframe, str) or not isinstance(age, (int, float)):
                            continue
                        allowed = _max_allowed_candle_age_seconds(
                            timeframe=timeframe,
                            thresholds=thresholds,
                        )
                        worst.append(
                            {
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "latest_candle_ago_seconds": float(age),
                                "max_allowed_candle_age_seconds": allowed,
                            },
                        )
            worst.sort(key=lambda x: float(x.get("latest_candle_ago_seconds", 0.0)), reverse=True)
            if worst:
                details["worst_candles"] = worst[:5]

            issues.append(
                PipelineHealthIssue(
                    key="websocket_disconnected",
                    symbol="SYSTEM",
                    error_type="websocket_disconnected",
                    message="WebSocket is disconnected",
                    details=details,
                ),
            )
            return issues
        else:
            ws_last_is_over_threshold = ws_last_ago is None or (
                isinstance(ws_last_ago, (int, float)) and ws_last_ago > thresholds.stale_ws_seconds
            )
            if ws_stale or ws_last_is_over_threshold:
                # WS stale supersedes kline_stream_stale (if WS is stale, klines are obviously stale too)
                issues.append(
                    PipelineHealthIssue(
                        key="websocket_stale",
                        symbol="SYSTEM",
                        error_type="websocket_stale",
                        message="WebSocket connected but not receiving messages",
                        details={
                            "last_message_ago_seconds": ws_last_ago,
                            "stale_threshold_seconds": thresholds.stale_ws_seconds,
                            "consecutive_failures": consecutive_failures,
                            "recovery_stage": "message_gap_repair",
                            **recovery_details,
                        },
                    ),
                )
                suppress_candle_stale = True
            else:
                kline_subscriptions = websocket.get("kline_subscriptions")
                ticker_subscriptions = websocket.get("ticker_subscriptions")
                if isinstance(kline_subscriptions, int) and kline_subscriptions <= 0:
                    issues.append(
                        PipelineHealthIssue(
                            key="kline_not_subscribed",
                            symbol="SYSTEM",
                            error_type="kline_not_subscribed",
                            message="WebSocket connected but no kline subscriptions are active",
                            details={
                                "subscriptions": websocket.get("subscriptions"),
                                "kline_subscriptions": kline_subscriptions,
                                "ticker_subscriptions": ticker_subscriptions,
                                "last_subscribe_ok_ago_seconds": websocket.get(
                                    "last_subscribe_ok_ago_seconds",
                                ),
                                "last_subscribe_error_ago_seconds": websocket.get(
                                    "last_subscribe_error_ago_seconds",
                                ),
                                "last_subscribe_error": websocket.get(
                                    "last_subscribe_error",
                                ),
                                "recovery_stage": "subscription_repair",
                                **recovery_details,
                            },
                        ),
                    )
                    return issues

                # WS is connected and receiving messages (tickers flowing),
                # but check if klines specifically are stale ("tickers alive, klines dead")
                # Use last_kline_ago_seconds (any kline, open or closed) because:
                # - Open klines arrive frequently (every few seconds during active trading)
                # - Closed klines only arrive at timeframe intervals (e.g., every 5m)
                # - Using stale_ws_seconds (120s default) for any-kline is appropriate
                ws_last_kline_ago = websocket.get("last_kline_ago_seconds")
                kline_is_missing = ws_last_kline_ago is None
                kline_is_stale = isinstance(ws_last_kline_ago, (int, float)) and (
                    ws_last_kline_ago > thresholds.stale_ws_seconds
                )
                if kline_is_missing or kline_is_stale:
                    issues.append(
                        PipelineHealthIssue(
                            key="kline_stream_stale",
                            symbol="SYSTEM",
                            error_type="kline_stream_stale",
                            message="WebSocket connected but klines not arriving",
                            details={
                                "last_kline_ago_seconds": ws_last_kline_ago,
                                "last_closed_kline_ago_seconds": ws_last_closed_kline_ago,
                                "last_message_ago_seconds": ws_last_ago,
                                "stale_threshold_seconds": thresholds.stale_ws_seconds,
                                "last_subscribe_ok_ago_seconds": websocket.get(
                                    "last_subscribe_ok_ago_seconds",
                                ),
                                "last_subscribe_error_ago_seconds": websocket.get(
                                    "last_subscribe_error_ago_seconds",
                                ),
                                "last_subscribe_error": websocket.get(
                                    "last_subscribe_error",
                                ),
                                "recovery_stage": "kline_gap_repair",
                                **recovery_details,
                            },
                        ),
                    )
                    suppress_candle_stale = True

    if suppress_candle_stale:
        return issues

    latest_candle_ago_seconds = ingest_health.get("latest_candle_ago_seconds")
    if isinstance(latest_candle_ago_seconds, dict):
        for symbol, by_tf in latest_candle_ago_seconds.items():
            if not isinstance(symbol, str) or not isinstance(by_tf, dict):
                continue
            for timeframe, age in by_tf.items():
                if not isinstance(timeframe, str) or not isinstance(age, (int, float)):
                    continue
                allowed = _max_allowed_candle_age_seconds(
                    timeframe=timeframe,
                    thresholds=thresholds,
                )
                if allowed is None:
                    continue
                if age > allowed:
                    issues.append(
                        PipelineHealthIssue(
                            key=f"candle_stale:{symbol}:{timeframe}",
                            symbol=symbol,
                            error_type="candle_stale",
                            message="No recent closed candle for symbol/timeframe",
                            details={
                                "timeframe": timeframe,
                                "latest_candle_ago_seconds": age,
                                "max_allowed_candle_age_seconds": allowed,
                                "evaluated_at": now.isoformat(),
                            },
                        ),
                    )

    return issues


class PipelineHealthService:
    def __init__(
        self,
        *,
        bus: _EventBus,
        ingest_service: _IngestService,
        thresholds: PipelineHealthThresholds | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._bus = bus
        self._ingest_service = ingest_service
        self._thresholds = thresholds or PipelineHealthThresholds()
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_sent_at: dict[str, datetime] = {}
        self._started_at: datetime | None = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._started_at = self._now_fn()
        self._task = asyncio.create_task(self._run())
        logger.info("PipelineHealthService started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        logger.info("PipelineHealthService stopped")

    async def _run(self) -> None:
        while self._running:
            await self._check_once()
            await asyncio.sleep(self._thresholds.poll_interval_seconds)

    def _is_within_startup_grace_period(self, now: datetime) -> bool:
        """Check if we're still within the startup grace period."""
        if self._started_at is None:
            return False
        elapsed = max(0.0, (now - self._started_at).total_seconds())
        return elapsed < self._thresholds.startup_grace_seconds

    async def _check_once(self) -> None:
        now = self._now_fn()

        # Skip health checks during startup grace period to allow backfill
        if self._is_within_startup_grace_period(now):
            return

        try:
            ingest_health = await self._ingest_service.health_check()
        except Exception:
            logger.exception("Pipeline health check failed")
            return
        issues = evaluate_pipeline_health(
            ingest_health=ingest_health,
            now=now,
            thresholds=self._thresholds,
        )

        for issue in issues:
            if not self._should_emit(issue.key, now):
                continue
            await self._emit_issue(issue, now)

    def _should_emit(self, key: str, now: datetime) -> bool:
        last_sent = self._last_sent_at.get(key)
        if last_sent is None:
            return True
        elapsed = (now - last_sent).total_seconds()
        return elapsed >= self._thresholds.min_alert_interval_seconds

    async def _emit_issue(self, issue: PipelineHealthIssue, now: datetime) -> None:
        event = ErrorEvent(
            timestamp=now,
            symbol=issue.symbol,
            error_type=issue.error_type,
            error_message=issue.message,
            component="pipeline_health",
        )
        event.metadata.update(issue.details)
        published = await self._bus.publish(event)
        if published:
            self._last_sent_at[issue.key] = now
        else:
            logger.warning("Failed to publish pipeline health event: %s", issue.key)
