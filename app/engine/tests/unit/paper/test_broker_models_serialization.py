from datetime import datetime, timezone
from decimal import Decimal
import json

from app.engine.paper.broker import ClientOrderIDs, OrderUpdate, PlaceBracketResponse


def test_place_bracket_response_serialization():
    resp = PlaceBracketResponse(
        bracket_order_id="br_123",
        client_order_ids=ClientOrderIDs(
            main="co_main",
            take_profits=["co_tp1", "co_tp2"],
            stop_loss="co_sl",
        ),
        symbol="BTCUSDT",
        side="BUY",
        quantity=Decimal("1.23"),
        created_at=datetime.now(timezone.utc),
        partial_failure=False,
        errors=[],
    )
    d = json.loads(resp.model_dump_json())
    assert d["quantity"] == "1.23"
    assert "Z" in d["created_at"] or "+00:00" in d["created_at"]


def test_order_update_serialization():
    upd = OrderUpdate(
        event_type="order_update.v1",
        symbol="ETHUSDT",
        order_id=123,
        client_order_id="cli_1",
        status="FILLED",
        side="BUY",
        order_type="MARKET",
        price=Decimal("2500.01"),
        quantity=Decimal("2.0"),
        executed_qty=Decimal("2.0"),
        update_time=datetime.now(timezone.utc),
        reason=None,
    )
    d = json.loads(upd.model_dump_json())
    assert d["price"] == "2500.01"
    assert d["quantity"] == "2.0"
    assert d["executed_qty"] == "2.0"
    assert "Z" in d["update_time"] or "+00:00" in d["update_time"]
