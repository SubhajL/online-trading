from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.engine.models import ErrorEvent
from app.engine.monitoring.pipeline_health_service import (
    PipelineHealthService,
    PipelineHealthThresholds,
    evaluate_pipeline_health,
)


def _ingest_health(
    *,
    ws_connected: bool = True,
    ws_stale: bool = False,
    ws_last_message_ago_seconds: float | None = 10.0,
    ws_last_kline_ago_seconds: float | None = None,
    ws_last_closed_kline_ago_seconds: float | None = None,
    consecutive_failures: int = 0,
    latest_candle_ago_seconds: dict[str, dict[str, float]] | None = None,
) -> dict[str, object]:
    return {
        "websocket": {
            "connected": ws_connected,
            "stale": ws_stale,
            "last_message_ago_seconds": ws_last_message_ago_seconds,
            "last_kline_ago_seconds": ws_last_kline_ago_seconds,
            "last_closed_kline_ago_seconds": ws_last_closed_kline_ago_seconds,
            "consecutive_failures": consecutive_failures,
        },
        "latest_candle_ago_seconds": latest_candle_ago_seconds or {},
    }


class TestEvaluatePipelineHealth:
    def test_reports_issue_when_ws_is_disconnected(self) -> None:
        """ws_connected=False yields websocket_disconnected issue."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(ws_connected=False)

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "websocket_disconnected" for i in issues)
        assert any(i.error_type == "websocket_disconnected" for i in issues)

    def test_ws_disconnected_supersedes_stale(self) -> None:
        """When disconnected, should NOT also emit websocket_stale."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(
            ws_connected=False,
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "websocket_disconnected" for i in issues)
        assert not any(i.key == "websocket_stale" for i in issues)

    def test_no_ws_issue_when_connected_and_fresh(self) -> None:
        """ws_connected=True and fresh yields no WS issue."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(ws_connected=True, ws_stale=False, ws_last_message_ago_seconds=10.0)

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert not any(
            i.error_type in ("websocket_stale", "websocket_disconnected") for i in issues
        )

    def test_reports_issue_when_ws_is_stale(self) -> None:
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(ws_stale=True, ws_last_message_ago_seconds=200.0)

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "websocket_stale" for i in issues)

    def test_reports_issue_when_latest_candle_exceeds_timeframe_budget(self) -> None:
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds(candle_lag_multiplier=2.0, candle_lag_grace_seconds=0)
        health = _ingest_health(
            latest_candle_ago_seconds={
                "BTCUSDT": {"5m": 1000.0},
            },
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "candle_stale:BTCUSDT:5m" for i in issues)


class TestKlineStreamStaleDetection:
    """Tests for detecting kline-specific staleness (tickers alive, klines dead).

    Uses last_kline_ago_seconds (any kline, open or closed) because:
    - Open klines arrive frequently (every few seconds during active trading)
    - Closed klines only arrive at timeframe intervals (e.g., every 5m)
    - Using stale_ws_seconds (120s default) for any-kline is appropriate
    """

    def test_reports_kline_stream_stale_when_klines_not_arriving(self) -> None:
        """WS connected and messages flowing, but klines (open or closed) are stale."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds(stale_ws_seconds=120)
        # Tickers are flowing (last_message_ago_seconds=5)
        # But ANY klines haven't arrived in 150 seconds (> 120s threshold)
        health = _ingest_health(
            ws_connected=True,
            ws_stale=False,
            ws_last_message_ago_seconds=5.0,
            ws_last_kline_ago_seconds=150.0,
            ws_last_closed_kline_ago_seconds=300.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "kline_stream_stale" for i in issues)
        kline_issue = next(i for i in issues if i.key == "kline_stream_stale")
        assert kline_issue.error_type == "kline_stream_stale"
        assert "klines not arriving" in kline_issue.message.lower()
        assert kline_issue.details["last_kline_ago_seconds"] == 150.0
        assert kline_issue.details["last_message_ago_seconds"] == 5.0

    def test_no_kline_stream_stale_when_klines_fresh(self) -> None:
        """No kline_stream_stale issue when any klines (open or closed) are recent."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds(stale_ws_seconds=120)
        # Klines are fresh (30s old < 120s threshold)
        health = _ingest_health(
            ws_connected=True,
            ws_stale=False,
            ws_last_message_ago_seconds=5.0,
            ws_last_kline_ago_seconds=30.0,
            ws_last_closed_kline_ago_seconds=300.0,  # Closed klines can be old
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert not any(i.key == "kline_stream_stale" for i in issues)

    def test_no_kline_stream_stale_when_ws_disconnected(self) -> None:
        """Don't emit kline_stream_stale when WS is disconnected (websocket_disconnected takes precedence)."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(
            ws_connected=False,
            ws_last_kline_ago_seconds=150.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        # websocket_disconnected should be reported, NOT kline_stream_stale
        assert any(i.key == "websocket_disconnected" for i in issues)
        assert not any(i.key == "kline_stream_stale" for i in issues)

    def test_no_kline_stream_stale_when_ws_stale(self) -> None:
        """Don't emit kline_stream_stale when WS is already stale (websocket_stale takes precedence)."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds(stale_ws_seconds=120)
        health = _ingest_health(
            ws_connected=True,
            ws_stale=True,
            ws_last_message_ago_seconds=200.0,
            ws_last_kline_ago_seconds=150.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        # websocket_stale should be reported, NOT kline_stream_stale
        assert any(i.key == "websocket_stale" for i in issues)
        assert not any(i.key == "kline_stream_stale" for i in issues)

    def test_reports_kline_stream_stale_when_last_kline_ago_is_none(self) -> None:
        """WS connected and messages flowing, but no klines have been received."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds()
        health = _ingest_health(
            ws_connected=True,
            ws_stale=False,
            ws_last_message_ago_seconds=5.0,
            ws_last_kline_ago_seconds=None,  # No klines received yet
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "kline_stream_stale" for i in issues)

    def test_kline_stream_stale_uses_stale_ws_seconds_threshold(self) -> None:
        """kline_stream_stale uses stale_ws_seconds as threshold."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # Custom threshold of 60 seconds
        thresholds = PipelineHealthThresholds(stale_ws_seconds=60)
        # Any klines are 61 seconds old (> 60s threshold)
        health = _ingest_health(
            ws_connected=True,
            ws_stale=False,
            ws_last_message_ago_seconds=5.0,
            ws_last_kline_ago_seconds=61.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert any(i.key == "kline_stream_stale" for i in issues)

    def test_kline_stream_stale_at_boundary_is_not_stale(self) -> None:
        """Exactly at threshold is not stale (uses > not >=)."""
        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        thresholds = PipelineHealthThresholds(stale_ws_seconds=120)
        # Klines are exactly 120 seconds old (= threshold)
        health = _ingest_health(
            ws_connected=True,
            ws_stale=False,
            ws_last_message_ago_seconds=5.0,
            ws_last_kline_ago_seconds=120.0,
        )

        issues = evaluate_pipeline_health(ingest_health=health, now=now, thresholds=thresholds)

        assert not any(i.key == "kline_stream_stale" for i in issues)


class TestPipelineHealthService:
    @pytest.mark.asyncio
    async def test_service_emits_error_event_on_ws_stale(self) -> None:
        bus = AsyncMock()
        ingest = AsyncMock()
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )

        now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(min_alert_interval_seconds=0),
            now_fn=lambda: now,
        )

        await service._check_once()

        assert bus.publish.await_count == 1
        published_event = bus.publish.await_args[0][0]
        assert isinstance(published_event, ErrorEvent)
        assert published_event.component == "pipeline_health"

    @pytest.mark.asyncio
    async def test_ingest_health_check_error_does_not_raise_or_publish(self) -> None:
        bus = AsyncMock()
        ingest = AsyncMock()
        ingest.health_check.side_effect = RuntimeError("boom")

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(min_alert_interval_seconds=0),
        )

        await service._check_once()

        bus.publish.assert_not_called()


class TestPipelineHealthServiceStartupGrace:
    """Tests for startup grace period to avoid alerts during backfill."""

    @pytest.mark.asyncio
    async def test_skips_health_check_during_startup_grace_period(self) -> None:
        """Health checks should be skipped during startup grace period to allow backfill."""
        bus = AsyncMock()
        ingest = AsyncMock()
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )

        start_time = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # 30 seconds after start - still within 120s grace period
        check_time = datetime(2026, 1, 5, 12, 0, 30, tzinfo=UTC)

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(
                min_alert_interval_seconds=0,
                startup_grace_seconds=120,
            ),
            now_fn=lambda: check_time,
        )

        # Manually set _started_at without calling start() to avoid background task
        service._started_at = start_time

        # Check should be skipped during grace period
        await service._check_once()

        # Both health check AND publish should be skipped
        ingest.health_check.assert_not_called()
        bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_health_check_after_startup_grace_period(self) -> None:
        """Health checks should run after startup grace period expires."""
        bus = AsyncMock()
        ingest = AsyncMock()
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )

        start_time = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # 180 seconds after start - past 120s grace period
        check_time = datetime(2026, 1, 5, 12, 3, tzinfo=UTC)

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(
                min_alert_interval_seconds=0,
                startup_grace_seconds=120,
            ),
            now_fn=lambda: check_time,
        )

        # Manually set _started_at without calling start() to avoid background task
        service._started_at = start_time

        # Check should run and emit alert after grace period
        await service._check_once()

        ingest.health_check.assert_awaited_once()
        assert bus.publish.await_count == 1

    @pytest.mark.asyncio
    async def test_grace_period_boundary_at_exact_threshold(self) -> None:
        """At exactly startup_grace_seconds, health check should run (< not <=)."""
        bus = AsyncMock()
        ingest = AsyncMock()
        ingest.health_check.return_value = _ingest_health(ws_stale=False)

        start_time = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
        # Exactly 120 seconds after start - at boundary
        check_time = datetime(2026, 1, 5, 12, 2, tzinfo=UTC)

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(startup_grace_seconds=120),
            now_fn=lambda: check_time,
        )

        service._started_at = start_time

        await service._check_once()

        # At exactly 120s, grace period has expired (< 120 is False for 120)
        ingest.health_check.assert_awaited_once()


class TestPipelineHealthServiceCooldown:
    """Tests for cooldown behavior, especially flapping issues."""

    @pytest.mark.asyncio
    async def test_cooldown_not_reset_on_flap(self) -> None:
        """Issue appears, disappears, reappears within 300s — only emits once."""
        bus = AsyncMock()
        bus.publish.return_value = True
        ingest = AsyncMock()

        current_time = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(min_alert_interval_seconds=300),
            now_fn=lambda: current_time,
        )
        service._started_at = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)

        # Check 1: Issue present → should emit
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )
        await service._check_once()
        assert bus.publish.await_count == 1

        # Check 2: Issue gone (30s later)
        current_time = datetime(2026, 1, 5, 12, 0, 30, tzinfo=UTC)
        service._now_fn = lambda: current_time
        ingest.health_check.return_value = _ingest_health(
            ws_stale=False,
            ws_last_message_ago_seconds=1.0,
            ws_last_kline_ago_seconds=1.0,
        )
        await service._check_once()
        # No new emit (no issues)
        assert bus.publish.await_count == 1

        # Check 3: Issue re-appears (60s after first, within 300s cooldown)
        current_time = datetime(2026, 1, 5, 12, 1, tzinfo=UTC)
        service._now_fn = lambda: current_time
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )
        await service._check_once()
        # Should NOT emit again — within cooldown window
        assert bus.publish.await_count == 1

    @pytest.mark.asyncio
    async def test_cooldown_allows_reemit_after_interval(self) -> None:
        """Issue reappears after 300s cooldown — should emit again."""
        bus = AsyncMock()
        bus.publish.return_value = True
        ingest = AsyncMock()

        current_time = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

        service = PipelineHealthService(
            bus=bus,
            ingest_service=ingest,
            thresholds=PipelineHealthThresholds(min_alert_interval_seconds=300),
            now_fn=lambda: current_time,
        )
        service._started_at = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)

        # Check 1: Issue present → emit
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )
        await service._check_once()
        assert bus.publish.await_count == 1

        # Check 2: Issue gone
        current_time = datetime(2026, 1, 5, 12, 1, tzinfo=UTC)
        service._now_fn = lambda: current_time
        ingest.health_check.return_value = _ingest_health(
            ws_stale=False,
            ws_last_message_ago_seconds=1.0,
            ws_last_kline_ago_seconds=1.0,
        )
        await service._check_once()

        # Check 3: Issue re-appears after 301s — past cooldown
        current_time = datetime(2026, 1, 5, 12, 5, 1, tzinfo=UTC)
        service._now_fn = lambda: current_time
        ingest.health_check.return_value = _ingest_health(
            ws_stale=True,
            ws_last_message_ago_seconds=500.0,
        )
        await service._check_once()
        # Should emit again — past cooldown window
        assert bus.publish.await_count == 2
