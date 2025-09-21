"""
Shared math module for technical indicators

This module provides pure numpy/pandas implementations of technical indicators
used across the trading platform. All functions are deterministic and produce
identical results for the same inputs.
"""

from .atr import calculate_atr
from .bb import calculate_bollinger_bands
from .ema import calculate_ema
from .macd import calculate_macd
from .rsi import calculate_rsi
from .vwap import calculate_vwap, calculate_vwma

__all__ = [
    "calculate_atr",
    "calculate_bollinger_bands",
    "calculate_ema",
    "calculate_macd",
    "calculate_rsi",
    "calculate_vwap",
    "calculate_vwma",
]