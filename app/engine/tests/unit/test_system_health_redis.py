"""System health aggregator tests including Redis component."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.engine.core.health import HealthStatus, build_system_health


class _FakeRedisAdapter:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        if not self.ok:
            raise RuntimeError("boom")
        return {
            "status": "healthy",
            "database_size": 42,
            "connected_clients": 10,
            "memory_usage": "1MB",
            "total_commands_processed": 100,
        }


@pytest.mark.asyncio
async def test_system_health_includes_redis_metrics() -> None:
    services: dict[str, Any] = {"redis": _FakeRedisAdapter()}
    health = await build_system_health(services)
    assert "redis" in health.components
    comp = health.components["redis"]
    assert comp.status == HealthStatus.HEALTHY
    assert comp.details.get("database_size") == 42
    assert comp.details.get("connected_clients") == 10


@pytest.mark.asyncio
async def test_system_health_handles_redis_error() -> None:
    services: dict[str, Any] = {"redis": _FakeRedisAdapter(ok=False)}
    health = await build_system_health(services)
    assert "redis" in health.components
    comp = health.components["redis"]
    assert comp.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY)
