"""
Tests for Prometheus metrics collection.
"""

import asyncio
import time
from decimal import Decimal
import pytest

from app.engine.monitoring.metrics import (
    # Metrics
    signals_generated, orders_placed, signal_generation_latency,
    active_positions, account_balance,
    # Helper functions
    track_time, increment_counter, set_gauge, observe_histogram,
    record_signal_generated, record_order_placed, record_candle_processed,
    update_active_positions, update_account_balance,
    record_snapshot_request, record_snapshot_duration,
    get_metrics
)


class TestMetricHelpers:
    """Test metric helper functions."""

    def test_increment_counter(self):
        """Test counter increment."""
        # Get initial value
        initial_metrics = get_metrics().decode('utf-8')

        # Increment counter
        increment_counter(
            signals_generated,
            {
                'symbol': 'BTCUSDT',
                'timeframe': '15m',
                'signal_type': 'BUY',
                'source': 'test'
            }
        )

        # Check metrics updated
        final_metrics = get_metrics().decode('utf-8')
        assert 'trading_signals_generated_total' in final_metrics
        assert 'symbol="BTCUSDT"' in final_metrics
        assert 'signal_type="BUY"' in final_metrics

    def test_set_gauge(self):
        """Test gauge setting."""
        # Set gauge value
        set_gauge(account_balance, 10000.0)

        # Check metrics
        metrics = get_metrics().decode('utf-8')
        assert 'trading_account_balance_usdt 10000.0' in metrics

    def test_observe_histogram(self):
        """Test histogram observation."""
        # Record some observations
        observe_histogram(
            signal_generation_latency,
            0.25,
            {'symbol': 'BTCUSDT', 'timeframe': '15m'}
        )
        observe_histogram(
            signal_generation_latency,
            0.75,
            {'symbol': 'BTCUSDT', 'timeframe': '15m'}
        )

        # Check metrics
        metrics = get_metrics().decode('utf-8')
        assert 'trading_signal_generation_seconds_bucket' in metrics
        assert 'trading_signal_generation_seconds_count' in metrics
        assert 'trading_signal_generation_seconds_sum' in metrics

    @pytest.mark.asyncio
    async def test_track_time_decorator_async(self):
        """Test time tracking decorator with async function."""
        # Create test function with decorator
        @track_time(
            signal_generation_latency,
            {'symbol': 'ETHUSDT', 'timeframe': '1h'}
        )
        async def slow_function():
            await asyncio.sleep(0.1)
            return "done"

        # Run function
        result = await slow_function()
        assert result == "done"

        # Check metrics
        metrics = get_metrics().decode('utf-8')
        assert 'symbol="ETHUSDT"' in metrics
        assert 'timeframe="1h"' in metrics

    def test_track_time_decorator_sync(self):
        """Test time tracking decorator with sync function."""
        # Create test function with decorator
        @track_time(
            signal_generation_latency,
            {'symbol': 'SOLUSDT', 'timeframe': '5m'}
        )
        def fast_function():
            time.sleep(0.05)
            return "done"

        # Run function
        result = fast_function()
        assert result == "done"

        # Check metrics
        metrics = get_metrics().decode('utf-8')
        assert 'symbol="SOLUSDT"' in metrics


class TestTradingMetrics:
    """Test trading-specific metric recording."""

    def test_record_signal_generated(self):
        """Test signal generation recording."""
        record_signal_generated("BTCUSDT", "15m", "BUY", "zone_retest")

        metrics = get_metrics().decode('utf-8')
        assert 'trading_signals_generated_total' in metrics
        assert 'source="zone_retest"' in metrics

    def test_record_order_placed(self):
        """Test order placement recording."""
        record_order_placed("BTCUSDT", "BUY", "LIMIT", "FILLED")

        metrics = get_metrics().decode('utf-8')
        assert 'trading_orders_placed_total' in metrics
        assert 'side="BUY"' in metrics
        assert 'order_type="LIMIT"' in metrics
        assert 'status="FILLED"' in metrics

    def test_update_active_positions(self):
        """Test active position updates."""
        update_active_positions("BTCUSDT", 2)
        update_active_positions("ETHUSDT", 1)

        metrics = get_metrics().decode('utf-8')
        assert 'trading_active_positions{symbol="BTCUSDT"} 2' in metrics
        assert 'trading_active_positions{symbol="ETHUSDT"} 1' in metrics

    def test_update_account_metrics(self):
        """Test account metric updates."""
        update_account_balance(15000.0)

        metrics = get_metrics().decode('utf-8')
        assert 'trading_account_balance_usdt 15000.0' in metrics


class TestSystemMetrics:
    """Test system performance metrics."""

    def test_record_candle_processed(self):
        """Test candle processing metrics."""
        # Record multiple candles
        for _ in range(5):
            record_candle_processed("BTCUSDT", "15m")

        metrics = get_metrics().decode('utf-8')
        assert 'data_candles_processed_total' in metrics
        assert 'symbol="BTCUSDT"' in metrics
        assert 'timeframe="15m"' in metrics


class TestSnapshotMetrics:
    """Test chart snapshot metrics."""

    def test_record_snapshot_request(self):
        """Test snapshot request recording."""
        record_snapshot_request("success")
        record_snapshot_request("failed")
        record_snapshot_request("timeout")

        metrics = get_metrics().decode('utf-8')
        assert 'snapshot_generation_requests_total' in metrics
        assert 'status="success"' in metrics
        assert 'status="failed"' in metrics
        assert 'status="timeout"' in metrics

    def test_record_snapshot_duration(self):
        """Test snapshot duration recording."""
        # Record various durations
        record_snapshot_duration("BTCUSDT", 1.5)
        record_snapshot_duration("BTCUSDT", 2.3)
        record_snapshot_duration("ETHUSDT", 3.1)

        metrics = get_metrics().decode('utf-8')
        assert 'snapshot_generation_duration_seconds' in metrics
        assert 'symbol="BTCUSDT"' in metrics
        assert 'symbol="ETHUSDT"' in metrics


class TestMetricsIntegration:
    """Test metrics integration with simulated trading flow."""

    @pytest.mark.asyncio
    async def test_complete_trading_flow_metrics(self):
        """Test metrics collection during complete trading flow."""
        # Simulate candle processing
        start_time = time.time()
        record_candle_processed("BTCUSDT", "15m")

        # Simulate signal generation
        await asyncio.sleep(0.1)  # Simulate processing time
        record_signal_generated("BTCUSDT", "15m", "BUY", "smc_confluence")
        signal_latency = time.time() - start_time
        observe_histogram(
            signal_generation_latency,
            signal_latency,
            {'symbol': 'BTCUSDT', 'timeframe': '15m'}
        )

        # Simulate snapshot generation
        snapshot_start = time.time()
        await asyncio.sleep(0.2)  # Simulate Puppeteer rendering
        snapshot_duration = time.time() - snapshot_start
        record_snapshot_duration("BTCUSDT", snapshot_duration)
        record_snapshot_request("success")

        # Simulate order placement
        order_start = time.time()
        await asyncio.sleep(0.05)  # Simulate API call
        record_order_placed("BTCUSDT", "BUY", "LIMIT", "NEW")
        update_active_positions("BTCUSDT", 1)

        # Get final metrics
        metrics = get_metrics().decode('utf-8')

        # Verify all metrics recorded
        assert 'data_candles_processed_total' in metrics
        assert 'trading_signals_generated_total' in metrics
        assert 'trading_signal_generation_seconds' in metrics
        assert 'snapshot_generation_duration_seconds' in metrics
        assert 'trading_orders_placed_total' in metrics
        assert 'trading_active_positions' in metrics

        # Verify latency was reasonable
        assert signal_latency < 1.0  # Should be under 1 second


class TestMetricsExport:
    """Test metrics export functionality."""

    def test_get_metrics_format(self):
        """Test that metrics are exported in Prometheus format."""
        # Add some test data
        record_signal_generated("BTCUSDT", "15m", "BUY", "test")
        update_account_balance(10000.0)

        # Get metrics
        metrics_bytes = get_metrics()
        assert isinstance(metrics_bytes, bytes)

        # Decode and verify format
        metrics_text = metrics_bytes.decode('utf-8')

        # Should have Prometheus format
        assert '# HELP' in metrics_text
        assert '# TYPE' in metrics_text
        assert '{' in metrics_text  # Labels
        assert '}' in metrics_text

    def test_metrics_content_type(self):
        """Test metrics content type."""
        from app.engine.monitoring.metrics import get_metrics_content_type

        content_type = get_metrics_content_type()
        assert 'text/plain' in content_type
        assert 'version=' in content_type


class TestMetricErrorHandling:
    """Test error handling in metrics collection."""

    def test_invalid_label_handling(self):
        """Test handling of invalid labels."""
        # Try to record with None labels
        try:
            increment_counter(signals_generated, None)
            # Should not raise error
            assert True
        except Exception as e:
            pytest.fail(f"Should handle None labels gracefully: {e}")

    def test_concurrent_metric_updates(self):
        """Test concurrent metric updates."""
        import threading

        def update_metrics():
            for i in range(100):
                record_candle_processed(f"SYMBOL{i % 5}", "15m")
                update_account_balance(10000 + i)

        # Run concurrent updates
        threads = []
        for _ in range(5):
            t = threading.Thread(target=update_metrics)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify metrics are consistent
        metrics = get_metrics().decode('utf-8')
        assert 'data_candles_processed_total' in metrics
        assert 'trading_account_balance_usdt' in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])