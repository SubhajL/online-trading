"""
Database Adapters Module

Provides database adapters for various databases including TimescaleDB
for time-series data storage and PostgreSQL for relational data.
"""

from .connection_pool import ConnectionPool, DBConfig
from .timescale import (
    close_pool,
    get_active_positions,
    get_candles,
    get_pool,
    initialize_pool,
    upsert_candle,
    upsert_indicator,
    upsert_order,
    upsert_zone,
)
from .timescale_adapter import TimescaleDBAdapter

__all__ = [
    "ConnectionPool",
    "DBConfig",
    "TimescaleDBAdapter",
    "close_pool",
    "get_active_positions",
    "get_candles",
    "get_pool",
    "initialize_pool",
    "upsert_candle",
    "upsert_indicator",
    "upsert_order",
    "upsert_zone",
]
