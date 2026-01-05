"""
Simple performance benchmarks that can run without external dependencies.
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any
import statistics

import pytest
import numpy as np

from app.engine.models import Candle, TimeFrame


class SimpleBenchmark:
    """Simple performance benchmark without external dependencies."""

    def __init__(self, name: str):
        self.name = name
        self.samples: List[float] = []

    def measure(self, func, *args, **kwargs):
        """Measure function execution time."""
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        self.samples.append(elapsed)
        return result

    async def measure_async(self, func, *args, **kwargs):
        """Measure async function execution time."""
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        self.samples.append(elapsed)
        return result

    def report(self) -> Dict[str, float]:
        """Generate benchmark report."""
        if not self.samples:
            return {}

        sorted_samples = sorted(self.samples)
        return {
            "name": self.name,
            "samples": len(self.samples),
            "mean_ms": statistics.mean(self.samples) * 1000,
            "median_ms": statistics.median(self.samples) * 1000,
            "min_ms": min(self.samples) * 1000,
            "max_ms": max(self.samples) * 1000,
            "p95_ms": sorted_samples[int(len(sorted_samples) * 0.95)] * 1000,
            "p99_ms": sorted_samples[int(len(sorted_samples) * 0.99)] * 1000 if len(sorted_samples) > 100 else sorted_samples[-1] * 1000
        }


class TestSimplePerformanceBenchmarks:
    """Simple performance benchmarks."""

    def test_candle_serialization_performance(self):
        """Test candle serialization speed."""
        benchmark = SimpleBenchmark("candle_serialization")

        # Create test candle
        candle = Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            open_time=datetime.now() - timedelta(minutes=15),
            close_time=datetime.now(),
            open_price=Decimal("50000"),
            high_price=Decimal("50500"),
            low_price=Decimal("49500"),
            close_price=Decimal("50200"),
            volume=Decimal("1000"),
            quote_volume=Decimal("50000000"),
            trades=5000,
            taker_buy_base_volume=Decimal("600"),
            taker_buy_quote_volume=Decimal("30000000")
        )

        # Run 1000 iterations
        for _ in range(1000):
            benchmark.measure(candle.model_dump_json)

        # Report results
        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']:.3f}ms")
        print(f"  P95: {report['p95_ms']:.3f}ms")

        # Assert performance
        assert report['mean_ms'] < 1.0, "Candle serialization too slow"

    def test_bulk_candle_processing(self):
        """Test processing multiple candles."""
        benchmark = SimpleBenchmark("bulk_candle_processing")

        def process_candles(candles: List[Candle]) -> int:
            """Simulate candle processing."""
            processed = 0
            for candle in candles:
                # Validate
                _ = candle.model_validate(candle.model_dump())
                # Create key
                key = f"{candle.symbol}:{candle.timeframe}:{candle.open_time}"
                processed += 1
            return processed

        # Create 100 candles
        candles = []
        base_time = datetime.now() - timedelta(hours=24)
        for i in range(100):
            candle = Candle(
                venue="spot",
                symbol="BTCUSDT",
                timeframe=TimeFrame.M15,
                open_time=base_time + timedelta(minutes=15 * i),
                close_time=base_time + timedelta(minutes=15 * (i + 1)),
                open_price=Decimal("50000") + Decimal(str(i)),
                high_price=Decimal("50100") + Decimal(str(i)),
                low_price=Decimal("49900") + Decimal(str(i)),
                close_price=Decimal("50050") + Decimal(str(i)),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=1000,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000")
            )
            candles.append(candle)

        # Run 100 iterations
        for _ in range(100):
            result = benchmark.measure(process_candles, candles)
            assert result == 100

        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']:.3f}ms for 100 candles")
        print(f"  Per candle: {report['mean_ms']/100:.3f}ms")

        # Should process 100 candles in under 50ms
        assert report['mean_ms'] < 50

    def test_ema_calculation_speed(self):
        """Test EMA calculation performance."""
        benchmark = SimpleBenchmark("ema_calculation")

        def calculate_ema(prices: List[float], period: int) -> List[float]:
            """Calculate EMA."""
            if len(prices) < period:
                return []

            ema = []
            multiplier = 2.0 / (period + 1)

            # Initial SMA
            sma = sum(prices[:period]) / period
            ema.append(sma)

            # Calculate EMA
            for i in range(period, len(prices)):
                value = (prices[i] * multiplier) + (ema[-1] * (1 - multiplier))
                ema.append(value)

            return ema

        # Generate 1000 price points
        prices = [50000 + np.random.randn() * 100 for _ in range(1000)]

        # Run 100 iterations
        for _ in range(100):
            result = benchmark.measure(calculate_ema, prices, 20)
            assert len(result) == 981

        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']:.3f}ms for 1000 prices")
        print(f"  P95: {report['p95_ms']:.3f}ms")

        # Should calculate EMA quickly
        assert report['mean_ms'] < 5

    @pytest.mark.asyncio
    async def test_concurrent_processing(self):
        """Test concurrent processing performance."""
        benchmark = SimpleBenchmark("concurrent_processing")

        async def process_symbol(symbol: str, count: int) -> int:
            """Simulate async processing."""
            processed = 0
            for i in range(count):
                # Simulate some work
                await asyncio.sleep(0)  # Yield to event loop
                processed += 1
            return processed

        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]

        # Run 50 iterations
        for _ in range(50):
            # Process all symbols concurrently
            tasks = [process_symbol(symbol, 20) for symbol in symbols]
            results = await benchmark.measure_async(
                asyncio.gather, *tasks
            )
            assert sum(results) == 100  # 20 * 5 symbols

        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']:.3f}ms for 5 concurrent tasks")
        print(f"  P95: {report['p95_ms']:.3f}ms")

        # Concurrent processing should be fast
        assert report['mean_ms'] < 10

    @pytest.mark.asyncio
    async def test_event_bus_throughput(self):
        """Test event bus message throughput."""
        benchmark = SimpleBenchmark("event_bus_throughput")

        class MockEventBus:
            def __init__(self):
                self.messages = []

            async def publish(self, event_type: str, data: Dict):
                """Simulate event publishing."""
                self.messages.append({
                    "type": event_type,
                    "data": data,
                    "timestamp": time.time()
                })

        bus = MockEventBus()

        async def publish_batch(count: int):
            """Publish batch of events."""
            for i in range(count):
                await bus.publish("test_event", {"index": i})
            return len(bus.messages)

        # Run 100 iterations of 100 messages each
        for _ in range(100):
            bus.messages.clear()
            count = await benchmark.measure_async(publish_batch, 100)
            assert count == 100

        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']:.3f}ms for 100 messages")
        print(f"  Throughput: {100000/report['mean_ms']:.0f} messages/second")

        # Should handle 100 messages quickly
        assert report['mean_ms'] < 10

    def test_risk_calculation_performance(self):
        """Test risk management calculation speed."""
        benchmark = SimpleBenchmark("risk_calculation")

        def calculate_position_size(
            balance: float,
            risk_pct: float,
            entry: float,
            stop: float,
            leverage: float = 1.0
        ) -> float:
            """Calculate position size with risk management."""
            risk_amount = balance * risk_pct / 100
            price_diff = abs(entry - stop)

            if price_diff == 0:
                return 0

            position_size = risk_amount / price_diff
            max_position = balance * leverage
            return min(position_size, max_position)

        # Test data
        balance = 10000
        risk_pct = 0.5

        # Run 10000 calculations
        for i in range(10000):
            entry = 50000 + i
            stop = entry * 0.98

            size = benchmark.measure(
                calculate_position_size,
                balance, risk_pct, entry, stop, 3.0
            )
            assert size > 0

        report = benchmark.report()
        print(f"\n{report['name']}:")
        print(f"  Mean: {report['mean_ms']*1000:.3f} microseconds")
        print(f"  P95: {report['p95_ms']*1000:.3f} microseconds")

        # Risk calculations should be instant (< 0.01ms)
        assert report['mean_ms'] < 0.01

    def generate_summary_report(self):
        """Generate summary of all benchmarks."""
        print("\n" + "=" * 60)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 60)
        print("\nKey Performance Metrics:")
        print("- Candle Serialization: < 1ms per candle")
        print("- Bulk Processing: < 0.5ms per candle")
        print("- EMA Calculation: < 5ms for 1000 points")
        print("- Concurrent Tasks: < 2ms per task overhead")
        print("- Event Bus: > 10,000 messages/second")
        print("- Risk Calculations: < 10 microseconds")

        # Save report
        report = {
            "timestamp": datetime.now().isoformat(),
            "benchmarks": {
                "candle_serialization": "< 1ms",
                "bulk_processing": "< 0.5ms per candle",
                "ema_calculation": "< 5ms for 1000 points",
                "concurrent_processing": "< 2ms overhead",
                "event_bus_throughput": "> 10,000 msg/sec",
                "risk_calculations": "< 10 microseconds"
            },
            "targets": {
                "candle_to_signal": "≤ 500ms P95",
                "signal_to_order": "≤ 300ms P95",
                "health_check": "≤ 100ms",
                "websocket_latency": "≤ 50ms"
            }
        }

        with open("performance_benchmarks.json", "w") as f:
            json.dump(report, f, indent=2)

        print("\nReport saved to: performance_benchmarks.json")


if __name__ == "__main__":
    # Run tests
    test = TestSimplePerformanceBenchmarks()

    print("Running performance benchmarks...")
    test.test_candle_serialization_performance()
    test.test_bulk_candle_processing()
    test.test_ema_calculation_speed()

    # Run async tests
    asyncio.run(test.test_concurrent_processing())
    asyncio.run(test.test_event_bus_throughput())

    test.test_risk_calculation_performance()

    # Generate summary
    test.generate_summary_report()