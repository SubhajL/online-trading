"""Formatter for creating consistent alert messages across platforms."""

from decimal import Decimal
from typing import Any, Dict, Optional


class AlertFormatter:
    """Format trading alerts for external messaging platforms."""

    def format_decision(self, decision: Dict[str, Any]) -> str:
        """Format a trading decision into an alert message."""
        symbol = decision["symbol"]
        side = decision["side"]
        entry = decision["entry_price"]
        sl = decision["stop_loss"]
        tp = decision["take_profit"]
        quantity = decision["quantity"]
        confidence = decision["confidence"]
        reasons = decision.get("reasons", [])

        # Determine emoji and side text
        if side == "long":
            emoji = "🟢"
            side_text = "LONG"
        else:
            emoji = "🔴"
            side_text = "SHORT"

        # Calculate percentage changes
        sl_pct = self._calculate_pct_change(entry, sl)
        tp_pct = self._calculate_pct_change(entry, tp)

        # Extract base currency from symbol (e.g., BTC from BTCUSDT)
        base_currency = symbol.replace("USDT", "").replace("USD", "")

        # Build message
        lines = [
            f"{emoji} {side_text}: {symbol}",
            f"Entry: {self._format_currency(entry)}",
            f"SL: {self._format_currency(sl)} ({sl_pct:+.2f}%)",
            f"TP: {self._format_currency(tp)} ({tp_pct:+.2f}%)",
            f"Size: {quantity} {base_currency}",
            f"Confidence: {int(confidence * 100)}%",
        ]

        if reasons:
            lines.append("")
            lines.append("Reasons:")
            for reason in reasons:
                lines.append(f"• {reason}")

        return "\n".join(lines)

    def format_order_update(self, order: Dict[str, Any]) -> str:
        """Format an order update into an alert message."""
        symbol = order["symbol"]
        side = order["side"]
        status = order["status"]
        quantity = order["quantity"]

        # Status emoji
        status_emoji = {
            "filled": "✅",
            "partially_filled": "🔄",
            "cancelled": "❌",
            "rejected": "🚫",
        }.get(status, "ℹ️")

        # Build message
        lines = [f"{status_emoji} Order {status.title()}"]
        lines.append(f"{symbol}")

        if status == "filled" and "filled_price" in order:
            price = order["filled_price"]
            lines.append(f"{side.title()} {quantity} @ {self._format_currency(price)}")
        else:
            lines.append(f"{side.title()} {quantity}")

        if "reason" in order:
            lines.append(f"Reason: {order['reason']}")

        return "\n".join(lines)

    def format_guard_alert(self, guard: Dict[str, Any]) -> str:
        """Format a guard/risk alert message."""
        guard_type = guard["type"]
        symbol = guard["symbol"]
        current = guard["current_value"]
        threshold = guard["threshold"]
        action = guard["action"]

        # Format guard type
        type_display = guard_type.replace("_", " ").title()

        lines = [
            f"⚠️ Guard Triggered",
            f"{symbol}",
            f"{type_display}: {current:.2%}",
            f"Threshold: {threshold:.2%}",
            f"Action: {action.replace('_', ' ').title()}",
        ]

        return "\n".join(lines)

    def _calculate_pct_change(self, from_price: Decimal, to_price: Decimal) -> float:
        """Calculate percentage change between two prices."""
        if from_price == 0:
            return 0.0
        return float((to_price - from_price) / from_price * 100)

    def _format_currency(self, value: Decimal) -> str:
        """Format a decimal value as currency."""
        value_float = float(value)

        # For very small values (< 0.01), show more decimals
        if value_float < 0.01 and value_float > 0:
            return f"${value_float:.6f}".rstrip("0").rstrip(".")

        # For normal values, use standard currency format
        return f"${value_float:,.2f}"

    def _format_currency(self, value: Decimal, with_sign: bool = False) -> str:
        """Format a decimal value as currency with optional sign."""
        value_float = float(value)

        # For very small values (< 0.01), show more decimals
        if abs(value_float) < 0.01 and value_float != 0:
            formatted = f"${abs(value_float):.6f}".rstrip("0").rstrip(".")
        else:
            # For normal values, use standard currency format
            formatted = f"${abs(value_float):,.2f}"

        if with_sign and value_float != 0:
            sign = "+" if value_float > 0 else "-"
            return f"{sign}{formatted}"
        return formatted

    def format_position(self, position: Dict[str, Any]) -> str:
        """Format a position update into an alert message."""
        symbol = position["symbol"]
        side = position["side"]
        quantity = position["quantity"]
        entry_price = position.get("entry_price", 0)
        current_price = position.get("current_price", 0)
        pnl = position.get("pnl", 0)
        pnl_percent = position.get("pnl_percent", 0)

        # Build message
        lines = [
            "📊 POSITION UPDATE",
            symbol,
            f"{side.upper()} {quantity}"
        ]

        if entry_price and current_price:
            lines.append(f"Entry: {self._format_currency(entry_price)}")
            lines.append(f"Current: {self._format_currency(current_price)}")

        if pnl is not None:
            pnl_str = self._format_currency(abs(pnl), with_sign=False)
            sign = "+" if pnl >= 0 else "-"
            pnl_pct_sign = "+" if pnl_percent >= 0 else ""
            lines.append(f"P&L: {sign}{pnl_str} ({pnl_pct_sign}{pnl_percent:.2f}%)")

        return "\n".join(lines)

    def format_daily_summary(self, summary: Dict[str, Any]) -> str:
        """Format daily trading summary."""
        lines = [
            "📊 Daily Trading Summary",
            f"Date: {summary['date']}",
            f"Total Trades: {summary['total_trades']}",
            f"Winning Trades: {summary['winning_trades']}",
            f"Win Rate: {summary['win_rate']:.1%}",
            f"Total P&L: {self._format_currency(summary['total_pnl'], with_sign=True)}",
        ]
        return "\n".join(lines)