from typing import Any

from fastapi import APIRouter, Response, status

from app.engine.monitoring.health import HealthChecker, ReadinessChecker


def create_health_endpoints(
    health_checker: HealthChecker | None = None,
    readiness_checker: ReadinessChecker | None = None,
) -> APIRouter:
    """Create health check API endpoints"""
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/")
    async def health_check() -> dict[str, str]:
        """Basic health check endpoint"""
        return {"status": "healthy"}

    @router.get("/live")
    @router.get("/liveness")
    async def liveness_check() -> dict[str, str]:
        """Kubernetes liveness probe endpoint"""
        # Liveness just checks if the process is alive
        return {"status": "alive"}

    @router.get("/ready")
    @router.get("/readiness")
    async def readiness_check(response: Response) -> dict[str, Any]:
        """Kubernetes readiness probe endpoint"""
        if not readiness_checker:
            # If no readiness checker configured, assume ready
            return {"ready": True}

        result = await readiness_checker.is_ready()

        if not result["ready"]:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return result

    @router.get("/status")
    async def detailed_health_status(response: Response) -> dict[str, Any]:
        """Detailed health status of all components"""
        if not health_checker:
            return {"status": "unknown", "message": "Health checker not configured"}

        health = health_checker.get_overall_health()

        # Set appropriate HTTP status code
        if health["status"] == "unhealthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif health["status"] == "degraded":
            response.status_code = status.HTTP_200_OK  # Or use 207 Multi-Status

        return health

    @router.post("/check")
    async def run_health_checks() -> dict[str, Any]:
        """Manually trigger all health checks"""
        if not health_checker:
            return {"status": "error", "message": "Health checker not configured"}

        return await health_checker.run_all_checks()

    return router


def create_metrics_endpoints() -> APIRouter:
    """Create metrics endpoints for Prometheus scraping"""
    router = APIRouter(prefix="/metrics", tags=["metrics"])

    @router.get("/")
    async def prometheus_metrics() -> Response:
        """Prometheus metrics endpoint"""
        try:
            from app.engine.monitoring.metrics import (
                get_metrics,
                get_metrics_content_type,
            )

            # Get metrics from our Prometheus registry
            metrics_data = get_metrics()

            return Response(
                content=metrics_data,
                media_type=get_metrics_content_type(),
            )
        except ImportError:
            # Fallback if metrics module not available
            metrics = []

            # Example metrics
            metrics.append("# HELP python_info Python platform information")
            metrics.append("# TYPE python_info gauge")
            metrics.append('python_info{implementation="CPython",version="3.11"} 1')

            # Add actual process metrics
            import os

            import psutil

            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            metrics.append(
                "# HELP process_virtual_memory_bytes Virtual memory size in bytes",
            )
            metrics.append("# TYPE process_virtual_memory_bytes gauge")
            metrics.append(f"process_virtual_memory_bytes {memory_info.vms}")
            metrics.append(f"process_resident_memory_bytes {memory_info.rss}")

            return Response(
                content="\n".join(metrics) + "\n",
                media_type="text/plain; version=0.0.4",
            )

    return router


def setup_health_monitoring(
    app: Any, database_url: str, redis_url: str, event_bus: Any,
) -> tuple[HealthChecker, ReadinessChecker]:
    """Setup health monitoring for the application"""
    from app.engine.monitoring.health import (
        HealthChecker,
        HealthConfig,
        ReadinessChecker,
    )

    # Create health checker
    config = HealthConfig.from_env()
    health_checker = HealthChecker(config)

    # Register components with custom checks
    async def check_db() -> Any:
        return await health_checker.check_database(database_url)

    async def check_redis() -> Any:
        return await health_checker.check_redis(redis_url)

    async def check_bus() -> Any:
        return await health_checker.check_event_bus(event_bus)

    health_checker.register_component("database", check_db)
    health_checker.register_component("redis", check_redis)
    health_checker.register_component("event_bus", check_bus)

    # Create readiness checker
    readiness_checker = ReadinessChecker()

    async def db_ready() -> bool:
        try:
            result = await check_db()
            return bool(result.status != "unhealthy")
        except Exception:
            return False

    async def redis_ready() -> bool:
        try:
            result = await check_redis()
            return bool(result.status != "unhealthy")
        except Exception:
            return False

    readiness_checker.register_check("database", db_ready, required=True)
    readiness_checker.register_check("redis", redis_ready, required=True)
    readiness_checker.register_check(
        "event_bus",
        lambda: event_bus.is_running() if hasattr(event_bus, "is_running") else True,
        required=True,
    )

    # Add endpoints to app
    app.include_router(create_health_endpoints(health_checker, readiness_checker))
    app.include_router(create_metrics_endpoints())

    # Start monitoring on app startup
    @app.on_event("startup")
    async def start_health_monitoring() -> None:
        await health_checker.start_monitoring()

    @app.on_event("shutdown")
    async def stop_health_monitoring() -> None:
        await health_checker.stop_monitoring()

    return health_checker, readiness_checker
