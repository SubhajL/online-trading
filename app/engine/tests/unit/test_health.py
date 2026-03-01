"""
Unit tests for health monitoring system.
Following T-3: Pure logic unit tests without external dependencies.
Following T-4: Avoiding heavy mocking.
"""

import json
import pytest
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional

from app.engine.core.health import (
    check_database_health,
    check_redis_health,
    check_memory_pools_health,
    check_event_bus_health,
    aggregate_health_status,
    create_health_endpoint,
    HealthStatus,
    ComponentHealth,
    HealthCheck,
)

from app.engine.resilience.thread_safe_circuit_breaker import CircuitBreakerConfig as CBConfig


async def _open_router_breaker(client):
    # helper: trip GET:/orders once (threshold 1) to OPEN
    mapping = {("GET", "/orders"): [(500, "e")]}
    from app.engine.tests.unit.test_client_circuit_breakers import _RouterSession

    client._initialized = True
    client._session = _RouterSession(mapping)
    await client._make_request("GET", "/orders")


async def _open_binance_breaker(client):
    mapping = {("GET", "/api/v3/depth"): [(500, {"msg": "e"})]}
    from app.engine.tests.unit.test_client_circuit_breakers import _BinanceSession

    client._session = _BinanceSession(mapping)
    try:
        await client.get_order_book("BTCUSDT", 5)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_health_includes_router_breaker_metrics() -> None:
    from app.engine.adapters.router_client.http_client import RouterHTTPClient
    from app.engine.core.health import check_router_client_health

    cfg = {"GET:/orders": CBConfig(failure_threshold=1, success_threshold=1, timeout_seconds=1)}
    client = RouterHTTPClient(base_url="http://example", per_endpoint_breakers_config=cfg)
    await _open_router_breaker(client)

    comp = await check_router_client_health(client)
    assert isinstance(comp, ComponentHealth)
    assert comp.name == "router"
    assert "breakers" in comp.details
    breakers = comp.details["breakers"]
    assert any(k.startswith("GET:/orders") for k in breakers.keys())
    assert breakers["GET:/orders"]["state"] in ("OPEN", "HALF_OPEN", "CLOSED")


@pytest.mark.asyncio
async def test_health_includes_binance_breaker_metrics() -> None:
    from app.engine.ingest.binance_rest import BinanceRestClient
    from app.engine.core.health import check_binance_client_health

    cfg = {"GET:/api/v3/depth": CBConfig(failure_threshold=1, success_threshold=1, timeout_seconds=1)}
    client = BinanceRestClient(api_key="k", api_secret="s", testnet=True, per_endpoint_breakers_config=cfg)
    await _open_binance_breaker(client)

    comp = await check_binance_client_health(client)
    assert isinstance(comp, ComponentHealth)
    assert comp.name == "binance"
    assert "breakers" in comp.details
    breakers = comp.details["breakers"]
    assert "GET:/api/v3/depth" in breakers
    assert breakers["GET:/api/v3/depth"]["failure_count"] >= 1


class TestDatabaseHealth:
    """Tests for database health checks."""

    def test_database_health_when_healthy(self) -> None:
        """Returns OK with low latency metrics."""
        # Simulate healthy database stats
        db_stats = {
            "active_connections": 5,
            "max_connections": 20,
            "avg_query_time_ms": 2.5,
            "queries_per_second": 100,
            "connection_errors": 0,
        }

        health = check_database_health(db_stats)

        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms < 10
        assert "connections" in health.details
        assert health.details["utilization"] == 0.25  # 5/20

    def test_database_health_when_pool_exhausted(self) -> None:
        """Detects degraded state on pool saturation."""
        # Simulate exhausted connection pool
        db_stats = {
            "active_connections": 19,
            "max_connections": 20,
            "avg_query_time_ms": 15.0,
            "queries_per_second": 50,
            "connection_errors": 5,
        }

        health = check_database_health(db_stats)

        assert health.status == HealthStatus.DEGRADED
        assert health.message == "Connection pool near capacity"
        assert health.details["utilization"] == 0.95

    def test_database_health_when_unhealthy(self) -> None:
        """Reports unhealthy when connections fail."""
        # Simulate connection failures
        db_stats = {
            "active_connections": 0,
            "max_connections": 20,
            "avg_query_time_ms": 0,
            "queries_per_second": 0,
            "connection_errors": 100,
        }

        health = check_database_health(db_stats)

        assert health.status == HealthStatus.UNHEALTHY
        assert "error" in health.message.lower()
        assert health.details["connection_errors"] == 100


class TestRedisHealth:
    """Tests for Redis health checks."""

    def test_redis_health_with_high_memory(self) -> None:
        """Warns when Redis memory exceeds threshold."""
        # Simulate high memory usage
        redis_stats = {
            "connected": True,
            "memory_used_mb": 900,
            "memory_max_mb": 1000,
            "hit_rate": 0.95,
            "evicted_keys": 1000,
            "ping_latency_ms": 1.0,
        }

        health = check_redis_health(redis_stats)

        assert health.status == HealthStatus.DEGRADED
        assert "memory" in health.message.lower()
        assert health.details["memory_usage_percent"] == 90

    def test_redis_health_when_healthy(self) -> None:
        """Returns healthy with good metrics."""
        redis_stats = {
            "connected": True,
            "memory_used_mb": 200,
            "memory_max_mb": 1000,
            "hit_rate": 0.98,
            "evicted_keys": 0,
            "ping_latency_ms": 0.5,
        }

        health = check_redis_health(redis_stats)

        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms < 2
        assert health.details["hit_rate"] == 0.98

    def test_redis_health_when_disconnected(self) -> None:
        """Reports unhealthy when disconnected."""
        redis_stats = {
            "connected": False,
            "memory_used_mb": 0,
            "memory_max_mb": 0,
            "hit_rate": 0,
            "evicted_keys": 0,
            "ping_latency_ms": 0,
        }

        health = check_redis_health(redis_stats)

        assert health.status == HealthStatus.UNHEALTHY
        assert "disconnected" in health.message.lower()


class TestMemoryPoolsHealth:
    """Tests for memory pool health checks."""

    def test_memory_pools_detect_leaks(self) -> None:
        """Identifies arrays held beyond max duration."""
        # Simulate potential memory leaks
        pool_stats = {
            "pools": [
                {
                    "name": "price_arrays",
                    "capacity": 100,
                    "used": 50,
                    "free": 50,
                    "allocations": 1000,
                    "avg_hold_time_seconds": 300,  # 5 minutes
                    "longest_held_seconds": 3600,  # 1 hour - potential leak
                    "memory_mb": 100,
                }
            ],
            "total_memory_mb": 100,
            "leak_threshold_seconds": 600,
        }

        health = check_memory_pools_health(pool_stats)

        assert health.status == HealthStatus.DEGRADED
        assert "leak" in health.message.lower()
        assert health.details["potential_leaks"] == 1

    def test_memory_pools_healthy(self) -> None:
        """Reports healthy with normal usage."""
        pool_stats = {
            "pools": [
                {
                    "name": "price_arrays",
                    "capacity": 100,
                    "used": 30,
                    "free": 70,
                    "allocations": 1000,
                    "avg_hold_time_seconds": 5,
                    "longest_held_seconds": 30,
                    "memory_mb": 100,
                }
            ],
            "total_memory_mb": 100,
            "leak_threshold_seconds": 600,
        }

        health = check_memory_pools_health(pool_stats)

        assert health.status == HealthStatus.HEALTHY
        assert health.details["utilization"] == 0.3

    def test_memory_pools_exhausted(self) -> None:
        """Detects pool exhaustion."""
        pool_stats = {
            "pools": [
                {
                    "name": "price_arrays",
                    "capacity": 100,
                    "used": 95,
                    "free": 5,
                    "allocations": 5000,  # Many new allocations
                    "avg_hold_time_seconds": 10,
                    "longest_held_seconds": 60,
                    "memory_mb": 100,
                }
            ],
            "total_memory_mb": 100,
            "leak_threshold_seconds": 600,
        }

        health = check_memory_pools_health(pool_stats)

        assert health.status == HealthStatus.DEGRADED
        assert (
            "exhausted" in health.message.lower()
            or "capacity" in health.message.lower()
        )


class TestEventBusHealth:
    """Tests for event bus health checks."""

    def test_event_bus_health_circuit_open(self) -> None:
        """Reports unhealthy when circuits are open."""
        # Simulate open circuit breakers
        bus_stats = {
            "queue_depth": 100,
            "queue_capacity": 10000,
            "processing_rate": 50,
            "error_rate": 0.15,  # 15% errors
            "circuit_breakers": {
                "order_processor": "OPEN",
                "position_tracker": "CLOSED",
                "risk_manager": "HALF_OPEN",
            },
            "subscriptions": 10,
            "active_processors": 8,
        }

        health = check_event_bus_health(bus_stats)

        assert health.status == HealthStatus.UNHEALTHY
        assert "circuit" in health.message.lower()
        assert health.details["open_circuits"] == 1

    def test_event_bus_health_queue_backing_up(self) -> None:
        """Detects when queue is backing up."""
        bus_stats = {
            "queue_depth": 8000,
            "queue_capacity": 10000,
            "processing_rate": 10,  # Very slow
            "error_rate": 0.01,
            "circuit_breakers": {
                "order_processor": "CLOSED",
                "position_tracker": "CLOSED",
            },
            "subscriptions": 10,
            "active_processors": 10,
        }

        health = check_event_bus_health(bus_stats)

        assert health.status == HealthStatus.DEGRADED
        assert "queue" in health.message.lower()
        assert health.details["queue_utilization"] == 0.8

    def test_event_bus_healthy(self) -> None:
        """Reports healthy with normal operation."""
        bus_stats = {
            "queue_depth": 100,
            "queue_capacity": 10000,
            "processing_rate": 1000,
            "error_rate": 0.001,  # 0.1% errors
            "circuit_breakers": {
                "order_processor": "CLOSED",
                "position_tracker": "CLOSED",
                "risk_manager": "CLOSED",
            },
            "subscriptions": 10,
            "active_processors": 10,
        }

        health = check_event_bus_health(bus_stats)

        assert health.status == HealthStatus.HEALTHY
        assert health.details["queue_utilization"] == 0.01


class TestAggregateHealth:
    """Tests for health aggregation."""

    def test_aggregate_combines_statuses(self) -> None:
        """Worst status wins, preserves component details."""
        components = [
            ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                latency_ms=2.0,
                message="Database operational",
                details={"connections": 5},
            ),
            ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                latency_ms=5.0,
                message="High memory usage",
                details={"memory_percent": 85},
            ),
            ComponentHealth(
                name="event_bus",
                status=HealthStatus.UNHEALTHY,
                latency_ms=0,
                message="Circuit breaker open",
                details={"open_circuits": 2},
            ),
        ]

        overall = aggregate_health_status(components)

        assert overall.status == HealthStatus.UNHEALTHY  # Worst status
        assert len(overall.components) == 3
        assert overall.components["event_bus"].status == HealthStatus.UNHEALTHY
        assert "redis" in overall.message  # Mentions degraded component
        assert "event_bus" in overall.message  # Mentions unhealthy component

    def test_aggregate_all_healthy(self) -> None:
        """Reports healthy when all components healthy."""
        components = [
            ComponentHealth(
                name="database",
                status=HealthStatus.HEALTHY,
                latency_ms=2.0,
                message="Database operational",
                details={},
            ),
            ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                latency_ms=1.0,
                message="Redis operational",
                details={},
            ),
        ]

        overall = aggregate_health_status(components)

        assert overall.status == HealthStatus.HEALTHY
        assert "healthy" in overall.message.lower()
        assert overall.latency_ms == max(2.0, 1.0)

    def test_aggregate_empty_components(self) -> None:
        """Handles empty component list."""
        overall = aggregate_health_status([])

        assert overall.status == HealthStatus.UNHEALTHY
        assert "no components" in overall.message.lower()


class TestHealthEndpoint:
    """Tests for health HTTP endpoint."""

    def test_health_endpoint_format(self) -> None:
        """Returns proper JSON with HTTP status codes."""
        # Create mock health check
        health_check = HealthCheck(
            status=HealthStatus.HEALTHY,
            message="All systems operational",
            latency_ms=5.0,
            components={
                "database": ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    latency_ms=2.0,
                    message="OK",
                    details={"connections": 10},
                )
            },
        )

        endpoint = create_health_endpoint(lambda: health_check)
        response = endpoint()  # type: ignore[call-arg]

        assert response["status_code"] == 200
        assert "application/json" in response["content_type"]

        body = json.loads(response["body"])
        assert body["status"] == "healthy"
        assert "components" in body
        assert "database" in body["components"]

    def test_health_endpoint_degraded(self) -> None:
        """Returns 200 with degraded status."""
        health_check = HealthCheck(
            status=HealthStatus.DEGRADED,
            message="Some components degraded",
            latency_ms=10.0,
            components={},
        )

        endpoint = create_health_endpoint(lambda: health_check)
        response = endpoint()  # type: ignore[call-arg]

        assert response["status_code"] == 200  # Still 200 for degraded
        body = json.loads(response["body"])
        assert body["status"] == "degraded"

    def test_health_endpoint_unhealthy(self) -> None:
        """Returns 503 when unhealthy."""
        health_check = HealthCheck(
            status=HealthStatus.UNHEALTHY,
            message="Critical components failed",
            latency_ms=0,
            components={},
        )

        endpoint = create_health_endpoint(lambda: health_check)
        response = endpoint()  # type: ignore[call-arg]

        assert response["status_code"] == 503  # Service unavailable
        body = json.loads(response["body"])
        assert body["status"] == "unhealthy"

    def test_health_endpoint_kubernetes_compatible(self) -> None:
        """Compatible with Kubernetes probes."""
        health_check = HealthCheck(
            status=HealthStatus.HEALTHY, message="Ready", latency_ms=1.0, components={}
        )

        endpoint = create_health_endpoint(lambda: health_check)

        # Test liveness probe
        liveness_response = endpoint(probe_type="liveness")  # type: ignore[call-arg]
        assert liveness_response["status_code"] == 200

        # Test readiness probe
        readiness_response = endpoint(probe_type="readiness")  # type: ignore[call-arg]
        assert readiness_response["status_code"] == 200

        # Unhealthy should fail readiness but not liveness
        health_check.status = HealthStatus.DEGRADED
        readiness_response = endpoint(probe_type="readiness")  # type: ignore[call-arg]
        assert readiness_response["status_code"] == 503  # Not ready
