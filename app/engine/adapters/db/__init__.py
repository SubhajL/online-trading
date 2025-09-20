"""
Database Adapters Module

Provides database adapters for various databases including TimescaleDB
for time-series data storage and PostgreSQL for relational data.
"""

from .timescale_adapter import TimescaleDBAdapter
from .timescale import (
    initialize_pool,
    close_pool,
    get_pool,
    upsert_candle,
    get_candles,
    upsert_indicator,
    upsert_zone,
    upsert_order,
    get_active_positions,
)
from .connection_pool import ConnectionPool, DBConfig

__all__ = [
    "TimescaleDBAdapter",
    "ConnectionPool",
    "DBConfig",
    "initialize_pool",
    "close_pool",
    "get_pool",
    "upsert_candle",
    "get_candles",
    "upsert_indicator",
    "upsert_zone",
    "upsert_order",
    "get_active_positions",
]
