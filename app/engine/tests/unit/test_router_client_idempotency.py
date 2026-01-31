"""Tests for router client idempotency with newClientOrderId."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.engine.adapters.router_client.http_client import RouterHTTPClient
from app.engine.decision.idempotency import generate_client_order_id
from app.engine.models import OrderType, TradingDecision

EXPECTED_CAPTURED_COUNT = 2


class TestRouterClientIdempotency:
    """Tests for newClientOrderId in order placement."""

    @pytest.fixture
    def router_client(self) -> RouterHTTPClient:
        """Create a router client for testing."""
        client = RouterHTTPClient(
            base_url="http://localhost:8001",
            timeout=10,
            retry_attempts=1,
        )
        client._initialized = True
        return client

    @pytest.fixture
    def sample_decision(self) -> TradingDecision:
        """Create a sample trading decision."""
        return TradingDecision(
            decision_id=UUID("12345678-1234-5678-1234-567812345678"),
            venue="SPOT",
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            action="BUY",
            entry_price=Decimal("50000.00"),
            quantity=Decimal("0.1"),
            order_type=OrderType.MARKET,
            stop_loss=Decimal("49000.00"),
            take_profit=Decimal("52000.00"),
            confidence=Decimal("0.85"),
            reasoning="SMC retest pattern detected",
        )

    @pytest.mark.asyncio
    async def test_place_order_includes_new_client_order_id(
        self,
        router_client: RouterHTTPClient,
        sample_decision: TradingDecision,
    ) -> None:
        """place_order includes newClientOrderId in request."""
        captured_data: dict[str, Any] | None = None

        async def capture_request(
            _method: str,
            _endpoint: str,
            data: dict[str, Any] | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            nonlocal captured_data
            captured_data = data
            return {"success": True, "orderId": "12345"}

        router_client._make_request = AsyncMock(side_effect=capture_request)  # type: ignore[method-assign]

        await router_client.place_order(sample_decision)

        assert captured_data is not None
        assert "newClientOrderId" in captured_data

        expected_id = generate_client_order_id(sample_decision.decision_id, "entry")
        assert captured_data["newClientOrderId"] == expected_id

    @pytest.mark.asyncio
    async def test_place_order_client_id_is_deterministic(
        self,
        router_client: RouterHTTPClient,
        sample_decision: TradingDecision,
    ) -> None:
        """Same decision produces same client order ID on retry."""
        captured_ids: list[str] = []

        async def capture_request(
            _method: str,
            _endpoint: str,
            data: dict[str, Any] | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            if data and "newClientOrderId" in data:
                captured_ids.append(data["newClientOrderId"])
            return {"success": True, "orderId": "12345"}

        router_client._make_request = AsyncMock(side_effect=capture_request)  # type: ignore[method-assign]

        await router_client.place_order(sample_decision)
        await router_client.place_order(sample_decision)

        assert len(captured_ids) == EXPECTED_CAPTURED_COUNT
        assert captured_ids[0] == captured_ids[1]

    @pytest.mark.asyncio
    async def test_place_order_client_id_unique_per_decision(
        self,
        router_client: RouterHTTPClient,
    ) -> None:
        """Different decisions produce different client order IDs."""
        captured_ids: list[str] = []

        async def capture_request(
            _method: str,
            _endpoint: str,
            data: dict[str, Any] | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            if data and "newClientOrderId" in data:
                captured_ids.append(data["newClientOrderId"])
            return {"success": True, "orderId": "12345"}

        router_client._make_request = AsyncMock(side_effect=capture_request)  # type: ignore[method-assign]

        decision1 = TradingDecision(
            decision_id=UUID("11111111-1111-1111-1111-111111111111"),
            venue="SPOT",
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            action="BUY",
            confidence=Decimal("0.85"),
            reasoning="Signal 1",
        )

        decision2 = TradingDecision(
            decision_id=UUID("22222222-2222-2222-2222-222222222222"),
            venue="SPOT",
            symbol="BTCUSDT",
            timestamp=datetime.now(UTC),
            action="BUY",
            confidence=Decimal("0.85"),
            reasoning="Signal 2",
        )

        await router_client.place_order(decision1)
        await router_client.place_order(decision2)

        assert len(captured_ids) == EXPECTED_CAPTURED_COUNT
        assert captured_ids[0] != captured_ids[1]

    @pytest.mark.asyncio
    async def test_place_bracket_order_posts_to_place_bracket_endpoint(
        self,
        router_client: RouterHTTPClient,
    ) -> None:
        captured_endpoints: list[str] = []
        captured_payloads: list[dict[str, Any]] = []

        async def capture_request(
            _method: str,
            endpoint: str,
            data: dict[str, Any] | None = None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            captured_endpoints.append(endpoint)
            captured_payloads.append(data or {})
            return {"success": True}

        router_client._make_request = AsyncMock(side_effect=capture_request)  # type: ignore[method-assign]

        payload = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "quantity": "0.01",
            "entry_price": "50000.0",
            "take_profit_prices": ["52000.0"],
            "stop_loss_price": "49000.0",
            "order_type": "LIMIT",
            "is_futures": True,
            "metadata": {"signal_id": "sig_123", "timeframe": "15m"},
            "client_order_ids": {
                "main": "abc_entry",
                "take_profits": ["abc_tp1"],
                "stop_loss": "abc_sl",
            },
        }

        await router_client.place_bracket_order(payload)

        assert captured_endpoints == ["/place_bracket"]
        assert captured_payloads[0]["metadata"]["signal_id"] == "sig_123"
