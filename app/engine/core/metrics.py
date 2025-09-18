"""
Metrics collection framework for EventBus observability.

Provides thread-safe metrics collection with Prometheus export support.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import threading
from contextlib import contextmanager


class MetricType(Enum):
    """Types of metrics supported."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class Metric:
    """Base metric with metadata."""
    name: str
    type: MetricType
    description: str
    labels: Dict[str, str] = field(default_factory=dict)
    value: float = 0.0
    timestamp: float = field(default_factory=time.time)
    unit: Optional[str] = None

    def __hash__(self):
        """Make metric hashable based on name and labels."""
        return hash((self.name, tuple(sorted(self.labels.items()))))


class Counter:
    """A counter metric that can only increase."""

    def __init__(self, name: str, description: str, unit: Optional[str] = None):
        self.name = name
        self.description = description
        self.unit = unit
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment the counter."""
        if amount < 0:
            raise ValueError("Counter can only increase")

        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[label_key] += amount

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current value for given labels."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self._values[label_key]

    def collect(self) -> List[Metric]:
        """Collect all metrics for export."""
        metrics = []
        with self._lock:
            for label_tuple, value in self._values.items():
                labels = dict(label_tuple)
                metrics.append(Metric(
                    name=self.name,
                    type=MetricType.COUNTER,
                    description=self.description,
                    labels=labels,
                    value=value,
                    unit=self.unit
                ))
        return metrics


class Gauge:
    """A gauge metric that can go up or down."""

    def __init__(self, name: str, description: str, unit: Optional[str] = None):
        self.name = name
        self.description = description
        self.unit = unit
        self._values: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set the gauge value."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[label_key] = value

    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment the gauge."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[label_key] += amount

    def dec(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Decrement the gauge."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._values[label_key] -= amount

    def get(self, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current value for given labels."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self._values[label_key]

    def collect(self) -> List[Metric]:
        """Collect all metrics for export."""
        metrics = []
        with self._lock:
            for label_tuple, value in self._values.items():
                labels = dict(label_tuple)
                metrics.append(Metric(
                    name=self.name,
                    type=MetricType.GAUGE,
                    description=self.description,
                    labels=labels,
                    value=value,
                    unit=self.unit
                ))
        return metrics


class Histogram:
    """A histogram metric with configurable buckets."""

    def __init__(
        self,
        name: str,
        description: str,
        buckets: Optional[List[float]] = None,
        unit: Optional[str] = None
    ):
        self.name = name
        self.description = description
        self.unit = unit
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        self._buckets: Dict[Tuple[Tuple[str, str], ...], Dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets + [float('inf')]}
        )
        self._sums: Dict[Tuple[Tuple[str, str], ...], float] = defaultdict(float)
        self._counts: Dict[Tuple[Tuple[str, str], ...], int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record an observation."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._sums[label_key] += value
            self._counts[label_key] += 1

            # Update buckets (cumulative count)
            for bucket in self.buckets + [float('inf')]:
                if value <= bucket:
                    self._buckets[label_key][bucket] += 1

    def get_percentile(self, percentile: float, labels: Optional[Dict[str, str]] = None) -> float:
        """Get percentile value."""
        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100")

        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            count = self._counts[label_key]
            if count == 0:
                return 0.0

            target_count = count * (percentile / 100.0)

            # Buckets are already cumulative, so just check each bucket
            for bucket in sorted(self.buckets):
                if self._buckets[label_key][bucket] >= target_count:
                    return bucket

            return float('inf')

    def collect(self) -> List[Metric]:
        """Collect all metrics for export."""
        metrics = []
        with self._lock:
            for label_tuple in self._counts:
                labels = dict(label_tuple)

                # Add bucket metrics
                for bucket in self.buckets + [float('inf')]:
                    bucket_labels = labels.copy()
                    bucket_labels['le'] = str(bucket) if bucket != float('inf') else '+Inf'
                    metrics.append(Metric(
                        name=f"{self.name}_bucket",
                        type=MetricType.COUNTER,
                        description=f"{self.description} (bucket)",
                        labels=bucket_labels,
                        value=float(self._buckets[label_tuple][bucket]),
                        unit=self.unit
                    ))

                # Add sum and count
                metrics.append(Metric(
                    name=f"{self.name}_sum",
                    type=MetricType.COUNTER,
                    description=f"{self.description} (sum)",
                    labels=labels,
                    value=self._sums[label_tuple],
                    unit=self.unit
                ))

                metrics.append(Metric(
                    name=f"{self.name}_count",
                    type=MetricType.COUNTER,
                    description=f"{self.description} (count)",
                    labels=labels,
                    value=float(self._counts[label_tuple]),
                    unit=self.unit
                ))

        return metrics


class MetricsRegistry:
    """Global registry for all metrics."""

    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, metric: Any) -> None:
        """Register a metric."""
        with self._lock:
            if metric.name in self._metrics:
                raise ValueError(f"Metric {metric.name} already registered")
            self._metrics[metric.name] = metric

    def unregister(self, name: str) -> None:
        """Unregister a metric."""
        with self._lock:
            self._metrics.pop(name, None)

    def get(self, name: str) -> Optional[Any]:
        """Get a registered metric."""
        with self._lock:
            return self._metrics.get(name)

    def collect_all(self) -> List[Metric]:
        """Collect all registered metrics."""
        all_metrics = []
        with self._lock:
            for metric in self._metrics.values():
                if hasattr(metric, 'collect'):
                    all_metrics.extend(metric.collect())
        return all_metrics


class PrometheusExporter:
    """Exports metrics in Prometheus format."""

    def __init__(self, registry: MetricsRegistry):
        self.registry = registry

    def export(self) -> str:
        """Export metrics in Prometheus exposition format."""
        lines = []
        metrics = self.registry.collect_all()

        # Group metrics by name
        grouped = defaultdict(list)
        for metric in metrics:
            grouped[metric.name].append(metric)

        # Generate output
        for name, metric_list in grouped.items():
            if metric_list:
                first_metric = metric_list[0]

                # Add HELP line
                lines.append(f"# HELP {name} {first_metric.description}")

                # Add TYPE line
                metric_type = first_metric.type.value
                if name.endswith('_bucket') or name.endswith('_count') or name.endswith('_sum'):
                    metric_type = 'counter'
                lines.append(f"# TYPE {name} {metric_type}")

                # Add metric lines
                for metric in metric_list:
                    label_str = self._format_labels(metric.labels)
                    if label_str:
                        lines.append(f"{name}{{{label_str}}} {metric.value}")
                    else:
                        lines.append(f"{name} {metric.value}")

        return '\n'.join(lines) + '\n'

    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus."""
        if not labels:
            return ""

        label_pairs = []
        for key, value in sorted(labels.items()):
            # Escape special characters
            escaped_value = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            label_pairs.append(f'{key}="{escaped_value}"')

        return ','.join(label_pairs)


class MetricsCollector:
    """Collects and manages metrics."""

    def __init__(self):
        self.registry = MetricsRegistry()
        self.exporter = PrometheusExporter(self.registry)
        self._start_time = time.time()

    def counter(self, name: str, description: str, unit: Optional[str] = None) -> Counter:
        """Create and register a counter."""
        counter = Counter(name, description, unit)
        self.registry.register(counter)
        return counter

    def gauge(self, name: str, description: str, unit: Optional[str] = None) -> Gauge:
        """Create and register a gauge."""
        gauge = Gauge(name, description, unit)
        self.registry.register(gauge)
        return gauge

    def histogram(
        self,
        name: str,
        description: str,
        buckets: Optional[List[float]] = None,
        unit: Optional[str] = None
    ) -> Histogram:
        """Create and register a histogram."""
        histogram = Histogram(name, description, buckets, unit)
        self.registry.register(histogram)
        return histogram

    @contextmanager
    def record_duration(
        self,
        histogram: Histogram,
        labels: Optional[Dict[str, str]] = None
    ):
        """Context manager to record operation duration."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            histogram.observe(duration, labels)

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format."""
        return self.exporter.export()

    def get_uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self._start_time


# Global metrics collector instance
metrics_collector = MetricsCollector()

# Convenience functions
def create_counter(name: str, description: str, unit: Optional[str] = None) -> Counter:
    """Create a counter metric."""
    return metrics_collector.counter(name, description, unit)


def create_gauge(name: str, description: str, unit: Optional[str] = None) -> Gauge:
    """Create a gauge metric."""
    return metrics_collector.gauge(name, description, unit)


def create_histogram(
    name: str,
    description: str,
    buckets: Optional[List[float]] = None,
    unit: Optional[str] = None
) -> Histogram:
    """Create a histogram metric."""
    return metrics_collector.histogram(name, description, buckets, unit)


@contextmanager
def record_duration(histogram: Histogram, labels: Optional[Dict[str, str]] = None):
    """Record operation duration."""
    with metrics_collector.record_duration(histogram, labels):
        yield