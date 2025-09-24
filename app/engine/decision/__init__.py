"""
Decision Engine Module

Provides trading decision engine with risk management,
signal fusion, and bracket order construction.
"""

from .brackets import calculate_risk_reward_levels, create_bracket_orders
from .engine import apply_trading_guards, fuse_signals, generate_decision
from .sizing import calculate_position_size, check_concurrent_positions

__all__ = [
    "apply_trading_guards",
    "calculate_position_size",
    "calculate_risk_reward_levels",
    "check_concurrent_positions",
    "create_bracket_orders",
    "fuse_signals",
    "generate_decision",
]
