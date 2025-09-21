"""
Technical Analysis Features Module

Implements various technical indicators including:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- BB (Bollinger Bands)
"""

from .indicators import TechnicalIndicators, TechnicalIndicatorsCalculator
from .feature_service import FeatureService
from .engine import FeatureEngine

__all__ = [
    "TechnicalIndicators",
    "TechnicalIndicatorsCalculator",
    "FeatureService",
    "FeatureEngine",
]
