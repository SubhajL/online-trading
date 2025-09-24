"""Decision engine with signal fusion and guards integration"""

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from .brackets import calculate_risk_reward_levels
from .sizing import (
    apply_leverage_constraints,
    calculate_daily_drawdown,
    calculate_position_size,
)


def fuse_signals(signals_raw: list[dict], regime: dict) -> list[dict]:
    """Combine signals with regime context and confidence scoring

    Args:
        signals_raw: Raw trading signals
        regime: Current market regime data

    Returns:
        List of signals with regime context and adjusted confidence
    """
    fused = []

    for signal in signals_raw:
        # Check regime alignment
        signal_type = signal["signal_type"]
        regime_type = regime["regime_type"]

        # Determine if signal aligns with regime
        regime_aligned = (
            (signal_type == "long" and regime_type in ["trending_up"])
            or (signal_type == "short" and regime_type in ["trending_down"])
            or (regime_type == "ranging")  # Both directions OK in ranging
        )

        # Skip signals that strongly contradict regime
        if not regime_aligned and signal["confidence"] < 0.7:
            continue

        # Create fused signal with regime info
        fused_signal = signal.copy()
        fused_signal["regime_alignment"] = regime_aligned

        # Adjust confidence based on regime
        if regime_aligned:
            # Boost confidence for aligned signals
            adjusted_confidence = min(signal["confidence"] * 1.1, 1.0)
        else:
            # Reduce confidence for misaligned signals
            adjusted_confidence = signal["confidence"] * 0.9

        fused_signal["adjusted_confidence"] = adjusted_confidence
        fused.append(fused_signal)

    return fused


def apply_trading_guards(
    signals: list[dict],
    news_events: list[dict],
    funding_windows: list[dict],
    news_buffer_minutes: int = 60,
    funding_buffer_minutes: int = 30,
) -> list[dict] | dict:
    """Filter signals based on news events, funding windows, volatility

    Args:
        signals: Trading signals to filter
        news_events: Upcoming news events
        funding_windows: Upcoming funding windows
        news_buffer_minutes: Minutes before/after news to avoid
        funding_buffer_minutes: Minutes before funding to avoid

    Returns:
        Filtered signals or dict with blocked_reasons if all blocked
    """
    current_time = datetime.now(UTC)
    filtered = []
    blocked_reasons = []

    for signal in signals:
        blocked = False

        # Check news events
        for news in news_events:
            event_time = news["event_time"]
            time_to_event = (event_time - current_time).total_seconds() / 60

            if 0 <= time_to_event <= news_buffer_minutes and news["impact"] == "high":
                blocked = True
                blocked_reasons.append("high_impact_news_event")
                break

        # Check funding windows (for futures)
        if not blocked:
            for funding in funding_windows:
                funding_time = funding["funding_time"]
                time_to_funding = (funding_time - current_time).total_seconds() / 60

                if (
                    0 <= time_to_funding <= funding_buffer_minutes
                    and abs(funding.get("predicted_rate", 0)) > 0.01
                ):  # High funding
                    blocked = True
                    blocked_reasons.append("funding_window")
                    break

        if not blocked:
            filtered.append(signal)

    # If all signals blocked, return dict with reasons
    if not filtered and blocked_reasons:
        return {"blocked_reasons": list(set(blocked_reasons))}

    return filtered


def evaluate_current_positions(
    current_positions: list[dict],
    new_signal: dict,
    max_concurrent: int,
) -> bool | dict:
    """Check existing positions to avoid overexposure

    Args:
        current_positions: List of current open positions
        new_signal: New signal to evaluate
        max_concurrent: Maximum concurrent positions allowed

    Returns:
        True if allowed, dict with reason if blocked
    """
    # Check max concurrent positions
    if len(current_positions) >= max_concurrent:
        return {"reason": "max_concurrent_positions_reached"}

    # Check if we already have position in this symbol
    existing_symbols = {pos["symbol"] for pos in current_positions}
    if new_signal["symbol"] in existing_symbols:
        return {"reason": "position_already_exists"}

    return True


def generate_decision(
    signal: dict,
    account_balance: Decimal,
    risk_percentage: Decimal,
    symbol: str,
    is_futures: bool,
    daily_pnl_history: list[Decimal] | None = None,
    max_daily_drawdown: Decimal | None = None,
) -> dict:
    """Create final decision with full context and risk metadata

    Args:
        signal: Trading signal to process
        account_balance: Current account balance
        risk_percentage: Risk per trade
        symbol: Trading symbol
        is_futures: Whether this is a futures trade
        daily_pnl_history: Daily P&L history for DD calculation
        max_daily_drawdown: Maximum daily drawdown allowed

    Returns:
        Decision dictionary with full context
    """
    # Check daily drawdown if limits provided
    if daily_pnl_history is not None and max_daily_drawdown is not None:
        current_dd = calculate_daily_drawdown(
            daily_pnl_history=daily_pnl_history,
            current_balance=account_balance,
            starting_balance=account_balance - sum(daily_pnl_history),
        )

        # Block if approaching DD limit (within 0.5%)
        if current_dd >= (max_daily_drawdown - Decimal("0.005")):
            return {
                "decision_id": str(uuid.uuid4()),
                "action": "no_action",
                "reasons": ["approaching_daily_drawdown_limit"],
                "confidence": signal.get("confidence", 0),
                "risk_metadata": {
                    "current_drawdown": float(current_dd),
                    "max_allowed": float(max_daily_drawdown),
                },
            }

    # Calculate position size
    entry_price = Decimal(str(signal["entry_price"]))
    stop_loss = Decimal(str(signal["stop_loss"]))

    position_size = calculate_position_size(
        account_balance=account_balance,
        risk_percentage=risk_percentage,
        entry_price=entry_price,
        stop_loss=stop_loss,
    )

    # Apply leverage constraints for futures
    if is_futures:
        position_size = apply_leverage_constraints(
            position_size=position_size,
            account_balance=account_balance,
            entry_price=entry_price,
            is_futures=is_futures,
            max_leverage=Decimal(3),  # Max 3x leverage
        )

    # Calculate risk amount
    risk_amount = account_balance * risk_percentage

    # Calculate TP levels
    is_long = signal["signal_type"] == "long"
    tp_levels = calculate_risk_reward_levels(entry_price, stop_loss, is_long)

    # Build decision
    return {
        "decision_id": str(uuid.uuid4()),
        "action": "open_long" if is_long else "open_short",
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": tp_levels["tp1"],
        "take_profit_2": tp_levels["tp2"],
        "take_profit_3": tp_levels["tp3"],
        "position_size": position_size,
        "risk_amount": risk_amount,
        "risk_percentage": float(risk_percentage),
        "confidence": signal.get("confidence", signal.get("adjusted_confidence", 0.5)),
        "reasons": _build_reasons(signal),
        "risk_metadata": {
            "account_balance": float(account_balance),
            "position_value": float(position_size * entry_price),
            "leverage": (
                float((position_size * entry_price) / account_balance)
                if is_futures
                else 1.0
            ),
            "risk_reward_ratio": "1:3",
            "max_loss": float(risk_amount),
        },
    }


def format_decision_reasons(reasons_data: dict) -> list[str]:
    """Build human-readable reasons array explaining the decision

    Args:
        reasons_data: Dictionary with reason components

    Returns:
        List of formatted reason strings
    """
    reasons = []

    # Signal source
    source = reasons_data.get("signal_source", "unknown")
    source_map = {
        "smc_retest": "SMC retest pattern detected",
        "trend_continuation": "Trend continuation signal",
        "reversal": "Reversal pattern identified",
    }
    reasons.append(source_map.get(source, f"Signal from {source}"))

    # Regime alignment
    if reasons_data.get("regime_alignment"):
        reasons.append("Signal aligned with current market regime")

    # Confidence factors
    for factor in reasons_data.get("confidence_factors", []):
        factor_map = {
            "strong_volume": "Strong volume confirmation",
            "clean_structure": "Clean market structure",
        }
        reasons.append(factor_map.get(factor, factor))

    # Risk factors
    for risk in reasons_data.get("risk_factors", []):
        risk_map = {"near_resistance": "Caution: Near resistance level"}
        reasons.append(risk_map.get(risk, risk))

    # Position sizing constraints
    if reasons_data.get("position_size_limited_by"):
        limit = reasons_data["position_size_limited_by"]
        limit_map = {
            "leverage_constraint": "Position sized limited by leverage constraint",
            "risk_limit": "Position sized to risk limit",
        }
        reasons.append(limit_map.get(limit, f"Position limited by {limit}"))

    return reasons


def _build_reasons(signal: dict) -> list[str]:
    """Internal helper to build reasons from signal data"""
    reasons_data = {
        "signal_source": signal.get("source", "unknown"),
        "regime_alignment": signal.get("regime_alignment", False),
        "confidence_factors": [],
        "risk_factors": [],
    }

    # Add confidence factors based on signal metadata
    if signal.get("confidence", 0) > 0.8:
        reasons_data["confidence_factors"].append("strong_volume")

    return format_decision_reasons(reasons_data)
