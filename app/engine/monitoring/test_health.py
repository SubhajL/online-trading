import os
import pytest
import asyncio
from unittest import mock
from datetime import datetime, timedelta

from app.engine.monitoring.health import (
    HealthStatus,
    ComponentHealth,
    HealthConfig,
    HealthChecker,
    ReadinessChecker
)


class TestHealthConfig:
    def test_health_config_from_env(self):
        """Test health check configuration from environment variables"""
        env_vars = {
            "HEALTH_CHECK_INTERVAL": "60",
            "HEALTH_CHECK_TIMEOUT": "10",
            "HEALTH_FAILURE_THRESHOLD": "5",
            "HEALTH_RECOVERY_THRESHOLD": "3",
            "HEALTH_INCLUDE_DETAILS": "false",
        }
        
        with mock.patch.dict(os.environ, env_vars):
            config = HealthConfig.from_env()
            
            assert config.check_interval == 60
            assert config.timeout == 10
            assert config.failure_threshold == 5
            assert config.recovery_threshold == 3
            assert config.include_details is False
    
    def test_health_config_defaults(self):
        """Test default health check configuration"""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = HealthConfig.from_env()
            
            assert config.check_interval == 30
            assert config.timeout == 5
            assert config.failure_threshold == 3
            assert config.recovery_threshold == 2
            assert config.include_details is True


class TestHealthChecker:
    @pytest.mark.asyncio
    async def test_register_component(self):
        """Test component registration"""
        config = HealthConfig.from_env()
        checker = HealthChecker(config)
        
        # Register a component
        checker.register_component("test_service")
        
        assert "test_service" in checker.components
        assert checker.components["test_service"].status == HealthStatus.HEALTHY
        assert checker.failure_counts["test_service"] == 0
        assert checker.recovery_counts["test_service"] == 0
    
    @pytest.mark.asyncio
    async def test_custom_check_function(self):
        """Test custom health check function"""
        config = HealthConfig.from_env()
        checker = HealthChecker(config)
        
        # Custom check that always returns healthy
        async def custom_check():
            return ComponentHealth(
                name="custom",
                status=HealthStatus.HEALTHY,
                message="All good",
                latency_ms=10.0
            )
        
        checker.register_component("custom", custom_check)
        await checker._run_check("custom")
        
        assert checker.components["custom"].status == HealthStatus.HEALTHY
        assert checker.components["custom"].message == "All good"
        assert checker.components["custom"].latency_ms == 10.0
    
    @pytest.mark.asyncio
    async def test_failure_threshold(self):
        """Test that failures are tracked with threshold"""
        config = HealthConfig(
            check_interval=1,
            timeout=5,
            failure_threshold=3,
            recovery_threshold=2,
            include_details=False
        )
        checker = HealthChecker(config)
        
        # Check that fails
        fail_count = 0
        async def failing_check():
            nonlocal fail_count
            fail_count += 1
            return ComponentHealth(
                name="failing",
                status=HealthStatus.UNHEALTHY,
                message="Service down"
            )
        
        checker.register_component("failing", failing_check)
        
        # First failure - should be degraded
        await checker._run_check("failing")
        assert checker.components["failing"].status == HealthStatus.DEGRADED
        assert checker.failure_counts["failing"] == 1
        
        # Second failure - still degraded
        await checker._run_check("failing")
        assert checker.components["failing"].status == HealthStatus.DEGRADED
        assert checker.failure_counts["failing"] == 2
        
        # Third failure - now unhealthy
        await checker._run_check("failing")
        assert checker.components["failing"].status == HealthStatus.UNHEALTHY
        assert checker.failure_counts["failing"] == 3
    
    @pytest.mark.asyncio
    async def test_recovery_threshold(self):
        """Test that recovery is tracked with threshold"""
        config = HealthConfig(
            check_interval=1,
            timeout=5,
            failure_threshold=3,
            recovery_threshold=2,
            include_details=False
        )
        checker = HealthChecker(config)

        # Check that succeeds
        async def recovering_check():
            return ComponentHealth(
                name="recovering",
                status=HealthStatus.HEALTHY,
                message="Service recovered"
            )

        checker.register_component("recovering", recovering_check)

        # Start with failures after registration
        checker.failure_counts["recovering"] = 3
        
        # First recovery - should be degraded
        await checker._run_check("recovering")
        assert checker.components["recovering"].status == HealthStatus.DEGRADED
        assert checker.recovery_counts["recovering"] == 1
        
        # Second recovery - now healthy
        await checker._run_check("recovering")
        assert checker.components["recovering"].status == HealthStatus.HEALTHY
        assert checker.recovery_counts["recovering"] == 2
        assert checker.failure_counts["recovering"] == 0
    
    @pytest.mark.asyncio
    async def test_overall_health_status(self):
        """Test overall health status calculation"""
        config = HealthConfig.from_env()
        checker = HealthChecker(config)
        
        # Add components with different statuses
        checker.components["healthy"] = ComponentHealth(
            name="healthy",
            status=HealthStatus.HEALTHY,
            message="OK"
        )
        checker.components["degraded"] = ComponentHealth(
            name="degraded",
            status=HealthStatus.DEGRADED,
            message="Slow"
        )
        checker.components["unhealthy"] = ComponentHealth(
            name="unhealthy",
            status=HealthStatus.UNHEALTHY,
            message="Down"
        )
        
        overall = checker.get_overall_health()
        
        # Should be unhealthy if any component is unhealthy
        assert overall["status"] == "unhealthy"
        assert len(overall["components"]) == 3
        
        # Remove unhealthy component
        del checker.components["unhealthy"]
        overall = checker.get_overall_health()
        
        # Should be degraded if any component is degraded
        assert overall["status"] == "degraded"
        
        # Remove degraded component
        del checker.components["degraded"]
        overall = checker.get_overall_health()
        
        # Should be healthy if all components are healthy
        assert overall["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test starting and stopping monitoring"""
        config = HealthConfig(
            check_interval=0.1,  # 100ms for faster test
            timeout=1,
            failure_threshold=3,
            recovery_threshold=2,
            include_details=False
        )
        checker = HealthChecker(config)
        
        call_count = 0
        async def counting_check():
            nonlocal call_count
            call_count += 1
            return ComponentHealth(
                name="counter",
                status=HealthStatus.HEALTHY,
                message=f"Call {call_count}"
            )
        
        checker.register_component("counter", counting_check)
        
        # Start monitoring
        await checker.start_monitoring()
        
        # Wait for a few checks
        await asyncio.sleep(0.35)
        
        # Stop monitoring
        await checker.stop_monitoring()
        
        # Should have been called multiple times
        assert call_count >= 3
        
        # No more calls after stopping
        final_count = call_count
        await asyncio.sleep(0.2)
        assert call_count == final_count


class TestReadinessChecker:
    @pytest.mark.asyncio
    async def test_register_check(self):
        """Test registering readiness checks"""
        checker = ReadinessChecker()
        
        async def db_check():
            return True
        
        checker.register_check("database", db_check, required=True)
        
        assert "database" in checker.checks
        assert "database" in checker.required_components
    
    @pytest.mark.asyncio
    async def test_all_checks_pass(self):
        """Test when all readiness checks pass"""
        checker = ReadinessChecker()
        
        async def passing_check():
            return True
        
        checker.register_check("service1", passing_check, required=True)
        checker.register_check("service2", passing_check, required=False)
        
        result = await checker.is_ready()
        
        assert result["ready"] is True
        assert result["checks"]["service1"]["ready"] is True
        assert result["checks"]["service2"]["ready"] is True
    
    @pytest.mark.asyncio
    async def test_required_check_fails(self):
        """Test when a required check fails"""
        checker = ReadinessChecker()
        
        async def passing_check():
            return True
        
        async def failing_check():
            return False
        
        checker.register_check("service1", failing_check, required=True)
        checker.register_check("service2", passing_check, required=False)
        
        result = await checker.is_ready()
        
        assert result["ready"] is False
        assert result["checks"]["service1"]["ready"] is False
        assert result["checks"]["service2"]["ready"] is True
    
    @pytest.mark.asyncio
    async def test_optional_check_fails(self):
        """Test when only optional check fails"""
        checker = ReadinessChecker()
        
        async def passing_check():
            return True
        
        async def failing_check():
            return False
        
        checker.register_check("service1", passing_check, required=True)
        checker.register_check("service2", failing_check, required=False)
        
        result = await checker.is_ready()
        
        # Should still be ready if only optional check fails
        assert result["ready"] is True
        assert result["checks"]["service1"]["ready"] is True
        assert result["checks"]["service2"]["ready"] is False
    
    @pytest.mark.asyncio
    async def test_check_exception_handling(self):
        """Test exception handling in readiness checks"""
        checker = ReadinessChecker()
        
        async def error_check():
            raise ValueError("Check failed")
        
        checker.register_check("error_service", error_check, required=True)
        
        result = await checker.is_ready()
        
        assert result["ready"] is False
        assert result["checks"]["error_service"]["ready"] is False
        assert "error" in result["checks"]["error_service"]
        assert "Check failed" in result["checks"]["error_service"]["error"]
