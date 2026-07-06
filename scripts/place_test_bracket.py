#!/usr/bin/env python3
"""Place one deferred spot bracket against the router to exercise C5/C6 by hand.

The UI/BFF path cannot drive the deferred-legs code: the BFF omits
``client_order_ids`` when calling ``/place_bracket``, and the router only
defers exits (spot OCO on entry fill) and reserves a durable ``brackets`` row
when ``client_order_ids.main`` is set. This helper POSTs a bracket **with**
those ids so the entry-fill watcher (C5) and the startup reconciler (C6) have
something to act on. See docs/testnet-c5-c6-sanity-runbook.md.
"""

from __future__ import annotations

import argparse
from decimal import ROUND_DOWN, Decimal
import json
import os
import sys
from typing import Any
import urllib.error
import urllib.request
import uuid


def _format_decimal(value: Decimal, *, places: int) -> str:
    quantum = Decimal("1").scaleb(-places)
    return f"{value.quantize(quantum, rounding=ROUND_DOWN):f}"


def build_deferred_bracket_body(
    symbol: str,
    reference_price: Decimal,
    client_order_id: str,
    *,
    notional_usdt: Decimal,
    entry_offset_bps: int = 150,
) -> dict[str, Any]:
    """Build a resting-LIMIT BUY spot bracket that defers its exits.

    The entry sits ``entry_offset_bps`` below the reference so it rests then
    fills; the take-profit is symmetric above and the stop is twice the offset
    below. ``client_order_ids`` is what makes the router defer the exits.
    """
    offset = Decimal(entry_offset_bps) / Decimal("10000")
    entry_price = reference_price * (Decimal("1") - offset)
    take_profit_price = reference_price * (Decimal("1") + offset)
    stop_loss_price = reference_price * (Decimal("1") - offset * Decimal("2"))
    quantity = notional_usdt / entry_price
    return {
        "symbol": symbol,
        "side": "BUY",
        "quantity": _format_decimal(quantity, places=6),
        "entry_price": _format_decimal(entry_price, places=2),
        "take_profit_prices": [_format_decimal(take_profit_price, places=2)],
        "stop_loss_price": _format_decimal(stop_loss_price, places=2),
        "order_type": "LIMIT",
        "is_futures": False,
        "client_order_ids": {
            "main": client_order_id,
            "take_profits": [f"{client_order_id}-tp1"],
            "stop_loss": f"{client_order_id}-sl",
        },
    }


def _require_api_key() -> str:
    # The router compares the caller's token against SECURITY_REQUIRED_API_KEY;
    # ROUTER_API_KEY is what the BFF/soak send. They must match.
    key = os.getenv("SECURITY_REQUIRED_API_KEY") or os.getenv("ROUTER_API_KEY")
    if not key:
        print(
            "error: set SECURITY_REQUIRED_API_KEY (or ROUTER_API_KEY) to the router's token",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


def _fetch_reference_price(symbol: str) -> Decimal:
    base_url = os.getenv("BINANCE_SPOT_BASE_URL", "https://testnet.binance.vision").rstrip("/")
    url = f"{base_url}/api/v3/ticker/price?symbol={symbol}"
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - trusted testnet URL
        payload = json.loads(response.read().decode("utf-8"))
    price = payload.get("price")
    if not price:
        raise RuntimeError(f"price lookup response missing price: {payload}")
    return Decimal(str(price))


def _post_bracket(host: str, api_key: str, body: dict[str, Any]) -> tuple[int, Any]:
    request = urllib.request.Request(
        f"{host.rstrip('/')}/place_bracket",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Place one deferred spot bracket (C5/C6 sanity).")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--notional-usdt", default="25", help="Target entry notional in USDT")
    parser.add_argument("--entry-offset-bps", type=int, default=150)
    parser.add_argument(
        "--reference-price",
        help="Override the reference price instead of fetching the testnet ticker",
    )
    parser.add_argument("--host", default=os.getenv("ROUTER_HOST", "http://localhost:8001"))
    parser.add_argument(
        "--client-id",
        default=f"man-{uuid.uuid4().hex[:12]}",
        help="Client order id for the entry (derives -tp1 / -sl leg ids)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = _require_api_key()

    reference_price = (
        Decimal(args.reference_price)
        if args.reference_price
        else _fetch_reference_price(args.symbol)
    )
    body = build_deferred_bracket_body(
        args.symbol,
        reference_price,
        args.client_id,
        notional_usdt=Decimal(args.notional_usdt),
        entry_offset_bps=args.entry_offset_bps,
    )

    status, response = _post_bracket(args.host, api_key, body)
    print(json.dumps({"request": body, "status": status, "response": response}, indent=2))
    if status >= 300:
        return 1

    print(
        "\nWatch these client order ids "
        "(brackets/bracket_legs rows, /soak panel, order_update events):",
        file=sys.stderr,
    )
    print(f"  entry: {args.client_id}", file=sys.stderr)
    print(f"  tp1:   {args.client_id}-tp1", file=sys.stderr)
    print(f"  sl:    {args.client_id}-sl", file=sys.stderr)
    if isinstance(response, dict) and not response.get("legs_pending_trigger"):
        print(
            "\nWARNING: legs_pending_trigger was not true — exits were NOT deferred. "
            "Check BRACKET_LEGS_ON_FILL=true and DATABASE_URL on the router.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
