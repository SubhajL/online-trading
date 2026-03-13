from __future__ import annotations

from decimal import Decimal

from app.engine.decision.risk_state import RiskSnapshot
from app.engine.models import RiskParameters, TradingDecision


def _safe_div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def evaluate_pretrade_risk(
    *,
    snapshot: RiskSnapshot,
    decision: TradingDecision,
    risk: RiskParameters,
) -> tuple[bool, list[str]]:
    symbol = decision.symbol
    if risk.allowed_symbols and symbol not in set(risk.allowed_symbols):
        return False, [f"allowed_symbols_blocked:{symbol}"]

    entry_price = decision.entry_price
    quantity = decision.quantity
    if entry_price is None or quantity is None:
        return False, ["missing_price_or_quantity"]

    # Check equity FIRST - this is the root cause when position sizing
    # produces quantity=0 (because equity=0 → risk_amount=0 → quantity=0)
    equity = snapshot.equity
    if equity <= 0:
        return False, ["invalid_equity"]

    new_notional = abs(entry_price * quantity)
    if new_notional <= 0:
        return False, ["invalid_notional"]

    eq_ratio = _safe_div(new_notional, equity)
    # Note: eq_ratio should never be None here since we already checked equity > 0
    if eq_ratio is None:
        return False, ["invalid_equity"]

    daily_loss_ratio = _safe_div(
        max(Decimal(0), snapshot.start_of_day_equity - snapshot.equity),
        snapshot.start_of_day_equity,
    )
    if daily_loss_ratio is None:
        return False, ["invalid_start_of_day_equity"]
    if daily_loss_ratio > risk.max_daily_loss:
        return False, [f"daily_loss_exceeded:{daily_loss_ratio}"]

    drawdown_ratio = _safe_div(
        max(Decimal(0), snapshot.peak_equity - snapshot.equity),
        snapshot.peak_equity,
    )
    if drawdown_ratio is None:
        return False, ["invalid_peak_equity"]
    if drawdown_ratio > risk.max_drawdown:
        return False, [f"drawdown_exceeded:{drawdown_ratio}"]

    existing_symbol_exposure = snapshot.symbol_exposure_usd.get(symbol, Decimal(0))
    existing_total_exposure = snapshot.total_exposure_usd

    max_position_notional_ratio = _safe_div(new_notional, equity)
    if max_position_notional_ratio is None:
        return False, ["invalid_equity_for_position"]
    if max_position_notional_ratio > risk.max_position_notional_pct:
        return False, [f"max_position_notional_exceeded:{max_position_notional_ratio}"]

    symbol_exposure_ratio = _safe_div(existing_symbol_exposure + new_notional, equity)
    if symbol_exposure_ratio is None:
        return False, ["invalid_equity_for_symbol_exposure"]
    if symbol_exposure_ratio > risk.max_symbol_exposure_pct:
        return False, [f"max_symbol_exposure_exceeded:{symbol_exposure_ratio}"]

    total_exposure_ratio = _safe_div(existing_total_exposure + new_notional, equity)
    if total_exposure_ratio is None:
        return False, ["invalid_equity_for_total_exposure"]
    if total_exposure_ratio > risk.max_total_exposure_leverage:
        return False, [f"max_total_exposure_exceeded:{total_exposure_ratio}"]

    open_positions = snapshot.open_positions_count
    is_new_symbol = existing_symbol_exposure <= 0
    projected_open_positions = open_positions + (1 if is_new_symbol else 0)
    if projected_open_positions > risk.max_open_positions:
        return False, [f"max_open_positions_exceeded:{projected_open_positions}"]

    return True, ["ok"]


def build_pretrade_risk_debug_metadata(
    *,
    snapshot: RiskSnapshot,
    decision: TradingDecision,
    risk: RiskParameters,
) -> dict[str, object]:
    """Build operator-friendly debug metadata for risk-limit errors.

    Values are serialized as strings where Decimal precision matters.
    """
    entry_price = decision.entry_price
    stop_loss = decision.stop_loss
    quantity = decision.quantity

    equity = snapshot.equity
    start_of_day_equity = snapshot.start_of_day_equity
    peak_equity = snapshot.peak_equity

    stop_distance = None
    if entry_price is not None and stop_loss is not None:
        stop_distance = abs(entry_price - stop_loss)

    new_notional = None
    if entry_price is not None and quantity is not None:
        try:
            new_notional = abs(entry_price * quantity)
        except Exception:
            new_notional = None

    daily_loss_ratio = _safe_div(
        max(Decimal(0), start_of_day_equity - equity),
        start_of_day_equity,
    )
    drawdown_ratio = _safe_div(
        max(Decimal(0), peak_equity - equity),
        peak_equity,
    )

    max_position_notional_ratio = None
    if new_notional is not None:
        max_position_notional_ratio = _safe_div(new_notional, equity)

    existing_symbol_exposure = snapshot.symbol_exposure_usd.get(decision.symbol, Decimal(0))
    directional_symbol_exposure = snapshot.symbol_directional_exposure_usd.get(decision.symbol, {})
    existing_total_exposure = snapshot.total_exposure_usd

    def _dec(v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    def _ratio(v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    return {
        "equity_usd": _dec(equity),
        "equity_ts": snapshot.equity_ts.isoformat(),
        "start_of_day_equity_usd": _dec(start_of_day_equity),
        "peak_equity_usd": _dec(peak_equity),
        "symbol_exposure_usd": _dec(existing_symbol_exposure),
        "symbol_exposure_mode": "gross",
        "symbol_directional_exposure_usd": {
            side: str(value) for side, value in directional_symbol_exposure.items()
        },
        "total_exposure_usd": _dec(existing_total_exposure),
        "entry_price": _dec(entry_price),
        "stop_loss": _dec(stop_loss),
        "stop_distance": _dec(stop_distance),
        "quantity": _dec(quantity),
        "new_notional_usd": _dec(new_notional),
        "daily_loss_ratio": _ratio(daily_loss_ratio),
        "max_daily_loss": _ratio(risk.max_daily_loss),
        "drawdown_ratio": _ratio(drawdown_ratio),
        "max_drawdown": _ratio(risk.max_drawdown),
        "max_position_notional_ratio": _ratio(max_position_notional_ratio),
        "max_position_notional_pct": _ratio(risk.max_position_notional_pct),
        "max_symbol_exposure_pct": _ratio(risk.max_symbol_exposure_pct),
        "max_total_exposure_leverage": _ratio(risk.max_total_exposure_leverage),
        "max_open_positions": int(risk.max_open_positions),
        "risk_per_trade": _ratio(risk.risk_per_trade),
    }
