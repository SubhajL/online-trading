"""
Locust load tests for trading platform.

Tests the complete trading flow under load including:
- WebSocket data ingestion
- Signal generation
- Order placement
- Health checks and monitoring

Usage:
    locust -f locustfile.py --host http://localhost:8000
    locust -f locustfile.py --host http://localhost:8000 --headless -u 100 -r 10 -t 5m
"""

import json
import time
import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from locust import HttpUser, TaskSet, task, between, events
from locust.exception import RescheduleTask
import websocket
import threading


class TradingBehavior(TaskSet):
    """Simulates trading platform user behavior."""

    def on_start(self):
        """Called when a simulated user starts."""
        self.symbol = random.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
        self.timeframe = random.choice(["15m", "1h", "4h"])
        self.ws_client = None
        self.ws_thread = None
        self.positions = []

    def on_stop(self):
        """Called when a simulated user stops."""
        if self.ws_client:
            self.ws_client.close()

    @task(1)
    def check_health(self):
        """Health check endpoints."""
        # Basic health check
        with self.client.get("/health/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")

        # Detailed health status
        with self.client.get("/health/status", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "healthy":
                    response.success()
                elif data.get("status") == "degraded":
                    response.failure("System degraded")
                else:
                    response.failure("System unhealthy")

    @task(3)
    def get_market_data(self):
        """Get current market data."""
        # Get candles
        params = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "limit": 100
        }
        with self.client.get("/api/candles", params=params, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    response.success()
                else:
                    response.failure("No candle data returned")
            else:
                response.failure(f"Failed to get candles: {response.status_code}")

        # Get current price
        with self.client.get(f"/api/ticker/{self.symbol}", catch_response=True) as response:
            if response.status_code == 200:
                response.success()

    @task(2)
    def get_indicators(self):
        """Get technical indicators."""
        params = {
            "symbol": self.symbol,
            "timeframe": self.timeframe
        }
        with self.client.get("/api/indicators", params=params, catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                # Verify indicators are present
                expected_indicators = ["ema", "rsi", "macd", "atr", "bb"]
                if all(ind in data for ind in expected_indicators):
                    response.success()
                else:
                    response.failure("Missing indicators")

    @task(2)
    def get_smc_analysis(self):
        """Get Smart Money Concepts analysis."""
        params = {
            "symbol": self.symbol,
            "timeframe": self.timeframe
        }
        # Get SMC events
        with self.client.get("/api/smc/events", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()

        # Get zones
        with self.client.get("/api/smc/zones", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()

    @task(5)
    def simulate_signal_generation(self):
        """Simulate signal generation and order flow."""
        # Generate a mock signal
        current_price = self._get_current_price()
        if not current_price:
            raise RescheduleTask()

        signal_data = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "signal_type": random.choice(["BUY", "SELL"]),
            "entry_price": float(current_price),
            "stop_loss": float(current_price * Decimal("0.98")),
            "take_profit": float(current_price * Decimal("1.02")),
            "confidence": round(random.uniform(0.6, 0.95), 2),
            "source": random.choice(["zone_retest", "smc_confluence", "trend_continuation"])
        }

        # Post signal
        with self.client.post("/api/signals", json=signal_data, catch_response=True) as response:
            if response.status_code in [200, 201]:
                response.success()
                signal_id = response.json().get("id")

                # Simulate decision making
                self._simulate_decision(signal_data, signal_id)
            else:
                response.failure(f"Signal creation failed: {response.status_code}")

    def _get_current_price(self) -> Decimal:
        """Get current price for symbol."""
        response = self.client.get(f"/api/ticker/{self.symbol}")
        if response.status_code == 200:
            return Decimal(str(response.json().get("price", "0")))
        return None

    def _simulate_decision(self, signal_data: Dict[str, Any], signal_id: str):
        """Simulate decision engine processing."""
        # Check risk limits
        decision_request = {
            "signal_id": signal_id,
            "symbol": signal_data["symbol"],
            "signal_type": signal_data["signal_type"],
            "entry_price": signal_data["entry_price"],
            "stop_loss": signal_data["stop_loss"],
            "confidence": signal_data["confidence"]
        }

        with self.client.post("/api/decision", json=decision_request, catch_response=True) as response:
            if response.status_code == 200:
                decision = response.json()
                if decision.get("should_trade"):
                    response.success()
                    # Simulate order placement
                    self._simulate_order(decision)
                else:
                    response.success()  # Rejection is also valid
            else:
                response.failure(f"Decision failed: {response.status_code}")

    def _simulate_order(self, decision: Dict[str, Any]):
        """Simulate order placement."""
        order_data = {
            "symbol": decision["symbol"],
            "side": decision["side"],
            "type": "LIMIT",
            "quantity": decision["position_size"],
            "price": decision["entry_price"],
            "client_order_id": f"locust_{self.symbol}_{int(time.time() * 1000)}"
        }

        with self.client.post("/api/orders", json=order_data, catch_response=True) as response:
            if response.status_code in [200, 201]:
                response.success()
                order_id = response.json().get("order_id")
                self.positions.append({
                    "order_id": order_id,
                    "symbol": decision["symbol"],
                    "side": decision["side"],
                    "quantity": decision["position_size"]
                })
            else:
                response.failure(f"Order placement failed: {response.status_code}")

    @task(3)
    def check_positions(self):
        """Check current positions."""
        with self.client.get("/api/positions", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                positions = response.json()
                # Update local position tracking
                self.positions = positions.get("positions", [])

    @task(1)
    def get_account_info(self):
        """Get account information."""
        with self.client.get("/api/account", catch_response=True) as response:
            if response.status_code == 200:
                account = response.json()
                if "balance" in account:
                    response.success()
                else:
                    response.failure("Invalid account response")

    @task(2)
    def get_order_history(self):
        """Get order history."""
        params = {
            "symbol": self.symbol,
            "limit": 50
        }
        with self.client.get("/api/orders/history", params=params, catch_response=True) as response:
            if response.status_code == 200:
                response.success()

    @task(1)
    def get_metrics(self):
        """Get Prometheus metrics."""
        with self.client.get("/metrics/", catch_response=True) as response:
            if response.status_code == 200:
                # Verify it's Prometheus format
                if "# HELP" in response.text and "# TYPE" in response.text:
                    response.success()
                else:
                    response.failure("Invalid metrics format")

    @task(1)
    def simulate_chart_snapshot(self):
        """Simulate chart snapshot generation."""
        if not self.positions:
            raise RescheduleTask()

        # Pick a random position
        position = random.choice(self.positions)

        snapshot_request = {
            "signalId": f"signal_{int(time.time())}",
            "symbol": position["symbol"],
            "timeframe": self.timeframe,
            "signalData": {
                "type": position["side"],
                "entry": "50000",  # Mock price
                "stopLoss": "49000",
                "takeProfit": "52000"
            }
        }

        with self.client.post("/api/snapshots/generate", json=snapshot_request, catch_response=True) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Snapshot generation failed: {response.status_code}")


class WebSocketBehavior(TaskSet):
    """Simulates WebSocket connections for real-time data."""

    def on_start(self):
        """Connect to WebSocket on start."""
        self.symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.ws_url = self.client.base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.connect_websocket()

    def connect_websocket(self):
        """Connect to WebSocket for market data."""
        try:
            # Connect to market data WebSocket
            ws_market_url = f"{self.ws_url}/ws/market"
            self.ws_market = websocket.WebSocketApp(
                ws_market_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )

            # Run in background thread
            self.ws_thread = threading.Thread(target=self.ws_market.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()

        except Exception as e:
            events.request_failure.fire(
                request_type="WebSocket",
                name="connect",
                response_time=0,
                response_length=0,
                exception=e
            )

    def on_open(self, ws):
        """Subscribe to market data streams."""
        # Subscribe to candle streams
        for symbol in self.symbols:
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@kline_15m"],
                "id": int(time.time() * 1000)
            }
            ws.send(json.dumps(subscribe_msg))

        events.request_success.fire(
            request_type="WebSocket",
            name="connect",
            response_time=0,
            response_length=0
        )

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)

            # Track message latency
            if "E" in data:  # Event time
                latency = int(time.time() * 1000) - data["E"]
                events.request_success.fire(
                    request_type="WebSocket",
                    name="message",
                    response_time=latency,
                    response_length=len(message)
                )
        except Exception as e:
            events.request_failure.fire(
                request_type="WebSocket",
                name="message",
                response_time=0,
                response_length=0,
                exception=e
            )

    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        events.request_failure.fire(
            request_type="WebSocket",
            name="error",
            response_time=0,
            response_length=0,
            exception=error
        )

    def on_close(self, ws):
        """Handle WebSocket close."""
        pass

    @task
    def keep_alive(self):
        """Keep WebSocket alive with pings."""
        if hasattr(self, 'ws_market') and self.ws_market.sock and self.ws_market.sock.connected:
            self.ws_market.send(json.dumps({"method": "ping"}))
        else:
            # Reconnect if disconnected
            self.connect_websocket()

    def on_stop(self):
        """Clean up WebSocket on stop."""
        if hasattr(self, 'ws_market'):
            self.ws_market.close()


class TradingUser(HttpUser):
    """Simulated trading platform user."""

    # Wait between 1 and 5 seconds between tasks
    wait_time = between(1, 5)

    # Mix of behaviors
    tasks = {
        TradingBehavior: 8,  # 80% regular trading behavior
        WebSocketBehavior: 2  # 20% WebSocket connections
    }

    def on_start(self):
        """Initialize user session."""
        # Could add authentication here if needed
        pass


class HighFrequencyTradingUser(HttpUser):
    """Simulated high-frequency trading bot."""

    # Much shorter wait times
    wait_time = between(0.1, 0.5)

    class tasks(TaskSet):
        @task(10)
        def rapid_market_data(self):
            """Rapidly fetch market data."""
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
            symbol = random.choice(symbols)

            # Get ticker
            self.client.get(f"/api/ticker/{symbol}")

            # Get order book
            self.client.get(f"/api/orderbook/{symbol}")

        @task(5)
        def rapid_signal_check(self):
            """Rapidly check for signals."""
            self.client.get("/api/signals/latest")

        @task(2)
        def rapid_position_check(self):
            """Check positions frequently."""
            self.client.get("/api/positions")


# Custom event handlers for better reporting
@events.request_success.add_listener
def on_request_success(request_type, name, response_time, response_length, **kwargs):
    """Log successful requests."""
    if response_time > 1000:  # Log slow requests
        print(f"Slow request: {request_type} {name} took {response_time}ms")


@events.request_failure.add_listener
def on_request_failure(request_type, name, response_time, response_length, exception, **kwargs):
    """Log failed requests."""
    print(f"Request failed: {request_type} {name} - {exception}")


if __name__ == "__main__":
    import os
    os.system("locust -f locustfile.py --host http://localhost:8000")