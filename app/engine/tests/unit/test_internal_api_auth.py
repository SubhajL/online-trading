from __future__ import annotations

from fastapi.testclient import TestClient

from app.engine.main import app, services


class _CapturingBus:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish(self, event: object, priority: int = 0) -> bool:
        _ = priority
        self.events.append(event)
        return True


def test_internal_order_update_requires_bearer_token(monkeypatch) -> None:
    previous = dict(services)
    services.clear()
    try:
        services["event_bus"] = _CapturingBus()
        monkeypatch.setenv("ENGINE_INTERNAL_API_TOKEN", "engine-secret")

        client = TestClient(app)
        response = client.post(
            "/internal/order_update",
            json={
                "event_type": "order_update.v1",
                "venue": "SPOT",
                "symbol": "BTCUSDT",
                "order_id": 123,
                "client_order_id": "abc_entry",
                "status": "NEW",
                "side": "BUY",
                "order_type": "LIMIT",
                "price": "50000.00",
                "quantity": "0.01",
                "executed_qty": "0",
            },
        )

        assert response.status_code == 401
    finally:
        services.clear()
        services.update(previous)


def test_control_service_requires_bearer_token(monkeypatch) -> None:
    previous = dict(services)
    services.clear()
    try:
        monkeypatch.setenv("ENGINE_INTERNAL_API_TOKEN", "engine-secret")

        client = TestClient(app)
        response = client.post(
            "/control/service",
            json={"action": "start", "service": None},
        )

        assert response.status_code == 401
    finally:
        services.clear()
        services.update(previous)
