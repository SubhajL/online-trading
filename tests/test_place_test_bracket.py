from __future__ import annotations

from decimal import Decimal
import importlib.util
from pathlib import Path
import sys


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "place_test_bracket.py"
    spec = importlib.util.spec_from_file_location("place_test_bracket", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_deferred_bracket_body_includes_client_order_ids():
    module = _load_module()

    body = module.build_deferred_bracket_body(
        "BTCUSDT",
        Decimal("50000"),
        "man-abc123",
        notional_usdt=Decimal("25"),
        entry_offset_bps=150,
    )

    # client_order_ids is the field that makes the router defer the exits and
    # reserve a durable bracket row — the whole point of the helper.
    assert body["client_order_ids"] == {
        "main": "man-abc123",
        "take_profits": ["man-abc123-tp1"],
        "stop_loss": "man-abc123-sl",
    }
    assert body["is_futures"] is False
    assert body["order_type"] == "LIMIT"


def test_build_deferred_bracket_body_prices_bracket_the_reference():
    module = _load_module()

    body = module.build_deferred_bracket_body(
        "BTCUSDT",
        Decimal("50000"),
        "man-x",
        notional_usdt=Decimal("25"),
        entry_offset_bps=150,
    )

    # offset = 150bps = 1.5%. Entry rests below, TP above, SL twice below.
    assert body["entry_price"] == "49250.00"
    assert body["take_profit_prices"] == ["50750.00"]
    assert body["stop_loss_price"] == "48500.00"
    # quantity = 25 / 49250 floored to 6dp
    assert body["quantity"] == "0.000507"


def test_build_deferred_bracket_body_leg_ids_derive_from_entry_id():
    module = _load_module()

    body = module.build_deferred_bracket_body(
        "ETHUSDT",
        Decimal("3000"),
        "man-zzz",
        notional_usdt=Decimal("30"),
    )

    assert body["client_order_ids"]["take_profits"][0].startswith("man-zzz")
    assert body["client_order_ids"]["stop_loss"].startswith("man-zzz")
