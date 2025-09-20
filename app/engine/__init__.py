"""
Trading Engine Module

A comprehensive trading platform engine with:
- Real-time data ingestion from Binance
- Technical analysis and Smart Money Concepts
- Risk management and decision making
- Paper trading and backtesting capabilities
- Plugin system for extensibility
"""

__version__ = "1.0.0"
__author__ = "Trading Platform Team"

from .bus import EventBus
from .models import *

__all__ = [
    "EventBus",
    # Types will be imported from types module
]