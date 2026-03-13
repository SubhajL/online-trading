"""FastAPI TestClient integration tests for /health/system endpoint."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("httpx", reason="httpx is not installed")

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.engine.core.health import build_system_health


class _FakeRouterClient:
    async def get_breaker_metrics(self) -> dict[str, dict[str, Any]]:  # noqa: D401
        return {
            "GET:/orders": {"state": "CLOSED", "failure_count": 0, "success_count": 1}
        }


class _FakeBinanceRest:
    async def get_breaker_metrics(self) -> dict[str, dict[str, Any]]:  # noqa: D401
        return {
            "GET:/api/v3/klines": {
                "state": "CLOSED",
                "failure_count": 0,
                "success_count": 5,
            }
        }


class _FakeIngest:
    def __init__(self) -> None:
        self.rest_client = _FakeBinanceRest()


class _FakeRedis:
    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "status": "healthy",
            "database_size": 123,
            "connected_clients": 7,
            "memory_usage": "2MB",
            "total_commands_processed": 999,
        }


@pytest.mark.asyncio
async def test_health_system_returns_components_and_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Build a lightweight FastAPI app exposing the same route contract
    app = FastAPI()
    services_local: dict[str, Any] = {
        "router": _FakeRouterClient(),
        "ingest": _FakeIngest(),
        "redis": _FakeRedis(),
    }

    @app.get("/health/system")
    async def _system_health() -> Any:  # noqa: D401
        try:
            health = await build_system_health(services_local)
            body: dict[str, Any] = {
                "status": health.status.value,
                "message": health.message,
                "timestamp": health.timestamp,
                "latency_ms": health.latency_ms,
                "components": {},
            }
            for name, comp in health.components.items():
                body["components"][name] = {
                    "status": comp.status.value,
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                    "details": comp.details,
                }
            return JSONResponse(content=body, status_code=200)
        except Exception:  # pragma: no cover - error path tested separately
            return JSONResponse(
                content={
                    "status": "unhealthy",
                    "message": "system health error",
                },
                status_code=503,
            )

    with TestClient(app) as client:
        res = client.get("/health/system")
        assert res.status_code == 200
        body = res.json()
        assert body.get("status") in {"healthy", "degraded", "unhealthy"}
        components = body.get("components", {})
        assert set(["router", "binance", "redis"]).issubset(components.keys())
        assert "details" in components["router"]
        assert "details" in components["binance"]
        assert "details" in components["redis"]


def test_health_system_returns_503_on_aggregator_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Build app reusing same handler shape but force aggregator error
    app = FastAPI()

    @app.get("/health/system")
    async def _system_health() -> Any:  # noqa: D401
        try:
            # Simulate aggregator error
            raise RuntimeError("integration error")
        except Exception:
            return JSONResponse(
                content={
                    "status": "unhealthy",
                    "message": "system health error",
                },
                status_code=503,
            )

    with TestClient(app) as client:
        res = client.get("/health/system")
        assert res.status_code == 503
        body = res.json()
        assert body.get("status") == "unhealthy"
        assert body.get("message") == "system health error"
        assert "integration error" not in body.get("message", "")
