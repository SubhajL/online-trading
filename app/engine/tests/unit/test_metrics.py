"""
Unit tests for metrics collection framework.
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from app.engine.core.metrics import (
    MetricType,
    Metric,
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    PrometheusExporter,
    MetricsCollector,
    create_counter,
    create_gauge,
    create_histogram,
    record_duration,
)


class TestCounter:
    def test_counter_increment(self):
        counter = Counter("test_counter", "Test counter")

        counter.inc()
        assert counter.get() == 1.0

        counter.inc(5)
        assert counter.get() == 6.0

    def test_counter_with_labels(self):
        counter = Counter("requests_total", "Total requests")

        counter.inc(1, {"method": "GET", "status": "200"})
        counter.inc(2, {"method": "GET", "status": "200"})
        counter.inc(1, {"method": "POST", "status": "201"})

        assert counter.get({"method": "GET", "status": "200"}) == 3.0
        assert counter.get({"method": "POST", "status": "201"}) == 1.0
        assert counter.get({"method": "DELETE", "status": "404"}) == 0.0

    def test_counter_cannot_decrease(self):
        counter = Counter("test_counter", "Test counter")

        with pytest.raises(ValueError, match="Counter can only increase"):
            counter.inc(-1)

    def test_counter_collect(self):
        counter = Counter("test_counter", "Test counter", "seconds")
        counter.inc(10, {"type": "a"})
        counter.inc(20, {"type": "b"})

        metrics = counter.collect()
        assert len(metrics) == 2
        assert all(m.type == MetricType.COUNTER for m in metrics)
        assert all(m.name == "test_counter" for m in metrics)
        assert all(m.unit == "seconds" for m in metrics)


class TestGauge:
    def test_gauge_operations(self):
        gauge = Gauge("memory_usage", "Memory usage")

        gauge.set(100)
        assert gauge.get() == 100

        gauge.inc(50)
        assert gauge.get() == 150

        gauge.dec(30)
        assert gauge.get() == 120

        gauge.set(200)
        assert gauge.get() == 200

    def test_gauge_with_labels(self):
        gauge = Gauge("active_connections", "Active connections")

        gauge.set(10, {"server": "web1"})
        gauge.set(20, {"server": "web2"})
        gauge.inc(5, {"server": "web1"})

        assert gauge.get({"server": "web1"}) == 15
        assert gauge.get({"server": "web2"}) == 20


class TestHistogram:
    def test_histogram_observations(self):
        histogram = Histogram(
            "request_duration", "Request duration", buckets=[0.1, 0.5, 1.0, 5.0]
        )

        histogram.observe(0.05)
        histogram.observe(0.3)
        histogram.observe(0.7)
        histogram.observe(2.0)
        histogram.observe(10.0)

        metrics = histogram.collect()

        # Check bucket metrics exist
        bucket_metrics = [m for m in metrics if m.name == "request_duration_bucket"]
        assert len(bucket_metrics) == 5  # 4 buckets + inf

        # Check sum and count
        sum_metric = next(
            (m for m in metrics if m.name == "request_duration_sum"), None
        )
        assert sum_metric is not None
        assert sum_metric.value == pytest.approx(13.05)

        count_metric = next(
            (m for m in metrics if m.name == "request_duration_count"), None
        )
        assert count_metric is not None
        assert count_metric.value == 5

    def test_histogram_percentiles(self):
        histogram = Histogram("test_hist", "Test histogram", buckets=[1, 2, 3, 4, 5])

        # Add values: 0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5
        for i in range(10):
            histogram.observe(i * 0.5)

        # 50th percentile (5th value) = 2.0, should return bucket 2
        assert histogram.get_percentile(50) == 2
        # 90th percentile (9th value) = 4.0, should return bucket 4
        assert histogram.get_percentile(90) == 4
        # 100th percentile (all values) includes 4.5, should return bucket 5
        assert histogram.get_percentile(100) == 5

    def test_histogram_with_labels(self):
        histogram = Histogram("response_time", "Response time")

        histogram.observe(0.1, {"endpoint": "/api/users"})
        histogram.observe(0.2, {"endpoint": "/api/users"})
        histogram.observe(0.5, {"endpoint": "/api/posts"})

        # Percentiles should be calculated per label set
        assert histogram.get_percentile(50, {"endpoint": "/api/users"}) < 1
        assert histogram.get_percentile(50, {"endpoint": "/api/posts"}) < 1


class TestMetricsRegistry:
    def test_register_and_get(self):
        registry = MetricsRegistry()
        counter = Counter("test", "Test")

        registry.register(counter)
        assert registry.get("test") is counter
        assert registry.get("nonexistent") is None

    def test_cannot_register_duplicate(self):
        registry = MetricsRegistry()
        counter1 = Counter("test", "Test 1")
        counter2 = Counter("test", "Test 2")

        registry.register(counter1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(counter2)

    def test_unregister(self):
        registry = MetricsRegistry()
        counter = Counter("test", "Test")

        registry.register(counter)
        assert registry.get("test") is counter

        registry.unregister("test")
        assert registry.get("test") is None

    def test_collect_all(self):
        registry = MetricsRegistry()

        counter = Counter("counter", "Counter")
        counter.inc(10)
        registry.register(counter)

        gauge = Gauge("gauge", "Gauge")
        gauge.set(20)
        registry.register(gauge)

        metrics = registry.collect_all()
        assert len(metrics) == 2


class TestPrometheusExporter:
    def test_prometheus_format(self):
        registry = MetricsRegistry()
        exporter = PrometheusExporter(registry)

        counter = Counter("http_requests_total", "Total HTTP requests")
        counter.inc(100, {"method": "GET", "status": "200"})
        registry.register(counter)

        gauge = Gauge("temperature_celsius", "Temperature in Celsius")
        gauge.set(23.5)
        registry.register(gauge)

        output = exporter.export()

        assert "# HELP http_requests_total Total HTTP requests" in output
        assert "# TYPE http_requests_total counter" in output
        assert 'http_requests_total{method="GET",status="200"} 100' in output

        assert "# HELP temperature_celsius Temperature in Celsius" in output
        assert "# TYPE temperature_celsius gauge" in output
        assert "temperature_celsius 23.5" in output

    def test_label_escaping(self):
        registry = MetricsRegistry()
        exporter = PrometheusExporter(registry)

        counter = Counter("test", "Test")
        counter.inc(1, {"path": 'path/with"quotes', "newline": "line1\nline2"})
        registry.register(counter)

        output = exporter.export()
        assert r'path="path/with\"quotes"' in output
        assert r'newline="line1\nline2"' in output


class TestMetricsCollector:
    def test_create_metrics(self):
        collector = MetricsCollector()

        counter = collector.counter("test_counter", "Test counter")
        assert counter is not None
        assert collector.registry.get("test_counter") is counter

        gauge = collector.gauge("test_gauge", "Test gauge")
        assert gauge is not None
        assert collector.registry.get("test_gauge") is gauge

        histogram = collector.histogram("test_histogram", "Test histogram")
        assert histogram is not None
        assert collector.registry.get("test_histogram") is histogram

    def test_record_duration_context_manager(self):
        collector = MetricsCollector()
        histogram = collector.histogram("operation_duration", "Operation duration")

        with collector.record_duration(histogram, {"operation": "test"}):
            time.sleep(0.01)

        metrics = histogram.collect()
        count_metric = next(
            (m for m in metrics if m.name == "operation_duration_count"), None
        )
        assert count_metric is not None
        assert count_metric.value == 1

    def test_export_prometheus(self):
        collector = MetricsCollector()

        counter = collector.counter("events_processed", "Events processed")
        counter.inc(42)

        output = collector.export_prometheus()
        assert "events_processed 42" in output

    def test_uptime(self):
        collector = MetricsCollector()
        time.sleep(0.01)
        uptime = collector.get_uptime()
        assert uptime > 0
        assert uptime < 1  # Should be less than 1 second


class TestThreadSafety:
    def test_counter_thread_safety(self):
        counter = Counter("concurrent_test", "Concurrent test")

        def increment():
            for _ in range(100):
                counter.inc()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(10)]
            for future in futures:
                future.result()

        assert counter.get() == 1000

    def test_gauge_thread_safety(self):
        gauge = Gauge("concurrent_gauge", "Concurrent gauge")

        def modify():
            for i in range(100):
                if i % 2 == 0:
                    gauge.inc()
                else:
                    gauge.dec()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(modify) for _ in range(10)]
            for future in futures:
                future.result()

        # Should end up at 0 since each thread does equal inc/dec
        assert gauge.get() == 0

    def test_histogram_thread_safety(self):
        histogram = Histogram("concurrent_hist", "Concurrent histogram")

        def observe():
            for i in range(100):
                histogram.observe(i)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(observe) for _ in range(10)]
            for future in futures:
                future.result()

        metrics = histogram.collect()
        count_metric = next(
            (m for m in metrics if m.name == "concurrent_hist_count"), None
        )
        assert count_metric.value == 1000


class TestConvenienceFunctions:
    def test_create_counter(self):
        counter = create_counter("convenience_counter", "Test counter")
        counter.inc(5)
        assert counter.get() == 5

    def test_create_gauge(self):
        gauge = create_gauge("convenience_gauge", "Test gauge")
        gauge.set(10)
        assert gauge.get() == 10

    def test_create_histogram(self):
        histogram = create_histogram("convenience_histogram", "Test histogram")
        histogram.observe(1.5)

        metrics = histogram.collect()
        assert len(metrics) > 0

    def test_record_duration_function(self):
        histogram = create_histogram("timing_test", "Timing test")

        with record_duration(histogram, {"test": "true"}):
            time.sleep(0.01)

        metrics = histogram.collect()
        count_metrics = [m for m in metrics if m.name == "timing_test_count"]
        assert len(count_metrics) > 0
