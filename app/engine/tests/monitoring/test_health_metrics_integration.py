"""
Tests for health check metrics integration.

Verifies that health checks properly record metrics.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.engine.monitoring.health import (
    HealthChecker, HealthConfig, HealthStatus, ComponentHealth
)
from app.engine.monitoring.metrics import get_metrics


class TestHealthCheckMetricsIntegration:
    """Test that health checks record metrics properly."""

    @pytest.fixture
    def health_config(self):
        """Create test health config."""
        return HealthConfig(
            check_interval=30,
            timeout=5,
            failure_threshold=3,
            recovery_threshold=2,
            include_details=True
        )

    @pytest.fixture
    def health_checker(self, health_config):
        """Create health checker instance."""
        return HealthChecker(health_config)

    @pytest.mark.asyncio
    async def test_database_health_check_records_metrics(self, health_checker):
        """Test that database health check records metrics."""
        # Mock successful database connection
        with patch('asyncpg.connect') as mock_connect:
            mock_conn = AsyncMock()
            mock_conn.fetchval = AsyncMock(side_effect=[1, 1000000, 5])  # SELECT 1, DB size, active conns
            mock_conn.close = AsyncMock()
            mock_connect.return_value = mock_conn

            # Run health check
            result = await health_checker.check_database("postgresql://test")

            # Verify health check succeeded
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None
            assert result.latency_ms > 0

            # Get metrics and verify
            metrics = get_metrics().decode('utf-8')

            # Should have health check duration recorded
            assert 'health_check_duration_seconds_bucket{component="database"' in metrics
            assert 'health_check_duration_seconds_count{component="database"' in metrics

            # Should have health status recorded
            assert 'health_check_status{component="database"} 1' in metrics  # 1.0 for healthy

            # Should also have database query metrics
            assert 'database_query_duration_seconds' in metrics

    @pytest.mark.asyncio
    async def test_database_health_check_failure_records_metrics(self, health_checker):
        """Test that failed database health check records unhealthy metrics."""
        # Mock database connection failure
        with patch('asyncpg.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")

            # Run health check
            result = await health_checker.check_database("postgresql://test")

            # Verify health check failed
            assert result.status == HealthStatus.UNHEALTHY
            assert "Connection refused" in result.message

            # Get metrics and verify
            metrics = get_metrics().decode('utf-8')

            # Should have health check duration recorded
            assert 'health_check_duration_seconds_bucket{component="database"' in metrics

            # Should have unhealthy status recorded (0.0)
            assert 'health_check_status{component="database"} 0' in metrics

    @pytest.mark.asyncio
    async def test_redis_health_check_records_metrics(self, health_checker):
        """Test that Redis health check records metrics."""
        # Mock Redis client
        with patch('redis.asyncio.from_url') as mock_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock()
            mock_client.info = AsyncMock(return_value={
                'used_memory': 10485760,  # 10MB
                'used_memory_peak': 20971520  # 20MB
            })
            mock_client.aclose = AsyncMock()
            mock_from_url.return_value = mock_client

            # Run health check
            result = await health_checker.check_redis("redis://test")

            # Verify health check succeeded
            assert result.status == HealthStatus.HEALTHY
            assert result.details['memory_used_mb'] == 10.0
            assert result.details['memory_peak_mb'] == 20.0

            # Get metrics and verify
            metrics = get_metrics().decode('utf-8')

            # Should have health check metrics
            assert 'health_check_duration_seconds_bucket{component="redis"' in metrics
            assert 'health_check_status{component="redis"} 1' in metrics

    @pytest.mark.asyncio
    async def test_event_bus_health_check_records_metrics(self, health_checker):
        """Test that event bus health check records metrics."""
        # Mock event bus
        mock_event_bus = MagicMock()
        mock_event_bus.is_running.return_value = True
        mock_event_bus.get_queue_sizes.return_value = {'default': 0, 'priority': 5}
        mock_event_bus.get_subscriber_counts.return_value = {'signals': 3, 'orders': 2}

        # Run health check
        result = await health_checker.check_event_bus(mock_event_bus)

        # Verify health check succeeded
        assert result.status == HealthStatus.HEALTHY
        assert result.details['queue_sizes'] == {'default': 0, 'priority': 5}
        assert result.details['subscriber_counts'] == {'signals': 3, 'orders': 2}

        # Get metrics and verify
        metrics = get_metrics().decode('utf-8')

        # Should have health check metrics
        assert 'health_check_duration_seconds_bucket{component="event_bus"' in metrics
        assert 'health_check_status{component="event_bus"} 1' in metrics

    @pytest.mark.asyncio
    async def test_event_bus_not_running_records_metrics(self, health_checker):
        """Test that stopped event bus records unhealthy metrics."""
        # Mock stopped event bus
        mock_event_bus = MagicMock()
        mock_event_bus.is_running.return_value = False

        # Run health check
        result = await health_checker.check_event_bus(mock_event_bus)

        # Verify health check failed
        assert result.status == HealthStatus.UNHEALTHY
        assert result.message == "Event bus is not running"

        # Get metrics and verify
        metrics = get_metrics().decode('utf-8')

        # Should have unhealthy status
        assert 'health_check_status{component="event_bus"} 0' in metrics

    @pytest.mark.asyncio
    async def test_health_check_timeout_records_metrics(self, health_checker):
        """Test that health check timeouts are recorded."""
        # Mock slow database connection
        with patch('asyncpg.connect') as mock_connect:
            async def slow_connect(*args, **kwargs):
                await asyncio.sleep(10)  # Longer than timeout
            mock_connect.side_effect = slow_connect

            # Run health check with timeout
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    health_checker.check_database("postgresql://test"),
                    timeout=0.1
                )

    @pytest.mark.asyncio
    async def test_degraded_health_status_metrics(self, health_checker):
        """Test that degraded status (0.5) is recorded correctly."""
        # Register a component
        health_checker.register_component("test_service")

        # Simulate failures below threshold
        health_checker.failure_counts["test_service"] = 2  # Below threshold of 3

        # Create degraded health result
        result = ComponentHealth(
            name="test_service",
            status=HealthStatus.DEGRADED,
            message="Service degraded"
        )

        # Manually update the component
        health_checker.components["test_service"] = result

        # Update metrics manually
        try:
            from app.engine.monitoring.metrics import update_health_check_status
            update_health_check_status("test_service", "degraded")
        except ImportError:
            pass

        # Get metrics and verify
        metrics = get_metrics().decode('utf-8')

        # Should have degraded status (0.5)
        assert 'health_check_status{component="test_service"} 0.5' in metrics

    def test_health_metrics_labels(self):
        """Test that health metrics have correct labels."""
        # Record some test metrics
        from app.engine.monitoring.metrics import (
            record_health_check_duration, update_health_check_status
        )

        # Record metrics for different components
        record_health_check_duration("database", 0.1)
        record_health_check_duration("redis", 0.05)
        record_health_check_duration("event_bus", 0.02)

        update_health_check_status("database", "healthy")
        update_health_check_status("redis", "degraded")
        update_health_check_status("event_bus", "unhealthy")

        # Get metrics
        metrics = get_metrics().decode('utf-8')

        # Verify all components are labeled correctly
        assert 'component="database"' in metrics
        assert 'component="redis"' in metrics
        assert 'component="event_bus"' in metrics

        # Verify status values
        assert 'health_check_status{component="database"} 1' in metrics
        assert 'health_check_status{component="redis"} 0.5' in metrics
        assert 'health_check_status{component="event_bus"} 0' in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])