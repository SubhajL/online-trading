"""Tests for enhanced health monitoring system."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ClientError, ClientTimeout
import pytest

from app.engine.monitoring.enhanced_health import (
    ComponentHealth,
    DependencyStatus,
    EnhancedHealthChecker,
    HealthConfig,
    HealthReport,
    HealthStatus,
    ServiceDependency,
)


@pytest.fixture
def health_config():
    """Create test health config."""
    return HealthConfig(
        check_interval=5,
        timeout=2,
        failure_threshold=3,
        recovery_threshold=2,
        include_details=True,
        router_url="http://localhost:8080",
        router_health_path="/healthz",
    )


@pytest.fixture
def mock_event_bus():
    """Create mock event bus."""
    bus = MagicMock()
    bus.is_running = MagicMock(return_value=True)
    bus.get_queue_sizes = MagicMock(return_value={"candle_update": 5, "features": 3})
    bus.get_subscriber_counts = MagicMock(
        return_value={"candle_update": 2, "features": 1},
    )
    bus.get_event_metrics = MagicMock(
        return_value={
            "events_published": 1000,
            "events_processed": 995,
            "processing_lag_ms": 50,
        },
    )
    return bus


class TestEnhancedHealthChecker:
    """Test enhanced health checker functionality."""

    @pytest.mark.asyncio
    async def test_check_service_dependency_healthy(self, health_config):
        """Test checking healthy service dependency."""
        checker = EnhancedHealthChecker(health_config)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"status": "healthy"})
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await checker.check_service_dependency(
                "router", "http://localhost:8080/healthz",
            )

            assert result.service == "router"
            assert result.status == DependencyStatus.AVAILABLE
            assert result.latency_ms is not None
            assert result.latency_ms < 2000  # Should be less than timeout
            assert "healthy" in result.details

    @pytest.mark.asyncio
    async def test_check_service_dependency_timeout(self, health_config):
        """Test service dependency check with timeout."""
        checker = EnhancedHealthChecker(health_config)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get.side_effect = ClientTimeout()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await checker.check_service_dependency(
                "router", "http://localhost:8080/healthz",
            )

            assert result.service == "router"
            assert result.status == DependencyStatus.TIMEOUT
            assert "timeout" in result.message.lower()

    @pytest.mark.asyncio
    async def test_check_service_dependency_error(self, health_config):
        """Test service dependency check with connection error."""
        checker = EnhancedHealthChecker(health_config)

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_session.get.side_effect = ClientError("Connection refused")
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()
            mock_session_class.return_value = mock_session

            result = await checker.check_service_dependency(
                "router", "http://localhost:8080/healthz",
            )

            assert result.service == "router"
            assert result.status == DependencyStatus.UNAVAILABLE
            assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_check_all_dependencies(self, health_config):
        """Test checking all service dependencies."""
        checker = EnhancedHealthChecker(health_config)

        # Register dependencies
        checker.register_dependency(
            "router", "http://localhost:8080/healthz", critical=True,
        )
        checker.register_dependency(
            "external_api", "https://api.example.com/health", critical=False,
        )

        with patch.object(checker, "check_service_dependency") as mock_check:
            mock_check.side_effect = [
                ServiceDependency("router", DependencyStatus.AVAILABLE, "Healthy", 10),
                ServiceDependency(
                    "external_api", DependencyStatus.UNAVAILABLE, "Connection error", 0,
                ),
            ]

            results = await checker.check_all_dependencies()

            assert len(results) == 2
            assert results["router"].status == DependencyStatus.AVAILABLE
            assert results["external_api"].status == DependencyStatus.UNAVAILABLE

    @pytest.mark.asyncio
    async def test_check_event_bus_health_with_backlog(
        self, health_config, mock_event_bus,
    ):
        """Test event bus health check with message backlog."""
        checker = EnhancedHealthChecker(health_config)

        # Simulate high processing lag
        mock_event_bus.get_event_metrics.return_value = {
            "events_published": 10000,
            "events_processed": 8000,
            "processing_lag_ms": 5000,  # 5 second lag
        }

        result = await checker.check_event_bus_health(mock_event_bus)

        assert result.name == "event_bus"
        assert result.status == HealthStatus.DEGRADED
        assert "high processing lag" in result.message.lower()
        assert result.details["processing_lag_ms"] == 5000
        assert result.details["backlog_size"] == 2000

    @pytest.mark.asyncio
    async def test_check_event_bus_health_not_running(self, health_config):
        """Test event bus health check when not running."""
        checker = EnhancedHealthChecker(health_config)

        mock_bus = MagicMock()
        mock_bus.is_running.return_value = False

        result = await checker.check_event_bus_health(mock_bus)

        assert result.name == "event_bus"
        assert result.status == HealthStatus.UNHEALTHY
        assert "not running" in result.message.lower()

    @pytest.mark.asyncio
    async def test_database_health_check_with_replication_lag(self, health_config):
        """Test database health check including replication lag."""
        checker = EnhancedHealthChecker(health_config)

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock()
        mock_conn.fetch = AsyncMock()
        mock_conn.close = AsyncMock()

        # Mock database responses
        mock_conn.fetchval.side_effect = [
            1,  # SELECT 1
            104857600,  # Database size (100MB)
            5,  # Active connections
            15,  # Replication lag in seconds
        ]

        with patch("asyncpg.connect", return_value=mock_conn):
            result = await checker.check_database_health("postgresql://test")

            assert result.name == "database"
            assert result.status == HealthStatus.DEGRADED
            assert "replication lag" in result.message.lower()
            assert result.details["replication_lag_seconds"] == 15

    @pytest.mark.asyncio
    async def test_get_comprehensive_health_report(self, health_config, mock_event_bus):
        """Test getting comprehensive health report."""
        checker = EnhancedHealthChecker(health_config)

        # Register components and dependencies
        checker.register_component(
            "database", checker.check_database_health, "postgresql://test",
        )
        checker.register_component(
            "redis", checker.check_redis_health, "redis://localhost",
        )
        checker.register_component(
            "event_bus", checker.check_event_bus_health, mock_event_bus,
        )
        checker.register_dependency(
            "router", "http://localhost:8080/healthz", critical=True,
        )

        # Mock health check results
        with patch.multiple(
            checker,
            check_database_health=AsyncMock(
                return_value=ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=10,
                ),
            ),
            check_redis_health=AsyncMock(
                return_value=ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=5,
                ),
            ),
            check_event_bus_health=AsyncMock(
                return_value=ComponentHealth(
                    name="event_bus",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=1,
                ),
            ),
            check_service_dependency=AsyncMock(
                return_value=ServiceDependency(
                    service="router",
                    status=DependencyStatus.AVAILABLE,
                    message="OK",
                    latency_ms=20,
                ),
            ),
        ):
            report = await checker.get_comprehensive_health()

            assert isinstance(report, HealthReport)
            assert report.overall_status == HealthStatus.HEALTHY
            assert report.all_critical_healthy is True
            assert len(report.components) == 3
            assert len(report.dependencies) == 1
            assert report.components["database"].status == HealthStatus.HEALTHY
            assert report.dependencies["router"].status == DependencyStatus.AVAILABLE

    @pytest.mark.asyncio
    async def test_comprehensive_health_with_critical_failure(
        self, health_config, mock_event_bus,
    ):
        """Test comprehensive health report with critical dependency failure."""
        checker = EnhancedHealthChecker(health_config)

        checker.register_component(
            "database", checker.check_database_health, "postgresql://test",
        )
        checker.register_dependency(
            "router", "http://localhost:8080/healthz", critical=True,
        )

        with patch.multiple(
            checker,
            check_database_health=AsyncMock(
                return_value=ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    message="OK",
                    latency_ms=10,
                ),
            ),
            check_service_dependency=AsyncMock(
                return_value=ServiceDependency(
                    service="router",
                    status=DependencyStatus.UNAVAILABLE,
                    message="Connection refused",
                    latency_ms=0,
                ),
            ),
        ):
            report = await checker.get_comprehensive_health()

            assert report.overall_status == HealthStatus.UNHEALTHY
            assert report.all_critical_healthy is False
            assert "Critical dependency unavailable" in report.message

    @pytest.mark.asyncio
    async def test_periodic_health_monitoring(self, health_config):
        """Test periodic health monitoring with state transitions."""
        health_config.check_interval = 0.1  # 100ms for faster test
        checker = EnhancedHealthChecker(health_config)

        # Track health check calls
        check_count = 0
        health_states = [
            HealthStatus.HEALTHY,
            HealthStatus.DEGRADED,
            HealthStatus.UNHEALTHY,
            HealthStatus.HEALTHY,
        ]

        async def mock_check():
            nonlocal check_count
            status = health_states[min(check_count, len(health_states) - 1)]
            check_count += 1
            return ComponentHealth(
                name="test", status=status, message=f"Check {check_count}",
            )

        checker.register_component("test", mock_check)

        # Start monitoring
        await checker.start_monitoring()

        # Wait for multiple check cycles
        await asyncio.sleep(0.5)

        # Stop monitoring
        await checker.stop_monitoring()

        # Verify multiple checks occurred
        assert check_count >= 4

        # Verify state history was tracked
        assert "test" in checker.health_history
        assert len(checker.health_history["test"]) >= 4
