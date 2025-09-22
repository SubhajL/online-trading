"""
Technical Analysis Features Module

Implements various technical indicators including:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- BB (Bollinger Bands)
"""

from .engine import FeatureEngine
from .feature_service import FeatureService
from .indicators import TechnicalIndicatorsCalculator

__all__ = [
    "FeatureEngine",
    "FeatureService",
    "TechnicalIndicatorsCalculator",
]
