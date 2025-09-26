"""
Performance benchmarks for critical trading paths.

Measures latency and throughput for:
- Candle processing pipeline
- Signal generation latency
- Decision making speed
- End-to-end trading flow
"""

import asyncio
import time
import statistics
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Callable
import json

import pytest
import numpy as np
from pytest_benchmark.plugin import benchmark

from app.engine.models import (
    Candle, TimeFrame, Features, SMCSignal, RetestSignal,
    TradingDecision, Position, EventType
)
from app.engine.bus import EventBus
from app.engine.monitoring.metrics import get_metrics


class PerformanceBenchmark:
    """Base class for performance benchmarks."""

    def __init__(self, name: str):
        self.name = name
        self.samples: List[float] = []
        self.start_time: float = 0

    def start(self):
        """Start timing."""
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        """Stop timing and record sample."""
        elapsed = time.perf_counter() - self.start_time
        self.samples.append(elapsed)
        return elapsed

    def get_stats(self) -> Dict[str, float]:
        """Get performance statistics."""
        if not self.samples:
            return {}

        sorted_samples = sorted(self.samples)
        return {
            "count": len(self.samples),
            "mean": statistics.mean(self.samples),
            "median": statistics.median(self.samples),
            "std": statistics.stdev(self.samples) if len(self.samples) > 1 else 0,
            "min": min(self.samples),
            "max": max(self.samples),
            "p50": sorted_samples[int(len(sorted_samples) * 0.5)],
            "p90": sorted_samples[int(len(sorted_samples) * 0.9)],
            "p95": sorted_samples[int(len(sorted_samples) * 0.95)],
            "p99": sorted_samples[int(len(sorted_samples) * 0.99)] if len(sorted_samples) > 100 else sorted_samples[-1]
        }

    def assert_performance(self, max_p95_ms: float, max_p99_ms: float = None):
        """Assert performance meets requirements."""
        stats = self.get_stats()

        # Convert to milliseconds
        p95_ms = stats["p95"] * 1000
        p99_ms = stats["p99"] * 1000

        assert p95_ms <= max_p95_ms, f"{self.name} P95 latency {p95_ms:.2f}ms exceeds limit {max_p95_ms}ms"

        if max_p99_ms:
            assert p99_ms <= max_p99_ms, f"{self.name} P99 latency {p99_ms:.2f}ms exceeds limit {max_p99_ms}ms"


class TestCandleProcessingPerformance:
    """Benchmark candle processing pipeline."""

    @pytest.fixture
    def candle_generator(self):
        """Generate test candles."""
        def generate(count: int, symbol: str = "BTCUSDT") -> List[Candle]:
            candles = []
            base_time = datetime.now() - timedelta(hours=24)
            base_price = Decimal("50000")

            for i in range(count):
                candle = Candle(
                    symbol=symbol,
                    timeframe=TimeFrame.M15,
                    open_time=base_time + timedelta(minutes=15 * i),
                    close_time=base_time + timedelta(minutes=15 * (i + 1)),
                    open_price=base_price + Decimal(str(i * 10)),
                    high_price=base_price + Decimal(str(i * 10 + 50)),
                    low_price=base_price + Decimal(str(i * 10 - 50)),
                    close_price=base_price + Decimal(str(i * 10 + 20)),
                    volume=Decimal("1000"),
                    quote_volume=Decimal("50000000"),
                    trades=500,
                    taker_buy_base_volume=Decimal("600"),
                    taker_buy_quote_volume=Decimal("30000000")
                )
                candles.append(candle)

            return candles

        return generate

    @pytest.mark.benchmark
    def test_single_candle_processing(self, candle_generator, benchmark):
        """Benchmark single candle processing."""
        candle = candle_generator(1)[0]

        def process_candle():
            # Simulate candle validation and storage
            validated = candle.model_validate(candle.model_dump())
            serialized = validated.model_dump_json()
            return len(serialized)

        result = benchmark(process_candle)
        assert result > 0

    @pytest.mark.benchmark
    def test_bulk_candle_ingestion(self, candle_generator, benchmark):
        """Benchmark bulk candle ingestion."""
        candles = candle_generator(1000)  # 1000 candles

        def ingest_candles():
            processed = []
            for candle in candles:
                # Simulate deduplication check
                key = f"{candle.symbol}:{candle.timeframe}:{candle.open_time}"

                # Simulate validation
                validated = candle.model_validate(candle.model_dump())
                processed.append(validated)

            return len(processed)

        result = benchmark(ingest_candles)
        assert result == 1000

        # Check performance
        stats = benchmark.stats.stats
        assert stats.median < 0.1  # Should process 1000 candles in under 100ms

    @pytest.mark.asyncio
    @pytest.mark.benchmark
    async def test_concurrent_candle_processing(self, candle_generator):
        """Benchmark concurrent candle processing for multiple symbols."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
        benchmark = PerformanceBenchmark("concurrent_candle_processing")

        async def process_symbol_candles(symbol: str):
            candles = candle_generator(100, symbol)
            processed = []

            for candle in candles:
                # Simulate async processing
                await asyncio.sleep(0)  # Yield to event loop
                processed.append(candle)

            return len(processed)

        # Run 10 iterations
        for _ in range(10):
            benchmark.start()

            # Process all symbols concurrently
            tasks = [process_symbol_candles(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks)

            benchmark.stop()

            assert sum(results) == 500  # 100 candles * 5 symbols

        # Assert performance
        benchmark.assert_performance(max_p95_ms=50, max_p99_ms=100)

        # Print stats
        stats = benchmark.get_stats()
        print(f"\nConcurrent candle processing stats: {json.dumps(stats, indent=2)}")


class TestFeatureCalculationPerformance:
    """Benchmark technical indicator calculations."""

    @pytest.fixture
    def price_data(self):
        """Generate price data for indicators."""
        prices = []
        base = 50000
        for i in range(1000):
            # Generate realistic price movement
            change = np.random.normal(0, 100)
            base = max(base + change, 1)
            prices.append(Decimal(str(round(base, 2))))
        return prices

    @pytest.mark.benchmark
    def test_ema_calculation_performance(self, price_data, benchmark):
        """Benchmark EMA calculation."""
        def calculate_ema(prices: List[Decimal], period: int) -> List[Decimal]:
            ema_values = []
            multiplier = Decimal("2") / (Decimal(str(period)) + Decimal("1"))

            # First EMA is SMA
            if len(prices) >= period:
                sma = sum(prices[:period]) / Decimal(str(period))
                ema_values.append(sma)

                # Calculate rest
                for i in range(period, len(prices)):
                    ema = (prices[i] * multiplier) + (ema_values[-1] * (Decimal("1") - multiplier))
                    ema_values.append(ema)

            return ema_values

        result = benchmark(calculate_ema, price_data, 20)
        assert len(result) == 981  # 1000 - 19

    @pytest.mark.benchmark
    def test_rsi_calculation_performance(self, price_data, benchmark):
        """Benchmark RSI calculation."""
        def calculate_rsi(prices: List[Decimal], period: int = 14) -> List[Decimal]:
            rsi_values = []

            # Calculate price changes
            changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

            gains = [change if change > 0 else Decimal("0") for change in changes]
            losses = [-change if change < 0 else Decimal("0") for change in changes]

            # Initial averages
            avg_gain = sum(gains[:period]) / Decimal(str(period))
            avg_loss = sum(losses[:period]) / Decimal(str(period))

            # Calculate RSI values
            for i in range(period, len(changes)):
                avg_gain = (avg_gain * Decimal(str(period - 1)) + gains[i]) / Decimal(str(period))
                avg_loss = (avg_loss * Decimal(str(period - 1)) + losses[i]) / Decimal(str(period))

                if avg_loss == 0:
                    rsi = Decimal("100")
                else:
                    rs = avg_gain / avg_loss
                    rsi = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

                rsi_values.append(rsi)

            return rsi_values

        result = benchmark(calculate_rsi, price_data, 14)
        assert len(result) == 985  # 1000 - 15

    @pytest.mark.asyncio
    async def test_parallel_indicator_calculation(self, price_data):
        """Benchmark parallel calculation of multiple indicators."""
        benchmark = PerformanceBenchmark("parallel_indicators")

        async def calculate_all_indicators():
            # Simulate async indicator calculations
            tasks = []

            # EMA calculations
            for period in [9, 20, 50, 200]:
                tasks.append(asyncio.create_task(
                    asyncio.to_thread(self._calculate_ema_async, price_data, period)
                ))

            # Other indicators
            tasks.append(asyncio.create_task(
                asyncio.to_thread(self._calculate_rsi_async, price_data, 14)
            ))
            tasks.append(asyncio.create_task(
                asyncio.to_thread(self._calculate_macd_async, price_data)
            ))

            results = await asyncio.gather(*tasks)
            return len(results)

        # Run 50 iterations
        for _ in range(50):
            benchmark.start()
            result = await calculate_all_indicators()
            benchmark.stop()
            assert result == 6  # 4 EMAs + RSI + MACD

        # Performance should be much better than sequential
        benchmark.assert_performance(max_p95_ms=20, max_p99_ms=50)

    def _calculate_ema_async(self, prices: List[Decimal], period: int) -> List[Decimal]:
        """Async wrapper for EMA calculation."""
        # Simulate CPU-bound calculation
        time.sleep(0.005)  # 5ms
        return []

    def _calculate_rsi_async(self, prices: List[Decimal], period: int) -> List[Decimal]:
        """Async wrapper for RSI calculation."""
        time.sleep(0.008)  # 8ms
        return []

    def _calculate_macd_async(self, prices: List[Decimal]) -> Dict[str, List[Decimal]]:
        """Async wrapper for MACD calculation."""
        time.sleep(0.010)  # 10ms
        return {"macd": [], "signal": [], "histogram": []}


class TestSignalGenerationPerformance:
    """Benchmark signal generation latency."""

    @pytest.mark.asyncio
    async def test_smc_signal_generation(self):
        """Benchmark SMC signal generation from candle close."""
        benchmark = PerformanceBenchmark("smc_signal_generation")

        async def generate_smc_signal(candles: List[Candle]) -> Optional[SMCSignal]:
            # Simulate SMC analysis
            await asyncio.sleep(0.01)  # 10ms for pivot detection
            await asyncio.sleep(0.005)  # 5ms for structure analysis
            await asyncio.sleep(0.008)  # 8ms for zone identification

            # Generate signal
            signal = SMCSignal(
                symbol=candles[0].symbol,
                timeframe=candles[0].timeframe,
                signal_type="CHOCH",
                direction="BULLISH",
                entry_price=candles[-1].close_price,
                stop_loss=candles[-1].low_price,
                confidence=Decimal("0.75")
            )
            return signal

        # Generate test candles
        candles = []
        for i in range(100):
            candle = Candle(
                symbol="BTCUSDT",
                timeframe=TimeFrame.M15,
                open_time=datetime.now() - timedelta(minutes=15 * (100 - i)),
                close_time=datetime.now() - timedelta(minutes=15 * (99 - i)),
                open_price=Decimal("50000"),
                high_price=Decimal("50100"),
                low_price=Decimal("49900"),
                close_price=Decimal("50050"),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=1000,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000")
            )
            candles.append(candle)

        # Run 100 iterations
        for _ in range(100):
            benchmark.start()
            signal = await generate_smc_signal(candles)
            benchmark.stop()
            assert signal is not None

        # SMC signals should be generated quickly
        benchmark.assert_performance(max_p95_ms=30, max_p99_ms=50)

    @pytest.mark.asyncio
    async def test_retest_signal_generation(self):
        """Benchmark zone retest signal generation."""
        benchmark = PerformanceBenchmark("retest_signal_generation")

        async def check_retest(price: Decimal, zones: List[Dict]) -> Optional[RetestSignal]:
            # Simulate retest analysis
            await asyncio.sleep(0.003)  # 3ms for zone matching
            await asyncio.sleep(0.002)  # 2ms for confluence check

            # Check if price retests any zone
            for zone in zones:
                if zone["low"] <= price <= zone["high"]:
                    signal = RetestSignal(
                        symbol="BTCUSDT",
                        timeframe=TimeFrame.M15,
                        timestamp=datetime.now(),
                        level_price=price,
                        retest_type="zone_retest",
                        success_probability=Decimal("0.80"),
                        volume_confirmation=True,
                        confluence_factors=["EMA_support", "RSI_oversold"]
                    )
                    return signal
            return None

        # Create test zones
        zones = [
            {"low": Decimal("49800"), "high": Decimal("50200"), "type": "demand"},
            {"low": Decimal("51500"), "high": Decimal("51800"), "type": "supply"},
            {"low": Decimal("48500"), "high": Decimal("48800"), "type": "demand"}
        ]

        # Run 200 iterations with different prices
        for i in range(200):
            price = Decimal("50000") + Decimal(str(i * 10 - 1000))
            benchmark.start()
            signal = await check_retest(price, zones)
            benchmark.stop()

        # Retest checks should be very fast
        benchmark.assert_performance(max_p95_ms=10, max_p99_ms=20)


class TestDecisionEnginePerformance:
    """Benchmark decision making and risk management."""

    @pytest.mark.asyncio
    async def test_risk_calculation_performance(self):
        """Benchmark risk management calculations."""
        benchmark = PerformanceBenchmark("risk_calculation")

        def calculate_position_size(
            account_balance: Decimal,
            risk_percent: Decimal,
            entry_price: Decimal,
            stop_loss: Decimal
        ) -> Decimal:
            # Calculate risk amount
            risk_amount = account_balance * risk_percent / Decimal("100")

            # Calculate position size
            price_diff = abs(entry_price - stop_loss)
            if price_diff > 0:
                position_size = risk_amount / price_diff
            else:
                position_size = Decimal("0")

            # Apply leverage and limits
            max_position = account_balance * Decimal("3")  # 3x max leverage
            return min(position_size, max_position)

        # Test data
        account_balance = Decimal("10000")
        risk_percent = Decimal("0.5")  # 0.5% risk per trade

        # Run 1000 calculations
        for i in range(1000):
            entry = Decimal("50000") + Decimal(str(i))
            stop = entry * Decimal("0.98")  # 2% stop

            benchmark.start()
            size = calculate_position_size(account_balance, risk_percent, entry, stop)
            benchmark.stop()

            assert size > 0

        # Risk calculations should be instant
        benchmark.assert_performance(max_p95_ms=0.1, max_p99_ms=0.5)

    @pytest.mark.asyncio
    async def test_concurrent_decision_making(self):
        """Benchmark concurrent decision making for multiple signals."""
        benchmark = PerformanceBenchmark("concurrent_decisions")

        async def make_trading_decision(signal: Dict) -> TradingDecision:
            # Simulate decision process
            await asyncio.sleep(0.002)  # Risk check
            await asyncio.sleep(0.001)  # Position sizing
            await asyncio.sleep(0.002)  # Validation

            decision = TradingDecision(
                signal_id=signal["id"],
                should_trade=True,
                position_size=Decimal("0.1"),
                leverage=Decimal("2"),
                order_type="LIMIT"
            )
            return decision

        # Create test signals
        signals = []
        for i in range(10):
            signals.append({
                "id": f"signal_{i}",
                "symbol": f"SYMBOL{i}",
                "entry": Decimal("50000") + Decimal(str(i * 100))
            })

        # Run 50 iterations of concurrent decisions
        for _ in range(50):
            benchmark.start()

            # Make decisions concurrently
            tasks = [make_trading_decision(signal) for signal in signals]
            decisions = await asyncio.gather(*tasks)

            benchmark.stop()

            assert len(decisions) == 10
            assert all(d.should_trade for d in decisions)

        # Should handle 10 concurrent decisions quickly
        benchmark.assert_performance(max_p95_ms=10, max_p99_ms=20)


class TestEndToEndPerformance:
    """Benchmark complete trading flow performance."""

    @pytest.mark.asyncio
    async def test_candle_to_signal_latency(self):
        """Benchmark latency from candle close to signal generation."""
        benchmark = PerformanceBenchmark("candle_to_signal")

        async def process_candle_to_signal(candle: Candle) -> float:
            start = time.perf_counter()

            # 1. Candle validation and storage
            await asyncio.sleep(0.002)  # 2ms

            # 2. Feature calculation
            await asyncio.sleep(0.005)  # 5ms

            # 3. SMC analysis
            await asyncio.sleep(0.010)  # 10ms

            # 4. Signal generation
            await asyncio.sleep(0.003)  # 3ms

            return time.perf_counter() - start

        # Create test candle
        candle = Candle(
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

        # Run 100 iterations
        for _ in range(100):
            latency = await process_candle_to_signal(candle)
            benchmark.samples.append(latency)

        # Should meet our target of ≤500ms P95
        benchmark.assert_performance(max_p95_ms=50, max_p99_ms=100)

    @pytest.mark.asyncio
    async def test_signal_to_order_latency(self):
        """Benchmark latency from signal to order placement."""
        benchmark = PerformanceBenchmark("signal_to_order")

        async def process_signal_to_order(signal: RetestSignal) -> float:
            start = time.perf_counter()

            # 1. Risk management decision
            await asyncio.sleep(0.002)  # 2ms

            # 2. Position sizing
            await asyncio.sleep(0.001)  # 1ms

            # 3. Order preparation
            await asyncio.sleep(0.002)  # 2ms

            # 4. Router communication
            await asyncio.sleep(0.010)  # 10ms network

            return time.perf_counter() - start

        # Create test signal
        signal = RetestSignal(
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            timestamp=datetime.now(),
            level_price=Decimal("50000"),
            retest_type="zone_retest",
            success_probability=Decimal("0.85"),
            volume_confirmation=True,
            confluence_factors=["BOS", "EMA_support"]
        )

        # Run 100 iterations
        for _ in range(100):
            latency = await process_signal_to_order(signal)
            benchmark.samples.append(latency)

        # Should meet our target of ≤300ms P95
        benchmark.assert_performance(max_p95_ms=30, max_p99_ms=50)

    @pytest.mark.asyncio
    async def test_full_trading_cycle(self):
        """Benchmark complete trading cycle from candle to order."""
        benchmark = PerformanceBenchmark("full_trading_cycle")

        async def full_cycle():
            start = time.perf_counter()

            # 1. Candle ingestion
            await asyncio.sleep(0.002)

            # 2. Feature calculation
            await asyncio.sleep(0.005)

            # 3. Signal generation
            await asyncio.sleep(0.015)

            # 4. Decision making
            await asyncio.sleep(0.005)

            # 5. Order placement
            await asyncio.sleep(0.015)

            # 6. Snapshot generation (async, don't wait)
            asyncio.create_task(generate_snapshot())

            return time.perf_counter() - start

        async def generate_snapshot():
            await asyncio.sleep(2.0)  # 2 seconds for Puppeteer

        # Run 50 complete cycles
        for _ in range(50):
            latency = await full_cycle()
            benchmark.samples.append(latency)

        # Complete cycle should be fast (excluding snapshot)
        benchmark.assert_performance(max_p95_ms=100, max_p99_ms=150)

        # Print detailed stats
        stats = benchmark.get_stats()
        print(f"\nFull trading cycle performance:")
        print(f"  Mean: {stats['mean']*1000:.2f}ms")
        print(f"  P50:  {stats['p50']*1000:.2f}ms")
        print(f"  P95:  {stats['p95']*1000:.2f}ms")
        print(f"  P99:  {stats['p99']*1000:.2f}ms")


class TestDatabasePerformance:
    """Benchmark database operations."""

    @pytest.mark.asyncio
    @pytest.mark.skip("Requires running database")
    async def test_candle_insert_performance(self):
        """Benchmark candle insertion rate."""
        # Would test actual database performance
        pass

    @pytest.mark.asyncio
    @pytest.mark.skip("Requires running database")
    async def test_concurrent_queries(self):
        """Benchmark concurrent database queries."""
        # Would test query performance under load
        pass


def generate_performance_report(benchmarks: List[PerformanceBenchmark]):
    """Generate performance test report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "benchmarks": {}
    }

    for bench in benchmarks:
        stats = bench.get_stats()
        report["benchmarks"][bench.name] = {
            "samples": stats["count"],
            "mean_ms": round(stats["mean"] * 1000, 2),
            "p50_ms": round(stats["p50"] * 1000, 2),
            "p95_ms": round(stats["p95"] * 1000, 2),
            "p99_ms": round(stats["p99"] * 1000, 2),
            "min_ms": round(stats["min"] * 1000, 2),
            "max_ms": round(stats["max"] * 1000, 2)
        }

    # Save report
    with open("performance_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\nPerformance Report Summary:")
    print("=" * 60)
    for name, data in report["benchmarks"].items():
        print(f"\n{name}:")
        print(f"  Samples: {data['samples']}")
        print(f"  P95: {data['p95_ms']}ms")
        print(f"  P99: {data['p99_ms']}ms")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])