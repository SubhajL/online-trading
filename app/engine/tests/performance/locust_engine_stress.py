"""
Focused stress tests for trading engine critical paths.

Tests high-load scenarios for:
- Candle ingestion pipeline
- Signal generation under load
- Concurrent decision making
- Database performance

Usage:
    # Test candle ingestion at high rate
    locust -f locust_engine_stress.py --host http://localhost:8001 --users 50 --spawn-rate 10 --run-time 5m --tags candles

    # Test decision engine under load
    locust -f locust_engine_stress.py --host http://localhost:8001 --users 100 --spawn-rate 20 --run-time 10m --tags decisions
"""

import json
import time
import random
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any

from locust import HttpUser, task, between, tag, events
from locust.exception import RescheduleTask
import numpy as np


class CandleIngestionStress(HttpUser):
    """Stress test candle ingestion and processing pipeline."""

    wait_time = between(0.01, 0.1)  # Very high frequency

    def on_start(self):
        """Initialize test data."""
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT",
                       "DOTUSDT", "AVAXUSDT", "MATICUSDT", "LINKUSDT", "ATOMUSDT"]
        self.timeframes = ["1m", "5m", "15m", "1h", "4h"]

    @task
    @tag("candles")
    def ingest_candle_burst(self):
        """Simulate burst of candle data."""
        # Generate multiple candles at once
        candles = []
        base_time = datetime.now() - timedelta(minutes=15)
        base_price = Decimal("50000")

        for i in range(10):  # Burst of 10 candles
            symbol = random.choice(self.symbols)
            timeframe = random.choice(self.timeframes)

            # Generate realistic OHLCV data
            open_price = base_price + Decimal(str(random.randint(-100, 100)))
            high_price = open_price + Decimal(str(random.randint(0, 50)))
            low_price = open_price - Decimal(str(random.randint(0, 50)))
            close_price = low_price + Decimal(str(random.randint(0, int(high_price - low_price))))

            candle = {
                "symbol": symbol,
                "timeframe": timeframe,
                "open_time": int((base_time + timedelta(minutes=i)).timestamp() * 1000),
                "close_time": int((base_time + timedelta(minutes=i+1)).timestamp() * 1000),
                "open": float(open_price),
                "high": float(high_price),
                "low": float(low_price),
                "close": float(close_price),
                "volume": float(Decimal(str(random.randint(100, 10000)))),
                "closed": True
            }
            candles.append(candle)

        # Send burst of candles
        start_time = time.time()
        with self.client.post("/api/candles/bulk", json={"candles": candles}, catch_response=True) as response:
            if response.status_code in [200, 201, 202]:
                response.success()
                # Track ingestion rate
                elapsed = time.time() - start_time
                rate = len(candles) / elapsed
                if rate < 100:  # Less than 100 candles/second is slow
                    response.failure(f"Slow ingestion rate: {rate:.2f} candles/sec")
            else:
                response.failure(f"Bulk candle ingestion failed: {response.status_code}")

    @task
    @tag("candles", "database")
    def concurrent_candle_queries(self):
        """Test concurrent candle queries."""
        # Query different symbols/timeframes simultaneously
        tasks = []
        for _ in range(5):  # 5 concurrent queries
            symbol = random.choice(self.symbols)
            timeframe = random.choice(self.timeframes)

            params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": 500  # Large query
            }

            with self.client.get("/api/candles", params=params, catch_response=True) as response:
                if response.status_code == 200:
                    candles = response.json()
                    if len(candles) > 0:
                        response.success()
                    else:
                        response.failure("No candles returned")
                else:
                    response.failure(f"Candle query failed: {response.status_code}")


class SignalGenerationStress(HttpUser):
    """Stress test signal generation under high load."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Initialize test parameters."""
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.current_prices = {
            "BTCUSDT": 50000,
            "ETHUSDT": 3000,
            "SOLUSDT": 100
        }

    @task
    @tag("signals", "features")
    def concurrent_feature_calculation(self):
        """Test concurrent feature calculation."""
        symbol = random.choice(self.symbols)

        # Request multiple indicators simultaneously
        endpoints = [
            f"/api/indicators/ema?symbol={symbol}&period=20",
            f"/api/indicators/rsi?symbol={symbol}&period=14",
            f"/api/indicators/macd?symbol={symbol}",
            f"/api/indicators/bb?symbol={symbol}",
            f"/api/indicators/atr?symbol={symbol}&period=14"
        ]

        start_time = time.time()
        responses = []

        for endpoint in endpoints:
            with self.client.get(endpoint) as response:
                responses.append(response)

        # Check all succeeded and were fast
        elapsed = time.time() - start_time
        if all(r.status_code == 200 for r in responses) and elapsed < 1.0:
            events.request_success.fire(
                request_type="Features",
                name="concurrent_indicators",
                response_time=elapsed * 1000,
                response_length=sum(len(r.content) for r in responses)
            )
        else:
            events.request_failure.fire(
                request_type="Features",
                name="concurrent_indicators",
                response_time=elapsed * 1000,
                response_length=0,
                exception=f"Slow or failed indicators: {elapsed:.2f}s"
            )

    @task
    @tag("signals", "smc")
    def stress_smc_calculations(self):
        """Stress test SMC calculations."""
        symbol = random.choice(self.symbols)

        # Request SMC analysis with different lookbacks
        lookbacks = [50, 100, 200, 500]

        for lookback in lookbacks:
            params = {
                "symbol": symbol,
                "timeframe": "15m",
                "lookback": lookback
            }

            with self.client.get("/api/smc/analyze", params=params, catch_response=True) as response:
                if response.status_code == 200:
                    data = response.json()
                    # Verify we got reasonable results
                    if "pivots" in data and "zones" in data:
                        response.success()
                    else:
                        response.failure("Invalid SMC response")
                else:
                    response.failure(f"SMC analysis failed: {response.status_code}")

    @task
    @tag("signals")
    def rapid_signal_generation(self):
        """Generate signals rapidly to test throughput."""
        symbol = random.choice(self.symbols)
        base_price = self.current_prices[symbol]

        # Generate 10 signals in rapid succession
        for i in range(10):
            signal = {
                "symbol": symbol,
                "timeframe": "15m",
                "type": random.choice(["BUY", "SELL"]),
                "entry": base_price * (1 + random.uniform(-0.001, 0.001)),
                "stop_loss": base_price * 0.99,
                "take_profit": base_price * 1.01,
                "confidence": random.uniform(0.6, 0.9),
                "source": "stress_test",
                "timestamp": int(time.time() * 1000) + i
            }

            with self.client.post("/api/signals", json=signal, catch_response=True) as response:
                if response.status_code not in [200, 201]:
                    response.failure(f"Signal generation failed: {response.status_code}")


class DecisionEngineStress(HttpUser):
    """Stress test decision engine and risk management."""

    wait_time = between(0.05, 0.2)

    def on_start(self):
        """Initialize test state."""
        self.active_positions = {}
        self.account_balance = 10000

    @task
    @tag("decisions", "risk")
    def concurrent_decision_requests(self):
        """Test concurrent decision requests."""
        # Generate multiple decision requests
        decisions = []

        for i in range(5):  # 5 concurrent decisions
            symbol = random.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT"])

            decision_request = {
                "signal_id": f"stress_signal_{int(time.time() * 1000)}_{i}",
                "symbol": symbol,
                "signal_type": random.choice(["BUY", "SELL"]),
                "entry_price": 50000 * (1 + random.uniform(-0.01, 0.01)),
                "stop_loss": 49500,
                "take_profit": 50500,
                "confidence": random.uniform(0.6, 0.95),
                "account_balance": self.account_balance,
                "active_positions": len(self.active_positions)
            }

            start_time = time.time()
            with self.client.post("/api/decision/evaluate", json=decision_request, catch_response=True) as response:
                elapsed = time.time() - start_time

                if response.status_code == 200:
                    decision = response.json()
                    # Decision should be fast
                    if elapsed < 0.1:  # Less than 100ms
                        response.success()
                    else:
                        response.failure(f"Slow decision: {elapsed:.3f}s")

                    # Track decision
                    if decision.get("should_trade"):
                        self.active_positions[symbol] = decision.get("position_size", 0)
                else:
                    response.failure(f"Decision failed: {response.status_code}")

    @task
    @tag("decisions", "risk")
    def test_risk_limit_enforcement(self):
        """Test risk limits under high load."""
        # Try to exceed risk limits
        large_positions = []

        for i in range(10):  # Try 10 large positions
            decision_request = {
                "signal_id": f"risk_test_{i}",
                "symbol": "BTCUSDT",
                "signal_type": "BUY",
                "entry_price": 50000,
                "stop_loss": 45000,  # 10% stop loss
                "confidence": 0.9,
                "account_balance": self.account_balance,
                "active_positions": i  # Increasing positions
            }

            with self.client.post("/api/decision/evaluate", json=decision_request, catch_response=True) as response:
                if response.status_code == 200:
                    decision = response.json()
                    # Should reject after risk limit
                    if i > 3 and decision.get("should_trade"):
                        response.failure("Risk limit not enforced")
                    else:
                        response.success()


class DatabaseStress(HttpUser):
    """Stress test database operations."""

    wait_time = between(0.01, 0.05)  # Very high frequency

    @task
    @tag("database", "timescale")
    def concurrent_time_series_queries(self):
        """Test TimescaleDB under high query load."""
        # Multiple time-range queries
        queries = []

        for i in range(3):
            symbol = random.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
            hours_back = random.choice([1, 6, 24, 72])

            params = {
                "symbol": symbol,
                "start_time": int((datetime.now() - timedelta(hours=hours_back)).timestamp() * 1000),
                "end_time": int(datetime.now().timestamp() * 1000),
                "interval": "15m"
            }

            with self.client.get("/api/candles/range", params=params, catch_response=True) as response:
                if response.status_code == 200:
                    data = response.json()
                    expected_candles = hours_back * 4  # 15min candles
                    if len(data) > expected_candles * 0.8:  # At least 80% of expected
                        response.success()
                    else:
                        response.failure(f"Too few candles: {len(data)}/{expected_candles}")

    @task
    @tag("database", "aggregation")
    def stress_aggregation_queries(self):
        """Test complex aggregation queries."""
        symbol = random.choice(["BTCUSDT", "ETHUSDT"])

        # Complex aggregation query
        params = {
            "symbol": symbol,
            "timeframe": "1h",
            "aggregations": ["avg", "min", "max", "stddev"],
            "group_by": "day",
            "limit": 30
        }

        with self.client.get("/api/analytics/aggregates", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Aggregation failed: {response.status_code}")


class BurstLoadUser(HttpUser):
    """Simulate burst load patterns."""

    wait_time = between(0, 0.01)  # Extreme burst

    def on_start(self):
        self.burst_active = True
        self.burst_counter = 0

    @task
    def burst_requests(self):
        """Generate burst of requests."""
        if self.burst_active:
            self.burst_counter += 1

            # Rapid fire requests
            endpoints = [
                "/health/",
                "/api/ticker/BTCUSDT",
                "/api/candles?symbol=BTCUSDT&limit=10",
                "/metrics/"
            ]

            endpoint = endpoints[self.burst_counter % len(endpoints)]
            self.client.get(endpoint)

            # Stop burst after 100 requests
            if self.burst_counter >= 100:
                self.burst_active = False
                time.sleep(5)  # Rest period
                self.burst_active = True
                self.burst_counter = 0


# Monitoring and reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize test monitoring."""
    print(f"Starting stress test against {environment.host}")
    print(f"Users: {environment.parsed_options.num_users}")
    print(f"Spawn rate: {environment.parsed_options.spawn_rate}")


@events.request_success.add_listener
def track_response_times(request_type, name, response_time, response_length, **kwargs):
    """Track response time percentiles."""
    if response_time > 500:  # Log slow requests over 500ms
        print(f"⚠️  Slow {request_type} {name}: {response_time}ms")

    if response_time > 1000:  # Critical if over 1 second
        print(f"🚨 CRITICAL: {request_type} {name}: {response_time}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate final report."""
    print("\n" + "="*50)
    print("STRESS TEST SUMMARY")
    print("="*50)

    # Calculate percentiles
    if environment.stats.total.response_times:
        percentiles = np.percentile(
            list(environment.stats.total.response_times),
            [50, 90, 95, 99]
        )
        print(f"Response time percentiles (ms):")
        print(f"  50%: {percentiles[0]:.2f}")
        print(f"  90%: {percentiles[1]:.2f}")
        print(f"  95%: {percentiles[2]:.2f}")
        print(f"  99%: {percentiles[3]:.2f}")

    print(f"\nTotal requests: {environment.stats.total.num_requests}")
    print(f"Failed requests: {environment.stats.total.num_failures}")
    print(f"Failure rate: {environment.stats.total.fail_ratio:.2%}")
    print(f"Avg response time: {environment.stats.total.avg_response_time:.2f}ms")


if __name__ == "__main__":
    import os
    # Run with specific test scenario
    scenario = os.getenv("STRESS_SCENARIO", "all")

    if scenario == "candles":
        os.system("locust -f locust_engine_stress.py --host http://localhost:8001 -u 50 -r 10 -t 5m --headless --tags candles")
    elif scenario == "decisions":
        os.system("locust -f locust_engine_stress.py --host http://localhost:8001 -u 100 -r 20 -t 5m --headless --tags decisions")
    else:
        os.system("locust -f locust_engine_stress.py --host http://localhost:8001")