"""
Unit tests for observability manager.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch

from app.engine.core.observability import (
    HealthStatus,
    HealthCheck,
    HealthReport,
    ObservabilityManager,
    EventBusHealthCheck,
    init_observability,
    get_observability,
)


class TestHealthCheck:
    def test_health_check_creation(self):
        check = HealthCheck(
            name="test_check",
            status=HealthStatus.HEALTHY,
            message="All good",
            details={"key": "value"},
        )

        assert check.name == "test_check"
        assert check.status == HealthStatus.HEALTHY
        assert check.message == "All good"
        assert check.details["key"] == "value"
        assert check.timestamp > 0


class TestHealthReport:
    def test_health_report_creation(self):
        checks = [
            HealthCheck("check1", HealthStatus.HEALTHY),
            HealthCheck("check2", HealthStatus.DEGRADED),
        ]

        report = HealthReport(status=HealthStatus.DEGRADED, checks=checks)

        assert report.status == HealthStatus.DEGRADED
        assert len(report.checks) == 2

    def test_health_report_to_dict(self):
        checks = [HealthCheck("check1", HealthStatus.HEALTHY, "OK", {"metric": 100})]

        report = HealthReport(HealthStatus.HEALTHY, checks)
        report_dict = report.to_dict()

        assert report_dict["status"] == "healthy"
        assert len(report_dict["checks"]) == 1
        assert report_dict["checks"][0]["name"] == "check1"
        assert report_dict["checks"][0]["details"]["metric"] == 100


class TestObservabilityManager:
    def test_initialization_with_metrics_and_tracing(self):
        manager = ObservabilityManager(
            service_name="test-service", enable_metrics=True, enable_tracing=True
        )

        assert manager.service_name == "test-service"
        assert manager.metrics is not None
        assert manager.tracer is not None

        # Check default metrics exist
        assert hasattr(manager, "request_counter")
        assert hasattr(manager, "request_duration")
        assert hasattr(manager, "request_errors")

    def test_initialization_without_metrics(self):
        manager = ObservabilityManager(enable_metrics=False, enable_tracing=True)

        assert manager.metrics is None
        assert manager.tracer is not None

    def test_initialization_without_tracing(self):
        manager = ObservabilityManager(enable_metrics=True, enable_tracing=False)

        assert manager.metrics is not None
        assert manager.tracer is None

    def test_register_health_check(self):
        manager = ObservabilityManager()

        def test_check():
            return HealthCheck("test", HealthStatus.HEALTHY)

        manager.register_health_check("test", test_check)

        assert "test" in manager._health_checks

    def test_health_report_generation(self):
        manager = ObservabilityManager()

        # Register checks
        manager.register_health_check(
            "check1", lambda: HealthCheck("check1", HealthStatus.HEALTHY)
        )
        manager.register_health_check(
            "check2", lambda: HealthCheck("check2", HealthStatus.DEGRADED)
        )

        report = manager.get_health_report()

        assert report.status == HealthStatus.DEGRADED
        assert len(report.checks) == 2

    def test_health_check_exception_handling(self):
        manager = ObservabilityManager()

        def failing_check():
            raise ValueError("Check failed")

        manager.register_health_check("failing", failing_check)
        report = manager.get_health_report()

        failing_check_result = next(
            (c for c in report.checks if c.name == "failing"), None
        )

        assert failing_check_result is not None
        assert failing_check_result.status == HealthStatus.UNHEALTHY
        assert "failed" in failing_check_result.message.lower()

    @pytest.mark.asyncio
    async def test_trace_operation_with_metrics(self):
        manager = ObservabilityManager(enable_metrics=True, enable_tracing=True)

        async with manager.trace_operation(
            "test_op", attributes={"key": "value"}
        ) as span:
            await asyncio.sleep(0.01)

        # Check metrics were recorded
        metrics = manager.metrics.registry.collect_all()
        counter_metrics = [m for m in metrics if "requests_total" in m.name]
        assert len(counter_metrics) > 0

        # Check operation history
        stats = manager.get_operation_statistics()
        assert stats["total_operations"] > 0

    @pytest.mark.asyncio
    async def test_trace_operation_with_error(self):
        manager = ObservabilityManager()

        with pytest.raises(ValueError):
            async with manager.trace_operation("failing_op"):
                raise ValueError("Test error")

        # Check error metrics
        if manager.metrics:
            metrics = manager.metrics.registry.collect_all()
            error_metrics = [m for m in metrics if "errors" in m.name]
            assert len(error_metrics) > 0

    @pytest.mark.asyncio
    async def test_trace_operation_without_tracing(self):
        manager = ObservabilityManager(enable_metrics=True, enable_tracing=False)

        async with manager.trace_operation("test_op") as span:
            assert span is None
            await asyncio.sleep(0.01)

        # Metrics should still be recorded
        metrics = manager.metrics.registry.collect_all()
        assert len(metrics) > 0

    def test_update_queue_metrics(self):
        manager = ObservabilityManager()

        manager.update_queue_metrics(queue_size=100, processing_lag=0.5)

        if manager.metrics:
            metrics = manager.metrics.registry.collect_all()
            queue_metrics = [m for m in metrics if "queue_size" in m.name]
            assert len(queue_metrics) > 0
            assert queue_metrics[0].value == 100

    def test_record_event(self):
        manager = ObservabilityManager(enable_tracing=True)

        # Create a span context
        with manager.tracer.start_as_current_span("test") as span:
            manager.record_event("test_event", {"detail": "value"})

            assert len(span.events) == 1
            assert span.events[0].name == "test_event"

    def test_get_metrics_summary(self):
        manager = ObservabilityManager(enable_metrics=True)

        # Record some metrics
        manager.request_counter.inc()

        summary = manager.get_metrics_summary()

        assert "uptime_seconds" in summary
        assert "metrics" in summary
        assert len(summary["metrics"]) > 0

    def test_get_operation_statistics(self):
        manager = ObservabilityManager()

        # Add some operations to history
        manager._operation_history.append(
            {
                "operation": "op1",
                "duration": 0.1,
                "timestamp": time.time(),
                "success": True,
            }
        )
        manager._operation_history.append(
            {
                "operation": "op2",
                "duration": 0.2,
                "timestamp": time.time(),
                "success": False,
            }
        )

        stats = manager.get_operation_statistics()

        assert stats["total_operations"] == 2
        assert stats["success_rate"] == 0.5
        assert (
            abs(stats["average_duration"] - 0.15) < 0.0001
        )  # Use approximate comparison
        assert "p50_duration" in stats
        assert "p95_duration" in stats

    def test_operation_statistics_empty(self):
        manager = ObservabilityManager()

        stats = manager.get_operation_statistics()

        assert stats["total_operations"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["average_duration"] == 0.0

    def test_export_metrics_prometheus(self):
        manager = ObservabilityManager(enable_metrics=True)

        # Record a metric
        manager.request_counter.inc(labels={"method": "GET"})

        prometheus_output = manager.export_metrics_prometheus()

        assert "requests_total" in prometheus_output
        assert "GET" in prometheus_output

    def test_export_metrics_disabled(self):
        manager = ObservabilityManager(enable_metrics=False)

        prometheus_output = manager.export_metrics_prometheus()

        assert prometheus_output == ""

    def test_health_check_background_loop(self):
        manager = ObservabilityManager()

        check_called = False

        def test_check():
            nonlocal check_called
            check_called = True
            return HealthCheck("test", HealthStatus.HEALTHY)

        manager.register_health_check("test", test_check)
        manager.start_health_checks(interval=0.1)

        time.sleep(0.2)
        manager.stop_health_checks()

        assert check_called

    def test_shutdown(self):
        manager = ObservabilityManager(
            enable_metrics=True, enable_tracing=True, enable_console_export=True
        )

        manager.start_health_checks()
        manager.shutdown()

        assert manager._shutdown is True


class TestEventBusHealthCheck:
    @pytest.mark.asyncio
    async def test_check_queue_health_healthy(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"queue_size": 100, "max_queue_size": 10000}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_queue_health()

        assert check.status == HealthStatus.HEALTHY
        assert "healthy" in check.message.lower()

    @pytest.mark.asyncio
    async def test_check_queue_health_degraded(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"queue_size": 7500, "max_queue_size": 10000}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_queue_health()

        assert check.status == HealthStatus.DEGRADED
        assert "filling" in check.message.lower()

    @pytest.mark.asyncio
    async def test_check_queue_health_unhealthy(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"queue_size": 9500, "max_queue_size": 10000}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_queue_health()

        assert check.status == HealthStatus.UNHEALTHY
        assert "critical" in check.message.lower()

    @pytest.mark.asyncio
    async def test_check_processing_health_healthy(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"error_rate": 0.01, "is_running": True}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_processing_health()

        assert check.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_check_processing_health_not_running(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"error_rate": 0.0, "is_running": False}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_processing_health()

        assert check.status == HealthStatus.UNHEALTHY
        assert "not running" in check.message.lower()

    @pytest.mark.asyncio
    async def test_check_processing_health_high_errors(self):
        mock_event_bus = AsyncMock()
        mock_event_bus.get_metrics = AsyncMock(
            return_value={"error_rate": 0.6, "is_running": True}
        )

        checker = EventBusHealthCheck(mock_event_bus)
        check = await checker.check_processing_health()

        assert check.status == HealthStatus.UNHEALTHY
        assert "high error rate" in check.message.lower()


class TestGlobalObservability:
    def test_init_observability(self):
        manager = init_observability(
            service_name="test-global", enable_metrics=True, enable_tracing=True
        )

        assert manager is not None
        assert manager.service_name == "test-global"
        assert get_observability() is manager

    def test_get_observability_none(self):
        # Reset global
        import app.engine.core.observability

        app.engine.core.observability._observability_manager = None

        assert get_observability() is None
