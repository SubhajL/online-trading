"""
Observability manager integrating metrics, tracing, and health checks.

Provides unified observability for the EventBus system.
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union
import threading
from collections import deque

from app.engine.core.metrics import MetricsCollector, Counter, Gauge, Histogram
from app.engine.core.tracing import (
    Tracer,
    TracerProvider,
    SpanKind,
    StatusCode,
    get_tracer,
    BatchSpanProcessor,
    ConsoleSpanExporter,
)


class HealthStatus(Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Health check result."""

    name: str
    status: HealthStatus
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class HealthReport:
    """Overall health report."""

    status: HealthStatus
    checks: List[HealthCheck]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                }
                for check in self.checks
            ],
        }


class ObservabilityManager:
    """
    Manages metrics, tracing, and health checks for the system.
    """

    def __init__(
        self,
        service_name: str = "event-bus",
        enable_metrics: bool = True,
        enable_tracing: bool = True,
        enable_console_export: bool = False,
    ):
        self.service_name = service_name
        self.enable_metrics = enable_metrics
        self.enable_tracing = enable_tracing

        # Initialize metrics
        if enable_metrics:
            self.metrics = MetricsCollector()
            self._setup_default_metrics()
        else:
            self.metrics = None

        # Initialize tracing
        if enable_tracing:
            self.tracer_provider = TracerProvider(
                resource={"service.name": service_name}
            )
            if enable_console_export:
                self.tracer_provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
            self.tracer = self.tracer_provider.get_tracer(service_name)
        else:
            self.tracer = None

        # Health checks
        self._health_checks: Dict[str, Callable[[], HealthCheck]] = {}
        self._health_check_results: Dict[str, HealthCheck] = {}
        self._health_check_interval = 30  # seconds
        self._health_check_lock = threading.RLock()
        self._health_check_thread: Optional[threading.Thread] = None
        self._shutdown = False

        # Performance tracking
        self._operation_history: deque = deque(maxlen=1000)
        self._start_time = time.time()

        # Logger
        self.logger = logging.getLogger(f"{service_name}.observability")

    def _setup_default_metrics(self) -> None:
        """Set up default metrics."""
        # Request metrics
        self.request_counter = self.metrics.counter(
            "requests_total", "Total number of requests"
        )
        self.request_duration = self.metrics.histogram(
            "request_duration_seconds",
            "Request duration in seconds",
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5],
            unit="seconds",
        )
        self.request_errors = self.metrics.counter(
            "request_errors_total", "Total number of request errors"
        )

        # System metrics
        self.active_operations = self.metrics.gauge(
            "active_operations", "Number of active operations"
        )
        self.queue_size = self.metrics.gauge("queue_size", "Current queue size")
        self.processing_lag = self.metrics.gauge(
            "processing_lag_seconds", "Processing lag in seconds", unit="seconds"
        )

    def start_health_checks(self, interval: int = 30) -> None:
        """Start background health check monitoring."""
        self._health_check_interval = interval
        self._shutdown = False
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop, daemon=True
        )
        self._health_check_thread.start()

    def stop_health_checks(self) -> None:
        """Stop health check monitoring."""
        self._shutdown = True
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5)

    def _health_check_loop(self) -> None:
        """Background loop for health checks."""
        while not self._shutdown:
            self._run_health_checks()
            time.sleep(self._health_check_interval)

    def _run_health_checks(self) -> None:
        """Run all registered health checks."""
        with self._health_check_lock:
            for name, check_func in self._health_checks.items():
                try:
                    result = check_func()
                    self._health_check_results[name] = result
                except Exception as e:
                    self._health_check_results[name] = HealthCheck(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check failed: {str(e)}",
                    )

    def register_health_check(
        self, name: str, check_func: Callable[[], HealthCheck]
    ) -> None:
        """Register a health check function."""
        with self._health_check_lock:
            self._health_checks[name] = check_func

    def get_health_report(self) -> HealthReport:
        """Get current health report."""
        with self._health_check_lock:
            # Run checks if not done recently
            if not self._health_check_results:
                self._run_health_checks()

            checks = list(self._health_check_results.values())

            # Determine overall status
            if any(c.status == HealthStatus.UNHEALTHY for c in checks):
                overall_status = HealthStatus.UNHEALTHY
            elif any(c.status == HealthStatus.DEGRADED for c in checks):
                overall_status = HealthStatus.DEGRADED
            else:
                overall_status = HealthStatus.HEALTHY

            return HealthReport(status=overall_status, checks=checks)

    @asynccontextmanager
    async def trace_operation(
        self,
        operation_name: str,
        attributes: Optional[Dict[str, Any]] = None,
        record_metrics: bool = True,
    ):
        """
        Trace an async operation with metrics.

        Args:
            operation_name: Name of the operation
            attributes: Span attributes
            record_metrics: Whether to record metrics
        """
        start_time = time.time()

        # Start tracing
        if self.tracer:
            async with self.tracer.start_as_current_span_async(
                operation_name, kind=SpanKind.INTERNAL, attributes=attributes
            ) as span:
                # Record metrics
                if record_metrics and self.metrics:
                    self.active_operations.inc()
                    self.request_counter.inc(labels={"operation": operation_name})

                try:
                    yield span

                    # Mark success
                    if span:
                        span.set_status(StatusCode.OK)

                except Exception as e:
                    # Record error
                    if span:
                        span.record_exception(e)

                    if record_metrics and self.metrics:
                        self.request_errors.inc(
                            labels={
                                "operation": operation_name,
                                "error_type": type(e).__name__,
                            }
                        )

                    raise

                finally:
                    # Record duration
                    duration = time.time() - start_time

                    if record_metrics and self.metrics:
                        self.request_duration.observe(
                            duration, labels={"operation": operation_name}
                        )
                        self.active_operations.dec()

                    # Store in history
                    self._operation_history.append(
                        {
                            "operation": operation_name,
                            "duration": duration,
                            "timestamp": start_time,
                            "success": (
                                span.status.code == StatusCode.OK if span else True
                            ),
                        }
                    )
        else:
            # No tracing, just metrics
            if record_metrics and self.metrics:
                self.active_operations.inc()
                self.request_counter.inc(labels={"operation": operation_name})

            try:
                yield None
            except Exception as e:
                if record_metrics and self.metrics:
                    self.request_errors.inc(
                        labels={
                            "operation": operation_name,
                            "error_type": type(e).__name__,
                        }
                    )
                raise
            finally:
                duration = time.time() - start_time

                if record_metrics and self.metrics:
                    self.request_duration.observe(
                        duration, labels={"operation": operation_name}
                    )
                    self.active_operations.dec()

    def record_event(
        self, event_name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a significant event."""
        if self.tracer:
            current_span = self.tracer.get_current_span()
            if current_span:
                current_span.add_event(event_name, attributes)

    def update_queue_metrics(
        self, queue_size: int, processing_lag: Optional[float] = None
    ) -> None:
        """Update queue-related metrics."""
        if self.metrics:
            self.queue_size.set(float(queue_size))
            if processing_lag is not None:
                self.processing_lag.set(processing_lag)

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of current metrics."""
        if not self.metrics:
            return {}

        metrics = self.metrics.registry.collect_all()
        summary = {"uptime_seconds": time.time() - self._start_time, "metrics": {}}

        for metric in metrics:
            if metric.name not in summary["metrics"]:
                summary["metrics"][metric.name] = []

            summary["metrics"][metric.name].append(
                {
                    "labels": metric.labels,
                    "value": metric.value,
                    "type": metric.type.value,
                }
            )

        return summary

    def get_operation_statistics(self) -> Dict[str, Any]:
        """Get statistics about recent operations."""
        if not self._operation_history:
            return {"total_operations": 0, "success_rate": 0.0, "average_duration": 0.0}

        operations = list(self._operation_history)
        total = len(operations)
        successful = sum(1 for op in operations if op.get("success", True))
        durations = [op["duration"] for op in operations]

        return {
            "total_operations": total,
            "success_rate": successful / total if total > 0 else 0.0,
            "average_duration": sum(durations) / len(durations) if durations else 0.0,
            "p50_duration": self._percentile(durations, 50),
            "p95_duration": self._percentile(durations, 95),
            "p99_duration": self._percentile(durations, 99),
        }

    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile of values."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100))
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def export_metrics_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        if self.metrics:
            return self.metrics.export_prometheus()
        return ""

    def shutdown(self) -> None:
        """Shutdown observability manager."""
        self.stop_health_checks()

        if self.tracer_provider:
            for processor in self.tracer_provider._processors:
                processor.shutdown()


class EventBusHealthCheck:
    """Health checks specific to EventBus."""

    def __init__(self, event_bus: Any):
        self.event_bus = event_bus

    async def check_queue_health(self) -> HealthCheck:
        """Check EventBus queue health."""
        try:
            metrics = await self.event_bus.get_metrics()
            queue_size = metrics.get("queue_size", 0)
            max_queue_size = metrics.get("queue_max_size", 10000)  # Fixed key name

            utilization = queue_size / max_queue_size if max_queue_size > 0 else 0

            if utilization > 0.9:
                return HealthCheck(
                    name="queue_health",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Queue critically full: {utilization:.1%}",
                    details={"queue_size": queue_size, "max_size": max_queue_size},
                )
            elif utilization > 0.7:
                return HealthCheck(
                    name="queue_health",
                    status=HealthStatus.DEGRADED,
                    message=f"Queue filling up: {utilization:.1%}",
                    details={"queue_size": queue_size, "max_size": max_queue_size},
                )
            else:
                return HealthCheck(
                    name="queue_health",
                    status=HealthStatus.HEALTHY,
                    message=f"Queue healthy: {utilization:.1%}",
                    details={"queue_size": queue_size, "max_size": max_queue_size},
                )

        except Exception as e:
            return HealthCheck(
                name="queue_health",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check queue: {str(e)}",
            )

    async def check_processing_health(self) -> HealthCheck:
        """Check event processing health."""
        try:
            metrics = await self.event_bus.get_metrics()

            error_rate = metrics.get("error_rate", 0)
            is_running = metrics.get("is_running", False)

            if not is_running:
                return HealthCheck(
                    name="processing_health",
                    status=HealthStatus.UNHEALTHY,
                    message="EventBus is not running",
                )

            if error_rate > 0.5:
                return HealthCheck(
                    name="processing_health",
                    status=HealthStatus.UNHEALTHY,
                    message=f"High error rate: {error_rate:.1%}",
                    details={"error_rate": error_rate},
                )
            elif error_rate > 0.1:
                return HealthCheck(
                    name="processing_health",
                    status=HealthStatus.DEGRADED,
                    message=f"Elevated error rate: {error_rate:.1%}",
                    details={"error_rate": error_rate},
                )
            else:
                return HealthCheck(
                    name="processing_health",
                    status=HealthStatus.HEALTHY,
                    message="Processing healthy",
                    details={"error_rate": error_rate},
                )

        except Exception as e:
            return HealthCheck(
                name="processing_health",
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to check processing: {str(e)}",
            )


# Global observability instance
_observability_manager: Optional[ObservabilityManager] = None


def init_observability(
    service_name: str = "event-bus",
    enable_metrics: bool = True,
    enable_tracing: bool = True,
    enable_console_export: bool = False,
) -> ObservabilityManager:
    """Initialize global observability manager."""
    global _observability_manager
    _observability_manager = ObservabilityManager(
        service_name=service_name,
        enable_metrics=enable_metrics,
        enable_tracing=enable_tracing,
        enable_console_export=enable_console_export,
    )
    return _observability_manager


def get_observability() -> Optional[ObservabilityManager]:
    """Get global observability manager."""
    return _observability_manager
