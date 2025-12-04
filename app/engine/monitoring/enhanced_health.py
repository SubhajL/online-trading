"""Enhanced health monitoring with comprehensive dependency verification."""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import aiohttp
import asyncpg
import redis.asyncio as redis

from .health import ComponentHealth, HealthStatus
from .health import HealthConfig as BaseHealthConfig


class DependencyStatus(Enum):
    """Status of external service dependencies."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"


@dataclass
class ServiceDependency:
    """Represents an external service dependency."""

    service: str
    status: DependencyStatus
    message: str = ""
    latency_ms: float = 0
    critical: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.now)


@dataclass
class HealthConfig(BaseHealthConfig):
    """Extended health configuration with dependency settings."""

    router_url: str = "http://localhost:8080"
    router_health_path: str = "/healthz"
    dependency_timeout: int = 5  # seconds
    max_replication_lag_seconds: int = 10
    max_event_processing_lag_ms: int = 1000
    health_history_size: int = 100


@dataclass
class HealthReport:
    """Comprehensive health report including dependencies."""

    overall_status: HealthStatus
    message: str
    timestamp: datetime
    components: dict[str, ComponentHealth]
    dependencies: dict[str, ServiceDependency]
    all_critical_healthy: bool
    performance_metrics: dict[str, Any] = field(default_factory=dict)


class EnhancedHealthChecker:
    """Enhanced health checker with dependency verification and history tracking."""

    def __init__(self, config: HealthConfig):
        self.config = config
        self.components: dict[str, tuple[Callable, tuple]] = {}
        self.dependencies: dict[str, tuple[str, bool]] = {}  # url, is_critical
        self.health_history: dict[str, deque] = {}
        self._monitor_tasks: dict[str, asyncio.Task] = {}
        self._running = False

    def register_component(self, name: str, check_func: Callable, *args):
        """Register a component health check with its arguments."""
        self.components[name] = (check_func, args)
        self.health_history[name] = deque(maxlen=self.config.health_history_size)

    def register_dependency(self, name: str, health_url: str, critical: bool = False):
        """Register an external service dependency."""
        self.dependencies[name] = (health_url, critical)

    async def check_service_dependency(
        self, service: str, url: str
    ) -> ServiceDependency:
        """Check health of an external service dependency."""
        start_time = asyncio.get_event_loop().time()

        try:
            timeout = aiohttp.ClientTimeout(total=self.config.dependency_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    if response.status == 200:
                        try:
                            data = await response.json()
                            status = DependencyStatus.AVAILABLE
                            message = "Service is healthy"
                            details = data
                        except Exception:
                            # Still consider it available if we got 200
                            status = DependencyStatus.AVAILABLE
                            message = "Service responded with 200 OK"
                            details = {}
                    else:
                        status = (
                            DependencyStatus.DEGRADED
                            if response.status < 500
                            else DependencyStatus.UNAVAILABLE
                        )
                        message = f"Service returned status {response.status}"
                        details = {"http_status": response.status}

                    return ServiceDependency(
                        service=service,
                        status=status,
                        message=message,
                        latency_ms=latency_ms,
                        details=details,
                    )

        except aiohttp.ClientTimeout:
            return ServiceDependency(
                service=service,
                status=DependencyStatus.TIMEOUT,
                message=f"Health check timeout after {self.config.dependency_timeout}s",
                latency_ms=self.config.dependency_timeout * 1000,
            )
        except Exception as e:
            return ServiceDependency(
                service=service,
                status=DependencyStatus.UNAVAILABLE,
                message=str(e),
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )

    async def check_all_dependencies(self) -> dict[str, ServiceDependency]:
        """Check all registered service dependencies."""
        results = {}

        tasks = []
        for name, (url, critical) in self.dependencies.items():
            task = self.check_service_dependency(name, url)
            tasks.append((name, task, critical))

        for name, task, critical in tasks:
            result = await task
            result.critical = critical
            results[name] = result

        return results

    async def check_event_bus_health(self, event_bus: Any) -> ComponentHealth:
        """Enhanced event bus health check with backlog monitoring."""
        start_time = asyncio.get_event_loop().time()

        try:
            if not hasattr(event_bus, "is_running") or not event_bus.is_running():
                return ComponentHealth(
                    name="event_bus",
                    status=HealthStatus.UNHEALTHY,
                    message="Event bus is not running",
                    latency_ms=0,
                )

            details = {}

            # Get basic metrics
            if hasattr(event_bus, "get_queue_sizes"):
                details["queue_sizes"] = event_bus.get_queue_sizes()

            if hasattr(event_bus, "get_subscriber_counts"):
                details["subscriber_counts"] = event_bus.get_subscriber_counts()

            # Get advanced metrics
            if hasattr(event_bus, "get_event_metrics"):
                metrics = event_bus.get_event_metrics()
                details.update(metrics)

                # Check for processing lag
                processing_lag = metrics.get("processing_lag_ms", 0)
                backlog_size = metrics.get("events_published", 0) - metrics.get(
                    "events_processed", 0
                )
                details["backlog_size"] = backlog_size

                if processing_lag > self.config.max_event_processing_lag_ms:
                    return ComponentHealth(
                        name="event_bus",
                        status=HealthStatus.DEGRADED,
                        message=f"High processing lag: {processing_lag}ms",
                        latency_ms=(asyncio.get_event_loop().time() - start_time)
                        * 1000,
                        details=details,
                    )

            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            return ComponentHealth(
                name="event_bus",
                status=HealthStatus.HEALTHY,
                message="Event bus is operational",
                latency_ms=latency_ms,
                details=details,
            )

        except Exception as e:
            return ComponentHealth(
                name="event_bus",
                status=HealthStatus.UNHEALTHY,
                message=f"Event bus error: {e!s}",
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )

    async def check_database_health(self, connection_string: str) -> ComponentHealth:
        """Enhanced database health check with replication monitoring."""
        start_time = asyncio.get_event_loop().time()

        try:
            conn = await asyncpg.connect(connection_string)
            try:
                # Basic connectivity check
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise ValueError("Unexpected database response")

                details = {}

                # Check database size
                db_size = await conn.fetchval(
                    "SELECT pg_database_size(current_database())",
                )
                details["database_size_mb"] = db_size / (1024 * 1024)

                # Check active connections
                active_conns = await conn.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'",
                )
                details["active_connections"] = active_conns

                # Check replication lag (if replica)
                try:
                    lag_bytes = await conn.fetchval(
                        "SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) "
                        "FROM pg_stat_replication",
                    )
                    if lag_bytes:
                        # Estimate lag in seconds (rough approximation)
                        lag_seconds = lag_bytes / (16 * 1024 * 1024)  # Assume 16MB/s
                        details["replication_lag_seconds"] = lag_seconds

                        if lag_seconds > self.config.max_replication_lag_seconds:
                            return ComponentHealth(
                                name="database",
                                status=HealthStatus.DEGRADED,
                                message=f"High replication lag: {lag_seconds:.1f}s",
                                latency_ms=(
                                    asyncio.get_event_loop().time() - start_time
                                )
                                * 1000,
                                details=details,
                            )
                except Exception:
                    # Not a replica or no permission
                    pass

                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="Database is responsive",
                    latency_ms=latency_ms,
                    details=details,
                )

            finally:
                await conn.close()

        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {e!s}",
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )

    async def check_redis_health(self, redis_url: str) -> ComponentHealth:
        """Standard Redis health check (inherited functionality)."""
        start_time = asyncio.get_event_loop().time()

        try:
            client = redis.from_url(redis_url)
            try:
                await client.ping()

                details = {}
                if self.config.include_details:
                    info = await client.info("memory")
                    if info:
                        details["memory_used_mb"] = info.get("used_memory", 0) / (
                            1024 * 1024
                        )
                        details["memory_peak_mb"] = info.get("used_memory_peak", 0) / (
                            1024 * 1024
                        )

                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                return ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    message="Redis is responsive",
                    latency_ms=latency_ms,
                    details=details,
                )
            finally:
                await client.aclose()

        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {e!s}",
                latency_ms=(asyncio.get_event_loop().time() - start_time) * 1000,
            )

    async def get_comprehensive_health(self) -> HealthReport:
        """Get comprehensive health report including all components and dependencies."""
        # Check all components
        component_results = {}
        for name, (check_func, args) in self.components.items():
            try:
                result = await check_func(*args)
                component_results[name] = result
                # Track history
                self.health_history[name].append(
                    {
                        "timestamp": datetime.now(),
                        "status": result.status,
                        "latency_ms": result.latency_ms,
                    }
                )
            except Exception as e:
                component_results[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {e!s}",
                )

        # Check all dependencies
        dependency_results = await self.check_all_dependencies()

        # Determine overall status
        all_statuses = [comp.status for comp in component_results.values()]
        all_dep_statuses = [dep.status for dep in dependency_results.values()]

        # Check critical dependencies
        critical_deps_healthy = all(
            dep.status == DependencyStatus.AVAILABLE
            for dep in dependency_results.values()
            if dep.critical
        )

        # Determine overall health
        if (
            any(s == HealthStatus.UNHEALTHY for s in all_statuses)
            or not critical_deps_healthy
        ):
            overall_status = HealthStatus.UNHEALTHY
            if not critical_deps_healthy:
                message = "Critical dependency unavailable"
            else:
                message = "One or more components unhealthy"
        elif any(s == HealthStatus.DEGRADED for s in all_statuses) or any(
            d.status == DependencyStatus.DEGRADED for d in dependency_results.values()
        ):
            overall_status = HealthStatus.DEGRADED
            message = "System degraded but operational"
        else:
            overall_status = HealthStatus.HEALTHY
            message = "All systems operational"

        # Calculate performance metrics
        perf_metrics = {
            "avg_component_latency_ms": sum(
                c.latency_ms or 0 for c in component_results.values()
            )
            / len(component_results)
            if component_results
            else 0,
            "avg_dependency_latency_ms": sum(
                d.latency_ms for d in dependency_results.values()
            )
            / len(dependency_results)
            if dependency_results
            else 0,
        }

        return HealthReport(
            overall_status=overall_status,
            message=message,
            timestamp=datetime.now(),
            components=component_results,
            dependencies=dependency_results,
            all_critical_healthy=critical_deps_healthy,
            performance_metrics=perf_metrics,
        )

    async def start_monitoring(self):
        """Start continuous health monitoring."""
        self._running = True

        async def monitor_loop(name: str, check_func: Callable, args: tuple):
            while self._running:
                try:
                    await asyncio.sleep(self.config.check_interval)
                    result = await check_func(*args)
                    self.health_history[name].append(
                        {
                            "timestamp": datetime.now(),
                            "status": result.status,
                            "latency_ms": result.latency_ms,
                        }
                    )
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass

        # Start monitoring tasks for each component
        for name, (check_func, args) in self.components.items():
            task = asyncio.create_task(monitor_loop(name, check_func, args))
            self._monitor_tasks[name] = task

    async def stop_monitoring(self):
        """Stop all monitoring tasks."""
        self._running = False

        for task in self._monitor_tasks.values():
            task.cancel()

        await asyncio.gather(*self._monitor_tasks.values(), return_exceptions=True)
        self._monitor_tasks.clear()
