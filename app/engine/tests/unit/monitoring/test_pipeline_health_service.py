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
