"""
Pure position-sizing functions for the simulator's non-risk sizing modes.

"notional" sizes a fixed fraction of equity; "vol_target" scales that fraction
so the position's annualized volatility approximates a target. Both return a
target quantity that the caller must still clamp with the exposure caps.
"""

from __future__ import annotations

from decimal import Decimal
import math
import statistics
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def notional_quantity(
    *,
    equity: Decimal,
    entry_price: Decimal,
    notional_pct: Decimal,
) -> Decimal | None:
    if equity <= 0 or entry_price <= 0 or notional_pct <= 0:
        return None
    return equity * notional_pct / entry_price


def annualized_volatility(
    closes: Sequence[Decimal],
    bars_per_year: float,
) -> Decimal | None:
    """Population std of simple per-bar returns, sqrt-annualized — the same
    convention as MetricsCalculator's Sharpe, so target and measurement agree."""
    if len(closes) < 2:
        return None
    if any(close <= 0 for close in closes):
        return None
    returns = [float(closes[i] / closes[i - 1]) - 1.0 for i in range(1, len(closes))]
    return Decimal(str(statistics.pstdev(returns) * math.sqrt(bars_per_year)))


def vol_target_quantity(
    *,
    equity: Decimal,
    entry_price: Decimal,
    vol_target_annual_pct: Decimal,
    annualized_vol: Decimal | None,
) -> Decimal | None:
    if equity <= 0 or entry_price <= 0 or vol_target_annual_pct <= 0:
        return None
    if annualized_vol is None or annualized_vol <= 0:
        return None
    weight = vol_target_annual_pct / Decimal(100) / annualized_vol
    return equity * weight / entry_price
