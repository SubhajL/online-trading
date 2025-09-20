"""
Health monitoring system for production readiness.
Following C-4: Prefer simple, composable, testable functions.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: HealthStatus
    latency_ms: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Overall system health check result."""

    status: HealthStatus
    message: str
    latency_ms: float
    components: Dict[str, ComponentHealth] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


def check_database_health(db_stats: Dict[str, Any]) -> ComponentHealth:
    """
    Verify database connection pool is healthy.
    Checks query latency, connection count, transaction throughput.
    """
    start = time.time()

    active = db_stats.get("active_connections", 0)
    max_conn = db_stats.get("max_connections", 1)
    avg_query = db_stats.get("avg_query_time_ms", 0)
    qps = db_stats.get("queries_per_second", 0)
    errors = db_stats.get("connection_errors", 0)

    utilization = active / max_conn if max_conn > 0 else 0

    details = {
        "connections": f"{active}/{max_conn}",
        "utilization": utilization,
        "avg_query_ms": avg_query,
        "qps": qps,
        "connection_errors": errors,
    }

    # Determine health status
    if errors > 50 or active == 0:
        status = HealthStatus.UNHEALTHY
        message = f"Database connection errors: {errors}"
    elif utilization > 0.9:
        status = HealthStatus.DEGRADED
        message = "Connection pool near capacity"
    elif avg_query > 100:
        status = HealthStatus.DEGRADED
        message = f"High query latency: {avg_query}ms"
    else:
        status = HealthStatus.HEALTHY
        message = "Database operational"

    latency = (time.time() - start) * 1000

    return ComponentHealth(
        name="database",
        status=status,
        latency_ms=latency,
        message=message,
        details=details,
    )


def check_redis_health(redis_stats: Dict[str, Any]) -> ComponentHealth:
    """
    Test Redis connectivity and performance.
    Checks memory usage, hit rate, eviction rate.
    """
    start = time.time()

    connected = redis_stats.get("connected", False)
    memory_used = redis_stats.get("memory_used_mb", 0)
    memory_max = redis_stats.get("memory_max_mb", 1)
    hit_rate = redis_stats.get("hit_rate", 0)
    evicted = redis_stats.get("evicted_keys", 0)
    ping_latency = redis_stats.get("ping_latency_ms", 0)

    memory_percent = (memory_used / memory_max * 100) if memory_max > 0 else 0

    details = {
        "connected": connected,
        "memory_usage_percent": memory_percent,
        "hit_rate": hit_rate,
        "evicted_keys": evicted,
        "ping_ms": ping_latency,
    }

    # Determine health status
    if not connected:
        status = HealthStatus.UNHEALTHY
        message = "Redis disconnected"
    elif memory_percent > 85:
        status = HealthStatus.DEGRADED
        message = f"High memory usage: {memory_percent:.1f}%"
    elif evicted > 1000:
        status = HealthStatus.DEGRADED
        message = f"High eviction rate: {evicted} keys"
    elif hit_rate < 0.8:
        status = HealthStatus.DEGRADED
        message = f"Low cache hit rate: {hit_rate:.2f}"
    else:
        status = HealthStatus.HEALTHY
        message = "Redis operational"

    latency = (time.time() - start) * 1000

    return ComponentHealth(
        name="redis",
        status=status,
        latency_ms=latency,
        message=message,
        details=details,
    )


def check_memory_pools_health(pool_stats: Dict[str, Any]) -> ComponentHealth:
    """
    Monitor memory pool utilization and detect leaks.
    Checks for long-held arrays and allocation performance.
    """
    start = time.time()

    pools = pool_stats.get("pools", [])
    total_memory = pool_stats.get("total_memory_mb", 0)
    leak_threshold = pool_stats.get("leak_threshold_seconds", 600)

    total_used = 0
    total_capacity = 0
    potential_leaks = 0
    max_hold_time = 0

    for pool in pools:
        used = pool.get("used", 0)
        capacity = pool.get("capacity", 1)
        longest_held = pool.get("longest_held_seconds", 0)

        total_used += used
        total_capacity += capacity

        if longest_held > leak_threshold:
            potential_leaks += 1

        max_hold_time = max(max_hold_time, longest_held)

    utilization = total_used / total_capacity if total_capacity > 0 else 0

    details = {
        "utilization": utilization,
        "total_memory_mb": total_memory,
        "potential_leaks": potential_leaks,
        "max_hold_seconds": max_hold_time,
        "pools_count": len(pools),
    }

    # Determine health status
    if potential_leaks > 0:
        status = HealthStatus.DEGRADED
        message = f"Potential memory leak detected: {potential_leaks} pools"
    elif utilization > 0.9:
        status = HealthStatus.DEGRADED
        message = f"Memory pools near capacity exhaustion: {utilization:.1%}"
    else:
        status = HealthStatus.HEALTHY
        message = "Memory pools operational"

    latency = (time.time() - start) * 1000

    return ComponentHealth(
        name="memory_pools",
        status=status,
        latency_ms=latency,
        message=message,
        details=details,
    )


def check_event_bus_health(bus_stats: Dict[str, Any]) -> ComponentHealth:
    """
    Verify event bus queues and processing.
    Checks queue depth, circuit breakers, subscription health.
    """
    start = time.time()

    queue_depth = bus_stats.get("queue_depth", 0)
    queue_capacity = bus_stats.get("queue_capacity", 1)
    processing_rate = bus_stats.get("processing_rate", 0)
    error_rate = bus_stats.get("error_rate", 0)
    circuit_breakers = bus_stats.get("circuit_breakers", {})
    subscriptions = bus_stats.get("subscriptions", 0)
    active_processors = bus_stats.get("active_processors", 0)

    queue_utilization = queue_depth / queue_capacity if queue_capacity > 0 else 0

    # Count circuit breaker states
    open_circuits = sum(1 for state in circuit_breakers.values() if state == "OPEN")
    half_open = sum(1 for state in circuit_breakers.values() if state == "HALF_OPEN")

    details = {
        "queue_utilization": queue_utilization,
        "queue_depth": queue_depth,
        "processing_rate": processing_rate,
        "error_rate": error_rate,
        "open_circuits": open_circuits,
        "half_open_circuits": half_open,
        "active_processors": active_processors,
    }

    # Determine health status
    if open_circuits > 0:
        status = HealthStatus.UNHEALTHY
        message = f"Circuit breakers open: {open_circuits}"
    elif queue_utilization > 0.75:
        status = HealthStatus.DEGRADED
        message = f"Event queue backing up: {queue_utilization:.1%}"
    elif error_rate > 0.05:
        status = HealthStatus.DEGRADED
        message = f"High error rate: {error_rate:.1%}"
    elif processing_rate < 100 and queue_depth > 1000:
        status = HealthStatus.DEGRADED
        message = "Slow event processing"
    else:
        status = HealthStatus.HEALTHY
        message = "Event bus operational"

    latency = (time.time() - start) * 1000

    return ComponentHealth(
        name="event_bus",
        status=status,
        latency_ms=latency,
        message=message,
        details=details,
    )


def aggregate_health_status(components: List[ComponentHealth]) -> HealthCheck:
    """
    Combine all health checks into overall status.
    Worst status wins, preserves detailed breakdown.
    """
    if not components:
        return HealthCheck(
            status=HealthStatus.UNHEALTHY,
            message="No components reporting",
            latency_ms=0,
            components={},
        )

    # Build components dict
    components_dict = {comp.name: comp for comp in components}

    # Determine overall status (worst wins)
    unhealthy = [c for c in components if c.status == HealthStatus.UNHEALTHY]
    degraded = [c for c in components if c.status == HealthStatus.DEGRADED]

    if unhealthy:
        overall_status = HealthStatus.UNHEALTHY
        problem_components = unhealthy + degraded
        message = (
            f"Components unhealthy: {', '.join(c.name for c in problem_components)}"
        )
    elif degraded:
        overall_status = HealthStatus.DEGRADED
        message = f"Components degraded: {', '.join(c.name for c in degraded)}"
    else:
        overall_status = HealthStatus.HEALTHY
        message = "All systems healthy and operational"

    # Max latency across all checks
    max_latency = max(c.latency_ms for c in components)

    return HealthCheck(
        status=overall_status,
        message=message,
        latency_ms=max_latency,
        components=components_dict,
    )


def create_health_endpoint(health_check_fn: Callable[[], HealthCheck]) -> Callable:
    """
    Create HTTP endpoint for health checks.
    Returns JSON with proper status codes.
    Supports Kubernetes liveness/readiness probes.
    """

    def endpoint(probe_type: str = "health") -> Dict[str, Any]:
        """Health endpoint handler."""
        try:
            health = health_check_fn()

            # Build response body
            body = {
                "status": health.status.value,
                "message": health.message,
                "timestamp": health.timestamp,
                "latency_ms": health.latency_ms,
                "components": {},
            }

            # Add component details
            for name, comp in health.components.items():
                body["components"][name] = {
                    "status": comp.status.value,
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                    "details": comp.details,
                }

            # Determine HTTP status code
            if probe_type == "liveness":
                # Liveness only fails if completely broken
                status_code = 503 if health.status == HealthStatus.UNHEALTHY else 200
            elif probe_type == "readiness":
                # Readiness fails if degraded or unhealthy
                status_code = 200 if health.status == HealthStatus.HEALTHY else 503
            else:
                # Standard health check
                status_code = 503 if health.status == HealthStatus.UNHEALTHY else 200

            return {
                "status_code": status_code,
                "content_type": "application/json",
                "body": json.dumps(body, indent=2),
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status_code": 503,
                "content_type": "application/json",
                "body": json.dumps(
                    {
                        "status": "unhealthy",
                        "message": f"Health check error: {str(e)}",
                        "timestamp": time.time(),
                    }
                ),
            }

    return endpoint
