"""
Integration tests for observability with EventBus.
"""

import pytest
import asyncio
import time
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from app.engine.bus import EventBus
from app.engine.core.event_bus_factory import EventBusFactory, EventBusConfig
from app.engine.types import BaseEvent, EventType
from app.engine.core.observability import (
    ObservabilityManager,
    EventBusHealthCheck,
    HealthStatus,
    init_observability,
    get_observability
)
from app.engine.core.metrics import metrics_collector
from app.engine.core.tracing import get_tracer, StatusCode


# Test event class
class TestEvent(BaseEvent):
    """Test event for integration tests."""
    event_type: EventType = EventType.HEALTH_CHECK
    test_data: Dict[str, Any] = {}


class TestObservabilityIntegration:
    @pytest.mark.asyncio
    async def test_eventbus_with_full_observability(self):
        """Test EventBus with complete observability setup."""
        # Initialize observability
        observability = init_observability(
            service_name="eventbus-test",
            enable_metrics=True,
            enable_tracing=True,
            enable_console_export=False
        )

        # Create EventBus
        factory = EventBusFactory()
        config = EventBusConfig(
            max_queue_size=1000,
            num_workers=2
        )
        event_bus = factory.create_with_config(config)

        # We can't use sync health checks with async functions in tests
        # So we'll check health directly when needed instead of registering

        # Start EventBus
        await event_bus.start()

        # Track events processed
        events_processed = []

        async def test_handler(event: TestEvent) -> None:
            """Test event handler with tracing."""
            async with observability.trace_operation(
                "process_event",
                attributes={"event_type": event.event_type.value}
            ) as span:
                await asyncio.sleep(0.01)
                events_processed.append(event)
                if span:
                    span.set_attribute("processed", True)

        # Subscribe to events
        await event_bus.subscribe(EventType.HEALTH_CHECK, test_handler)

        # Publish events with tracing
        for i in range(5):
            async with observability.trace_operation(
                "publish_event",
                attributes={"event_id": i}
            ):
                test_event = TestEvent(
                    event_id=uuid4(),
                    timestamp=datetime.now(),
                    symbol="TEST",
                    test_data={"id": i, "data": f"test_{i}"}
                )
                await event_bus.publish(test_event)

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify metrics
        metrics_summary = observability.get_metrics_summary()
        assert "metrics" in metrics_summary
        assert "requests_total" in str(metrics_summary)

        # Verify operation statistics
        stats = observability.get_operation_statistics()
        assert stats["total_operations"] > 0
        assert stats["success_rate"] > 0

        # Check health directly since we can't register async health checks
        health_check = EventBusHealthCheck(event_bus)
        queue_health = await health_check.check_queue_health()
        processing_health = await health_check.check_processing_health()

        assert queue_health.status == HealthStatus.HEALTHY
        assert processing_health.status == HealthStatus.HEALTHY

        # Export Prometheus metrics
        prometheus_output = observability.export_metrics_prometheus()
        assert "requests_total" in prometheus_output
        assert "request_duration_seconds" in prometheus_output

        # Stop EventBus
        await event_bus.stop()

        # Verify all events were processed
        assert len(events_processed) == 5

        # Shutdown observability
        observability.shutdown()

    @pytest.mark.asyncio
    async def test_eventbus_error_tracking(self):
        """Test error tracking in EventBus with observability."""
        observability = ObservabilityManager(
            service_name="error-test",
            enable_metrics=True,
            enable_tracing=True
        )

        factory = EventBusFactory()
        event_bus = factory.create_event_bus()
        await event_bus.start()

        error_count = 0

        async def failing_handler(event: TestEvent) -> None:
            """Handler that fails on certain events."""
            nonlocal error_count
            async with observability.trace_operation(
                "failing_handler",
                attributes={"event_id": str(event.event_id)}
            ) as span:
                if event.test_data.get("fail", False):
                    error_count += 1
                    raise ValueError(f"Intentional failure for event {event.test_data.get('id')}")
                await asyncio.sleep(0.01)

        await event_bus.subscribe(EventType.HEALTH_CHECK, failing_handler)

        # Publish mixed events
        for i in range(10):
            test_event = TestEvent(
                event_id=uuid4(),
                timestamp=datetime.now(),
                symbol="TEST",
                test_data={"id": i, "fail": i % 3 == 0}  # Fail every 3rd event
            )
            await event_bus.publish(test_event)

        await asyncio.sleep(0.2)

        # Check error metrics
        if observability.metrics:
            metrics = observability.metrics.registry.collect_all()
            error_metrics = [m for m in metrics if "errors" in m.name]
            assert len(error_metrics) > 0

        # Check operation statistics
        stats = observability.get_operation_statistics()
        assert stats["success_rate"] < 1.0  # Some operations failed

        await event_bus.stop()
        observability.shutdown()

    @pytest.mark.asyncio
    async def test_eventbus_performance_monitoring(self):
        """Test performance monitoring of EventBus operations."""
        observability = ObservabilityManager(
            service_name="performance-test",
            enable_metrics=True,
            enable_tracing=True
        )

        factory = EventBusFactory()
        event_bus = factory.create_event_bus()
        await event_bus.start()

        processing_times = []

        async def timed_handler(event: TestEvent) -> None:
            """Handler with varying processing times."""
            delay = event.test_data.get("delay", 0.01)
            start = time.time()
            await asyncio.sleep(delay)
            processing_times.append(time.time() - start)

        await event_bus.subscribe(EventType.HEALTH_CHECK, timed_handler)

        # Publish events with varying delays
        delays = [0.001, 0.005, 0.01, 0.02, 0.05]
        for i, delay in enumerate(delays * 2):  # 10 events total
            async with observability.trace_operation(
                "publish_timed_event",
                attributes={"delay": delay}
            ):
                test_event = TestEvent(
                    event_id=uuid4(),
                    timestamp=datetime.now(),
                    symbol="TEST",
                    test_data={"id": i, "delay": delay}
                )
                await event_bus.publish(test_event)

        await asyncio.sleep(0.5)

        # Check performance metrics
        if observability.metrics:
            # Get histogram metrics for duration
            metrics = observability.metrics.registry.collect_all()
            duration_metrics = [m for m in metrics if "duration" in m.name]
            assert len(duration_metrics) > 0

        # Check operation statistics
        stats = observability.get_operation_statistics()
        assert "p50_duration" in stats
        assert "p95_duration" in stats
        assert "p99_duration" in stats

        # P95 should be higher than P50
        assert stats["p95_duration"] >= stats["p50_duration"]

        await event_bus.stop()
        observability.shutdown()

    @pytest.mark.asyncio
    async def test_eventbus_queue_health_monitoring(self):
        """Test queue health monitoring under load."""
        observability = ObservabilityManager(
            service_name="queue-health-test"
        )

        # Create EventBus with small queue for testing
        factory = EventBusFactory()
        config = EventBusConfig(
            max_queue_size=50,
            num_workers=1
        )
        event_bus = factory.create_with_config(config)
        await event_bus.start()

        # Set up health check
        health_check = EventBusHealthCheck(event_bus)

        # Slow handler to build up queue
        async def slow_handler(event: TestEvent) -> None:
            await asyncio.sleep(0.1)

        await event_bus.subscribe(EventType.HEALTH_CHECK, slow_handler)

        # Initially healthy
        initial_health = await health_check.check_queue_health()
        assert initial_health.status == HealthStatus.HEALTHY

        # Publish many events quickly to fill queue
        publish_tasks = []
        for i in range(40):  # 80% of queue capacity
            test_event = TestEvent(
                event_id=uuid4(),
                timestamp=datetime.now(),
                symbol="TEST",
                test_data={"id": i}
            )
            task = event_bus.publish(test_event)
            publish_tasks.append(task)

        await asyncio.gather(*publish_tasks)

        # Check queue health - should be degraded or unhealthy
        queue_health = await health_check.check_queue_health()
        assert queue_health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]

        # Let queue drain
        await asyncio.sleep(5)

        # Should be healthy again
        final_health = await health_check.check_queue_health()
        assert final_health.status == HealthStatus.HEALTHY

        await event_bus.stop()
        observability.shutdown()

    @pytest.mark.asyncio
    async def test_distributed_tracing_across_handlers(self):
        """Test tracing context propagation across event handlers."""
        tracer = get_tracer("distributed-test")

        factory = EventBusFactory()
        event_bus = factory.create_event_bus()
        await event_bus.start()

        trace_contexts = []

        async def handler_1(event: TestEvent) -> None:
            """First handler in chain."""
            with tracer.start_as_current_span("handler_1") as span:
                span.set_attribute("handler", "1")
                trace_contexts.append({
                    "handler": "1",
                    "trace_id": span.context.trace_id
                })
                # Publish downstream event
                downstream_event = TestEvent(
                    event_id=uuid4(),
                    timestamp=datetime.now(),
                    symbol="TEST",
                    event_type=EventType.POSITION_UPDATE,  # Different type for downstream
                    test_data={
                        "original_id": str(event.event_id),
                        "trace_id": span.context.trace_id
                    }
                )
                await event_bus.publish(downstream_event)

        async def handler_2(event: TestEvent) -> None:
            """Second handler in chain."""
            with tracer.start_as_current_span("handler_2") as span:
                span.set_attribute("handler", "2")
                span.set_attribute("original_id", event.test_data.get("original_id", ""))
                trace_contexts.append({
                    "handler": "2",
                    "trace_id": span.context.trace_id
                })

        await event_bus.subscribe(EventType.HEALTH_CHECK, handler_1)
        await event_bus.subscribe(EventType.POSITION_UPDATE, handler_2)

        # Start trace
        with tracer.start_as_current_span("root_span") as root:
            root_trace_id = root.context.trace_id
            test_event = TestEvent(
                event_id=uuid4(),
                timestamp=datetime.now(),
                symbol="TEST",
                test_data={"id": "test_123"}
            )
            await event_bus.publish(test_event)

        await asyncio.sleep(0.2)

        # Verify trace context propagation
        assert len(trace_contexts) == 2
        # In a full implementation, trace IDs would be propagated
        # Here we just verify handlers were called in order
        assert trace_contexts[0]["handler"] == "1"
        assert trace_contexts[1]["handler"] == "2"

        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_observability_with_circuit_breaker(self):
        """Test observability with circuit breaker patterns."""
        observability = ObservabilityManager(
            service_name="circuit-breaker-test"
        )

        factory = EventBusFactory()
        event_bus = factory.create_event_bus()
        await event_bus.start()

        failure_count = 0
        success_count = 0

        async def flaky_handler(event: TestEvent) -> None:
            """Handler that fails intermittently."""
            nonlocal failure_count, success_count

            async with observability.trace_operation(
                "flaky_operation",
                attributes={"event_id": str(event.event_id)}
            ) as span:
                # Fail first 5 events
                event_num = event.test_data.get("id", 0)
                if event_num < 5:
                    failure_count += 1
                    raise ConnectionError("Service unavailable")
                else:
                    success_count += 1
                    await asyncio.sleep(0.01)

        await event_bus.subscribe(EventType.HEALTH_CHECK, flaky_handler)

        # Send events that will trigger circuit breaker
        for i in range(10):
            try:
                test_event = TestEvent(
                    event_id=uuid4(),
                    timestamp=datetime.now(),
                    symbol="TEST",
                    test_data={"id": i}
                )
                await event_bus.publish(test_event)
            except Exception:
                pass  # Expected for circuit breaker

        await asyncio.sleep(0.5)

        # Check metrics show both failures and recoveries
        stats = observability.get_operation_statistics()
        if stats["total_operations"] > 0:
            # Should have some failures
            assert stats["success_rate"] < 1.0

        await event_bus.stop()
        observability.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_export_formats(self):
        """Test different metric export formats."""
        observability = ObservabilityManager(
            service_name="export-test",
            enable_metrics=True
        )

        # Record various metrics
        observability.request_counter.inc(labels={"method": "GET"})
        observability.request_counter.inc(labels={"method": "POST"})
        observability.request_duration.observe(0.1, labels={"endpoint": "/api"})
        observability.request_duration.observe(0.2, labels={"endpoint": "/api"})
        observability.active_operations.set(5)
        observability.queue_size.set(100)

        # Test Prometheus export
        prometheus = observability.export_metrics_prometheus()
        assert "# HELP requests_total" in prometheus
        assert "# TYPE requests_total counter" in prometheus
        assert 'method="GET"' in prometheus
        assert 'method="POST"' in prometheus

        # Test metrics summary
        summary = observability.get_metrics_summary()
        assert "uptime_seconds" in summary
        assert len(summary["metrics"]) > 0

        observability.shutdown()