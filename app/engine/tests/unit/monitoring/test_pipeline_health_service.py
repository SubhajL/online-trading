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
    consecutive_failures: int = 0,
    latest_candle_ago_seconds: dict[str, dict[str, float]] | None = None,
) -> dict[str, object]:
    return {
        "websocket": {
            "connected": ws_connected,
            "stale": ws_stale,
            "last_message_ago_seconds": ws_last_message_ago_seconds,
            "consecutive_failures": consecutive_failures,
        },
        "latest_candle_ago_seconds": latest_candle_ago_seconds or {},
    }


class TestEvaluatePipelineHealth:
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
