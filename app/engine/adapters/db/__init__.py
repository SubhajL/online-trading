"""
Database Adapters Module

Provides database adapters for various databases including TimescaleDB
for time-series data storage and PostgreSQL for relational data.
"""

from .timescale_adapter import TimescaleDBAdapter

__all__ = [
    "TimescaleDBAdapter"
]