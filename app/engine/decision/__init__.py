"""
Decision Engine Module

Provides trading decision engine with risk management,
signal fusion, and bracket order construction.
"""

from .engine import fuse_signals, apply_trading_guards, generate_decision
from .sizing import calculate_position_size, check_concurrent_positions
from .brackets import create_bracket_orders, calculate_risk_reward_levels

__all__ = [
    "fuse_signals",
    "apply_trading_guards",
    "generate_decision",
    "calculate_position_size",
    "check_concurrent_positions",
    "create_bracket_orders",
    "calculate_risk_reward_levels",
]
