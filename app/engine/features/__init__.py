"""
Technical Analysis Features Module

Implements various technical indicators including:
- EMA (Exponential Moving Average)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ATR (Average True Range)
- BB (Bollinger Bands)
"""

from .indicators import TechnicalIndicators
from .feature_service import FeatureService

__all__ = ["TechnicalIndicators", "FeatureService"]
