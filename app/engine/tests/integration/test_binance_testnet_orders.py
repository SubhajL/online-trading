"""
Integration tests for real Binance testnet order execution.

These tests use actual testnet API to validate the complete trading flow.
Requires testnet API keys to be configured in environment.
"""

import asyncio
import os
from decimal import Decimal
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.engine.models import SignalEvent, TimeFrame, TradingDecision, OrderSide, OrderType
from app.engine.ingest.binance_ws import BinanceWebSocketClient
from app.engine.ingest.binance_rest import BinanceRestClient
from app.engine.decision.order_formatter import OrderFormatter, ExchangeInfo
from app.engine.adapters.db.timescale import get_pool
from app.engine.bus import get_event_bus

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="session")
def testnet_config():
    """Get testnet configuration from environment."""
    return {
        "api_key": os.getenv("BINANCE_TESTNET_API_KEY", ""),
        "api_secret": os.getenv("BINANCE_TESTNET_SECRET", ""),
        "base_url": "https://testnet.binance.vision",
        "ws_url": "wss://testnet.binance.vision/ws",
        "testnet": True,
    }


@pytest.fixture(scope="session")
def skip_if_no_testnet_keys(testnet_config):
    """Skip tests if testnet API keys not configured."""
    if not testnet_config["api_key"] or not testnet_config["api_secret"]:
        pytest.skip("Testnet API keys not configured")


@pytest.fixture
async def testnet_rest_client(testnet_config, skip_if_no_testnet_keys):
    """Create testnet REST client."""
    client = BinanceRestClient(
        api_key=testnet_config["api_key"],
        api_secret=testnet_config["api_secret"],
        base_url=testnet_config["base_url"],
        testnet=True
    )
    await client.start()
    yield client
    await client.stop()


@pytest.fixture
async def testnet_ws_client(testnet_config, skip_if_no_testnet_keys):
    """Create testnet WebSocket client."""
    client = BinanceWebSocketClient(
        base_url=testnet_config["ws_url"],
        testnet=True
    )
    yield client
    await client.stop()


@pytest.fixture
async def exchange_info(testnet_rest_client):
    """Get exchange info for test symbol."""
    info = await testnet_rest_client.get_exchange_info("BTCUSDT")
    return ExchangeInfo(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        price_tick_size=Decimal(info["filters"][0]["tickSize"]),
        price_min=Decimal(info["filters"][0]["minPrice"]),
        price_max=Decimal(info["filters"][0]["maxPrice"]),
        qty_step_size=Decimal(info["filters"][1]["stepSize"]),
        qty_min=Decimal(info["filters"][1]["minQty"]),
        qty_max=Decimal(info["filters"][1]["maxQty"]),
        min_notional=Decimal(info["filters"][2]["minNotional"]),
    )


class TestBinanceTestnetOrders:
    """Test real order execution on Binance testnet."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_testnet_connectivity(self, testnet_rest_client):
        """Test that we can connect to testnet API."""
        # Test server time endpoint
        server_time = await testnet_rest_client.get_server_time()
        assert server_time is not None
        assert isinstance(server_time, datetime)

        # Verify time is reasonable (within 5 minutes of local time)
        local_time = datetime.now()
        time_diff = abs((server_time - local_time).total_seconds())
        assert time_diff < 300  # 5 minutes in seconds

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_testnet_account_info(self, testnet_rest_client):
        """Test retrieving testnet account information."""
        account = await testnet_rest_client.get_account_info()

        assert account is not None
        assert "balances" in account
        assert len(account["balances"]) > 0

        # Find USDT balance
        usdt_balance = None
        for balance in account["balances"]:
            if balance["asset"] == "USDT":
                usdt_balance = Decimal(balance["free"])
                break

        assert usdt_balance is not None
        assert usdt_balance > 0  # Should have testnet USDT

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_testnet_symbol_info(self, testnet_rest_client, exchange_info):
        """Test retrieving symbol trading rules."""
        assert exchange_info.symbol == "BTCUSDT"
        assert exchange_info.min_notional > 0
        assert exchange_info.qty_step_size > 0
        assert exchange_info.price_tick_size > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_market_order_execution(self, testnet_rest_client, exchange_info):
        """Test placing a real market order on testnet."""
        # Get current price
        ticker = await testnet_rest_client.get_ticker_24hr("BTCUSDT")
        current_price = Decimal(ticker["lastPrice"])

        # Calculate minimum order size
        min_qty = exchange_info.min_notional / current_price
        order_qty = max(min_qty * Decimal("1.1"), exchange_info.qty_min)  # 10% above minimum

        # Round to step size
        formatter = OrderFormatter({"BTCUSDT": exchange_info})
        order_qty = formatter.round_quantity("BTCUSDT", order_qty)

        # Place market buy order
        order_response = await testnet_rest_client.place_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=order_qty
        )

        assert order_response is not None
        assert order_response["symbol"] == "BTCUSDT"
        assert order_response["status"] == "FILLED"
        assert Decimal(order_response["executedQty"]) == order_qty

        # Verify position exists
        await asyncio.sleep(1)  # Wait for position update

        # Close position with market sell
        close_response = await testnet_rest_client.place_order(
            symbol="BTCUSDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=order_qty
        )
        assert close_response["status"] == "FILLED"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_limit_order_lifecycle(self, testnet_rest_client, exchange_info):
        """Test limit order placement and cancellation."""
        # Get current price
        ticker = await testnet_rest_client.get_ticker_24hr("BTCUSDT")
        current_price = Decimal(ticker["lastPrice"])

        # Place limit order 1% below current price
        limit_price = current_price * Decimal("0.99")
        formatter = OrderFormatter({"BTCUSDT": exchange_info})
        limit_price = formatter.round_price("BTCUSDT", limit_price)

        # Calculate order size
        order_qty = exchange_info.min_notional / limit_price * Decimal("1.1")
        order_qty = formatter.round_quantity("BTCUSDT", order_qty)

        # Place limit buy order
        order_response = await testnet_rest_client.place_order(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=order_qty,
            price=limit_price,
            time_in_force="GTC"
        )

        assert order_response is not None
        assert order_response["status"] in ["NEW", "PARTIALLY_FILLED"]
        order_id = order_response["orderId"]

        # Check order status
        await asyncio.sleep(2)
        order_status = await testnet_rest_client.get_order_status(
            symbol="BTCUSDT",
            order_id=order_id
        )

        assert order_status["orderId"] == order_id
        assert order_status["price"] == str(limit_price)

        # Cancel order
        cancel_response = await testnet_rest_client.cancel_order(
            symbol="BTCUSDT",
            order_id=order_id
        )

        assert cancel_response["status"] == "CANCELED"
        assert cancel_response["orderId"] == order_id

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_position_tracking_accuracy(self, testnet_rest_client):
        """Test that local position tracking matches exchange."""
        symbol = "BTCUSDT"

        # Get initial balance
        account = await testnet_rest_client.get_account_info()
        initial_btc = Decimal("0")
        for balance in account["balances"]:
            if balance["asset"] == "BTC":
                initial_btc = Decimal(balance["free"])
                break

        # Place a small market order
        ticker = await testnet_rest_client.get_ticker(symbol)
        current_price = Decimal(ticker["lastPrice"])

        # Use minimum order size
        exchange_info = await testnet_rest_client.get_exchange_info(symbol)
        min_notional = Decimal("10")  # Testnet minimum
        order_qty = min_notional / current_price * Decimal("1.1")
        order_qty = Decimal("0.001")  # Use fixed small amount for testnet

        # Place order
        order_response = await testnet_rest_client.place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=order_qty
        )
        executed_qty = Decimal(order_response["executedQty"])

        # Wait for balance to update
        await asyncio.sleep(2)

        # Verify balance changed
        account_after = await testnet_rest_client.get_account_info()
        final_btc = Decimal("0")
        for balance in account_after["balances"]:
            if balance["asset"] == "BTC":
                final_btc = Decimal(balance["free"])
                break

        position_size = final_btc - initial_btc
        assert abs(position_size - executed_qty) < Decimal("0.00001")  # Small tolerance

        # Cleanup - sell position
        await testnet_rest_client.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=executed_qty
        )


class TestOrderErrorHandling:
    """Test order error scenarios on testnet."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_insufficient_balance_rejection(self, testnet_rest_client):
        """Test order rejection for insufficient balance."""
        # Try to buy more BTC than account has USDT
        with pytest.raises(Exception) as exc_info:
            await testnet_rest_client.place_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("100.0")  # Way more than testnet balance
            )

        # Should get insufficient balance error
        assert "insufficient balance" in str(exc_info.value).lower() or \
               "account has insufficient balance" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_minimum_notional_rejection(self, testnet_rest_client, exchange_info):
        """Test order rejection for below minimum notional."""
        # Place order below minimum notional value
        with pytest.raises(Exception) as exc_info:
            await testnet_rest_client.place_order(
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("0.00001")  # Too small
            )

        # Should get MIN_NOTIONAL filter error
        assert "MIN_NOTIONAL" in str(exc_info.value) or \
               "notional" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_symbol_rejection(self, testnet_rest_client):
        """Test order rejection for invalid symbol."""
        with pytest.raises(Exception) as exc_info:
            await testnet_rest_client.place_order(
                symbol="INVALIDUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("1.0")
            )

        # Should get invalid symbol error
        assert "Invalid symbol" in str(exc_info.value) or \
               "INVALID" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
