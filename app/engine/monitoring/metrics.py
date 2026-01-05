"""
Prometheus metrics collection for trading engine.

Provides counters, histograms, and gauges for monitoring system performance,
trading activity, and health status.
"""

from collections.abc import Callable
from functools import wraps
import logging
import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.core import CollectorRegistry

logger = logging.getLogger(__name__)


# Create a custom registry to avoid conflicts
registry = CollectorRegistry()

# ==============================================================================
# Trading Metrics
# ==============================================================================

# Counters
signals_generated = Counter(
    "trading_signals_generated_total",
    "Total number of trading signals generated",
    ["symbol", "timeframe", "signal_type", "source"],
    registry=registry,
)

orders_placed = Counter(
    "trading_orders_placed_total",
    "Total number of orders placed",
    ["symbol", "side", "order_type", "status"],
    registry=registry,
)

order_errors = Counter(
    "trading_order_errors_total",
    "Total number of order placement errors",
    ["symbol", "error_type"],
    registry=registry,
)

candles_processed = Counter(
    "data_candles_processed_total",
    "Total number of candles processed",
    ["symbol", "timeframe"],
    registry=registry,
)

# Histograms
signal_generation_latency = Histogram(
    "trading_signal_generation_seconds",
    "Time to generate signal from candle close",
    ["symbol", "timeframe"],
    buckets=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
    registry=registry,
)

order_placement_latency = Histogram(
    "trading_order_placement_seconds",
    "Time to place order after signal",
    ["symbol"],
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0),
    registry=registry,
)

position_size_distribution = Histogram(
    "trading_position_size_usdt",
    "Distribution of position sizes in USDT",
    ["symbol"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
    registry=registry,
)

# Gauges
active_positions = Gauge(
    "trading_active_positions",
    "Number of currently active positions",
    ["symbol"],
    registry=registry,
)

account_balance = Gauge(
    "trading_account_balance_usdt",
    "Current account balance in USDT",
    registry=registry,
)

daily_pnl = Gauge(
    "trading_daily_pnl_usdt",
    "Daily profit and loss in USDT",
    registry=registry,
)

# ==============================================================================
# System Metrics
# ==============================================================================

# WebSocket metrics
websocket_connections = Gauge(
    "websocket_connections_active",
    "Number of active WebSocket connections",
    ["type"],  # 'market_data', 'user_data'
    registry=registry,
)

websocket_messages_received = Counter(
    "websocket_messages_received_total",
    "Total WebSocket messages received",
    ["type", "symbol"],
    registry=registry,
)

websocket_reconnections = Counter(
    "websocket_reconnections_total",
    "Total WebSocket reconnection attempts",
    ["reason"],
    registry=registry,
)

# Database metrics
db_query_duration = Histogram(
    "database_query_duration_seconds",
    "Database query execution time",
    ["operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=registry,
)

db_connection_pool_size = Gauge(
    "database_connection_pool_size",
    "Current size of database connection pool",
    ["state"],  # 'active', 'idle'
    registry=registry,
)

# Event bus metrics
event_bus_messages = Counter(
    "event_bus_messages_total",
    "Total messages published to event bus",
    ["event_type"],
    registry=registry,
)

event_bus_processing_time = Histogram(
    "event_bus_processing_seconds",
    "Time to process event bus messages",
    ["event_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    registry=registry,
)

# Health check metrics
health_check_duration = Histogram(
    "health_check_duration_seconds",
    "Time to perform health checks",
    ["component"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
    registry=registry,
)

health_check_status = Gauge(
    "health_check_status",
    "Current health check status (1=healthy, 0.5=degraded, 0=unhealthy)",
    ["component"],
    registry=registry,
)

# ==============================================================================
# Chart Snapshot Metrics
# ==============================================================================

snapshot_generation_requests = Counter(
    "snapshot_generation_requests_total",
    "Total snapshot generation requests",
    ["status"],  # 'success', 'failed', 'timeout'
    registry=registry,
)

snapshot_generation_duration = Histogram(
    "snapshot_generation_duration_seconds",
    "Time to generate chart snapshot",
    ["symbol"],
    buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0),
    registry=registry,
)

browser_pool_size = Gauge(
    "puppeteer_browser_pool_size",
    "Current number of browser instances",
    ["state"],  # 'active', 'idle'
    registry=registry,
)

snapshot_delivery_success = Counter(
    "snapshot_delivery_success_total",
    "Successful snapshot deliveries",
    ["channel"],  # 'telegram', 'ui'
    registry=registry,
)

# ==============================================================================
# Helper Functions
# ==============================================================================


def track_time(metric: Histogram, labels: dict[str, str] | None = None):
    """
    Decorator to track execution time of a function.

    Args:
        metric: Prometheus Histogram to track time
        labels: Optional labels to add to the metric

    Usage:
        @track_time(signal_generation_latency, {'symbol': 'BTCUSDT', 'timeframe': '15m'})
        async def generate_signal():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def increment_counter(
    counter: Counter, labels: dict[str, str] | None = None, value: float = 1,
):
    """
    Increment a counter metric.

    Args:
        counter: Prometheus Counter to increment
        labels: Optional labels to add
        value: Amount to increment (default: 1)
    """
    try:
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)
    except Exception as e:
        logger.error(f"Error incrementing counter: {e}")


def set_gauge(gauge: Gauge, value: float, labels: dict[str, str] | None = None):
    """
    Set a gauge metric value.

    Args:
        gauge: Prometheus Gauge to set
        value: Value to set
        labels: Optional labels to add
    """
    try:
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)
    except Exception as e:
        logger.error(f"Error setting gauge: {e}")


def observe_histogram(
    histogram: Histogram, value: float, labels: dict[str, str] | None = None,
):
    """
    Record an observation in a histogram.

    Args:
        histogram: Prometheus Histogram
        value: Value to observe
        labels: Optional labels to add
    """
    try:
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)
    except Exception as e:
        logger.error(f"Error observing histogram: {e}")


# ==============================================================================
# Metrics Export
# ==============================================================================


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.

    Returns:
        Metrics data in Prometheus text format
    """
    return generate_latest(registry)


def get_metrics_content_type() -> str:
    """
    Get the content type for Prometheus metrics.

    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST


# ==============================================================================
# Metric Collection Functions
# ==============================================================================


def record_signal_generated(symbol: str, timeframe: str, signal_type: str, source: str):
    """Record a signal generation event."""
    increment_counter(
        signals_generated,
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "signal_type": signal_type,
            "source": source,
        },
    )


def record_order_placed(symbol: str, side: str, order_type: str, status: str):
    """Record an order placement event."""
    increment_counter(
        orders_placed,
        {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "status": status,
        },
    )


def record_order_error(symbol: str, error_type: str):
    """Record an order error event."""
    increment_counter(
        order_errors,
        {
            "symbol": symbol,
            "error_type": error_type,
        },
    )


def record_candle_processed(symbol: str, timeframe: str):
    """Record a candle processing event."""
    increment_counter(
        candles_processed,
        {
            "symbol": symbol,
            "timeframe": timeframe,
        },
    )


def update_active_positions(symbol: str, count: int):
    """Update the number of active positions."""
    set_gauge(
        active_positions,
        count,
        {"symbol": symbol},
    )


def update_account_balance(balance: float):
    """Update the account balance."""
    set_gauge(account_balance, balance)


def update_daily_pnl(pnl: float):
    """Update the daily P&L."""
    set_gauge(daily_pnl, pnl)


def record_websocket_message(message_type: str, symbol: str):
    """Record a WebSocket message."""
    increment_counter(
        websocket_messages_received,
        {
            "type": message_type,
            "symbol": symbol,
        },
    )


def record_websocket_reconnection(reason: str):
    """Record a WebSocket reconnection."""
    increment_counter(
        websocket_reconnections,
        {"reason": reason},
    )


def update_websocket_connections(connection_type: str, count: int):
    """Update WebSocket connection count."""
    set_gauge(
        websocket_connections,
        count,
        {"type": connection_type},
    )


def record_db_query(operation: str, table: str, duration: float):
    """Record a database query."""
    observe_histogram(
        db_query_duration,
        duration,
        {
            "operation": operation,
            "table": table,
        },
    )


def update_db_pool_size(active: int, idle: int):
    """Update database connection pool metrics."""
    set_gauge(db_connection_pool_size, active, {"state": "active"})
    set_gauge(db_connection_pool_size, idle, {"state": "idle"})


def record_event_published(event_type: str):
    """Record an event bus publication."""
    increment_counter(
        event_bus_messages,
        {"event_type": event_type},
    )


def record_event_processing_time(event_type: str, duration: float):
    """Record event processing time."""
    observe_histogram(
        event_bus_processing_time,
        duration,
        {"event_type": event_type},
    )


def record_snapshot_request(status: str):
    """Record a snapshot generation request."""
    increment_counter(
        snapshot_generation_requests,
        {"status": status},
    )


def record_snapshot_duration(symbol: str, duration: float):
    """Record snapshot generation duration."""
    observe_histogram(
        snapshot_generation_duration,
        duration,
        {"symbol": symbol},
    )


def update_browser_pool(active: int, idle: int):
    """Update browser pool metrics."""
    set_gauge(browser_pool_size, active, {"state": "active"})
    set_gauge(browser_pool_size, idle, {"state": "idle"})


def record_snapshot_delivery(channel: str):
    """Record successful snapshot delivery."""
    increment_counter(
        snapshot_delivery_success,
        {"channel": channel},
    )


def record_health_check_duration(component: str, duration: float):
    """Record health check duration."""
    observe_histogram(
        health_check_duration,
        duration,
        {"component": component},
    )


def update_health_check_status(component: str, status: str):
    """Update health check status gauge."""
    # Map status to numeric value
    status_values = {
        "healthy": 1.0,
        "degraded": 0.5,
        "unhealthy": 0.0,
    }
    value = status_values.get(status.lower(), 0.0)
    set_gauge(
        health_check_status,
        value,
        {"component": component},
    )


if __name__ == "__main__":
    # Example usage
    record_signal_generated("BTCUSDT", "15m", "BUY", "zone_retest")
    record_order_placed("BTCUSDT", "BUY", "LIMIT", "FILLED")
    update_account_balance(10000.0)

    # Print metrics
    metrics = get_metrics()
    print(metrics.decode("utf-8"))
