"""Enhanced health monitoring endpoints with dependency checking."""

from typing import Any

from fastapi import APIRouter, Response, status

from .enhanced_health import EnhancedHealthChecker, HealthConfig


def create_enhanced_health_endpoints(
    health_checker: EnhancedHealthChecker | None = None,
) -> APIRouter:
    """Create enhanced health check API endpoints."""
    router = APIRouter(prefix="/health", tags=["health"])

    @router.get("/")
    async def health_check() -> dict[str, str]:
        """Basic health check endpoint."""
        return {"status": "healthy"}

    @router.get("/live")
    @router.get("/liveness")
    async def liveness_check() -> dict[str, str]:
        """Kubernetes liveness probe endpoint."""
        return {"status": "alive"}

    @router.get("/ready")
    @router.get("/readiness")
    async def readiness_check(response: Response) -> dict[str, Any]:
        """Enhanced readiness check with dependency verification."""
        if not health_checker:
            return {"ready": True}

        # Get comprehensive health
        report = await health_checker.get_comprehensive_health()

        # Check if all critical components and dependencies are healthy
        ready = report.all_critical_healthy and report.overall_status != "unhealthy"

        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "ready": ready,
            "timestamp": report.timestamp.isoformat(),
            "message": report.message,
            "details": {
                "components": {
                    name: {
                        "status": comp.status.value,
                        "message": comp.message,
                    }
                    for name, comp in report.components.items()
                },
                "dependencies": {
                    name: {
                        "status": dep.status.value,
                        "critical": dep.critical,
                    }
                    for name, dep in report.dependencies.items()
                },
            },
        }

    @router.get("/status")
    async def detailed_health_status(response: Response) -> dict[str, Any]:
        """Comprehensive health status including dependencies."""
        if not health_checker:
            return {"status": "unknown", "message": "Health checker not configured"}

        report = await health_checker.get_comprehensive_health()

        # Set appropriate HTTP status code
        if report.overall_status.value == "unhealthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif report.overall_status.value == "degraded":
            response.status_code = status.HTTP_200_OK

        return {
            "status": report.overall_status.value,
            "message": report.message,
            "timestamp": report.timestamp.isoformat(),
            "all_critical_healthy": report.all_critical_healthy,
            "performance_metrics": report.performance_metrics,
            "components": {
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "latency_ms": comp.latency_ms,
                    "details": comp.details,
                    "last_check": comp.last_check.isoformat(),
                }
                for name, comp in report.components.items()
            },
            "dependencies": {
                name: {
                    "service": dep.service,
                    "status": dep.status.value,
                    "critical": dep.critical,
                    "message": dep.message,
                    "latency_ms": dep.latency_ms,
                    "details": dep.details,
                    "last_check": dep.last_check.isoformat(),
                }
                for name, dep in report.dependencies.items()
            },
        }

    @router.post("/check")
    async def run_health_checks() -> dict[str, Any]:
        """Manually trigger comprehensive health checks."""
        if not health_checker:
            return {"status": "error", "message": "Health checker not configured"}

        report = await health_checker.get_comprehensive_health()
        return {
            "status": report.overall_status.value,
            "message": "Health checks completed",
            "timestamp": report.timestamp.isoformat(),
            "results": {
                "components": len(report.components),
                "dependencies": len(report.dependencies),
                "all_critical_healthy": report.all_critical_healthy,
            },
        }

    @router.get("/dependencies")
    async def check_dependencies() -> dict[str, Any]:
        """Check only external service dependencies."""
        if not health_checker:
            return {"status": "error", "message": "Health checker not configured"}

        dependencies = await health_checker.check_all_dependencies()

        all_available = all(
            dep.status.value == "available" for dep in dependencies.values()
        )

        critical_available = all(
            dep.status.value == "available"
            for dep in dependencies.values()
            if dep.critical
        )

        return {
            "all_available": all_available,
            "critical_available": critical_available,
            "dependencies": {
                name: {
                    "status": dep.status.value,
                    "critical": dep.critical,
                    "message": dep.message,
                    "latency_ms": dep.latency_ms,
                }
                for name, dep in dependencies.items()
            },
        }

    return router


def setup_enhanced_health_monitoring(
    app: Any,
    database_url: str,
    redis_url: str,
    event_bus: Any,
    router_url: str | None = None,
) -> EnhancedHealthChecker:
    """Setup enhanced health monitoring with dependency checking."""
    # Create enhanced health checker
    config = HealthConfig.from_env()
    if router_url:
        config.router_url = router_url

    health_checker = EnhancedHealthChecker(config)

    # Register component health checks
    health_checker.register_component(
        "database",
        health_checker.check_database_health,
        database_url,
    )
    health_checker.register_component(
        "redis",
        health_checker.check_redis_health,
        redis_url,
    )
    health_checker.register_component(
        "event_bus",
        health_checker.check_event_bus_health,
        event_bus,
    )

    # Register service dependencies
    health_checker.register_dependency(
        "router",
        f"{config.router_url}{config.router_health_path}",
        critical=True,
    )

    # Add endpoints to app
    app.include_router(create_enhanced_health_endpoints(health_checker))

    # Start monitoring on app startup
    @app.on_event("startup")
    async def start_health_monitoring() -> None:
        await health_checker.start_monitoring()

    @app.on_event("shutdown")
    async def stop_health_monitoring() -> None:
        await health_checker.stop_monitoring()

    return health_checker
