"""Serialization tests for key Pydantic models.

Ensures Decimals serialize to strings and datetimes are timezone-aware ISO.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest

from app.engine.models import (
    Ticker,
    TechnicalIndicators,
    MarketStructure,
    HealthStatus,
    SystemMetrics,
    TradingMetrics,
    TimeFrame,
    SMCStructure,
)


def _is_iso_utc(s: str) -> bool:
    """Basic check for ISO string ending with UTC offset."""
    return s.endswith("+00:00") or s.endswith("Z")


def test_ticker_serializes_decimals_and_aware_timestamps() -> None:
    now = datetime(2024, 1, 1, 12, 0, 0)  # naive on purpose; serializer should add UTC
    t = Ticker(
        symbol="BTCUSDT",
        price_change=Decimal("1.23"),
        price_change_percent=Decimal("0.5"),
        weighted_avg_price=Decimal("50000.1"),
        prev_close_price=Decimal("49999.9"),
        last_price=Decimal("50001"),
        last_qty=Decimal("0.1"),
        bid_price=Decimal("50000"),
        ask_price=Decimal("50002"),
        open_price=Decimal("48000"),
        high_price=Decimal("51000"),
        low_price=Decimal("47000"),
        volume=Decimal("100"),
        quote_volume=Decimal("5000000"),
        open_time=now,
        close_time=now,
        count=123,
    )
    data = json.loads(t.model_dump_json())

    # Decimal fields should be strings
    assert isinstance(data["price_change"], str)
    assert isinstance(data["last_price"], str)
    assert isinstance(data["quote_volume"], str)

    # Timestamps should be ISO UTC
    assert _is_iso_utc(data["open_time"]) and _is_iso_utc(data["close_time"])


def test_technical_indicators_serialization_optional_decimals() -> None:
    ti = TechnicalIndicators(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        ema_9=Decimal("1"),
        ema_21=None,
        rsi_14=Decimal("50"),
    )
    data = json.loads(ti.model_dump_json())
    assert isinstance(data["ema_9"], str)
    assert data["ema_21"] is None
    assert _is_iso_utc(data["timestamp"]) is True


def test_market_structure_serialization_price_and_timestamp() -> None:
    ms = MarketStructure(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        structure_type=SMCStructure.HIGHER_HIGH,
        price=Decimal("50000"),
    )
    data = json.loads(ms.model_dump_json())
    assert isinstance(data["price"], str)
    assert _is_iso_utc(data["timestamp"]) is True


def test_health_status_serialization_timestamp_aware_utc() -> None:
    hs = HealthStatus(
        service="db",
        status="healthy",
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        details={"ok": True},
    )
    data = json.loads(hs.model_dump_json())
    assert _is_iso_utc(data["timestamp"]) is True


def test_system_metrics_serialization_timestamp_aware_utc() -> None:
    sm = SystemMetrics(
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        cpu_usage=0.1,
        memory_usage=0.2,
        disk_usage=0.3,
        network_io={"in": 1.0, "out": 2.0},
        active_connections=5,
        events_processed=10,
        errors_count=0,
        uptime_seconds=1.23,
    )
    data = json.loads(sm.model_dump_json())
    assert _is_iso_utc(data["timestamp"]) is True


def test_trading_metrics_serialization_decimals_and_timestamp() -> None:
    tm = TradingMetrics(
        timestamp=datetime(2024, 1, 1, 0, 0, 0),
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=Decimal("0.6"),
        total_pnl=Decimal("123.45"),
        max_drawdown=Decimal("-10.0"),
        average_win=Decimal("50"),
        average_loss=Decimal("-20"),
        largest_win=Decimal("200"),
        largest_loss=Decimal("-100"),
    )
    data = json.loads(tm.model_dump_json())
    assert isinstance(data["total_pnl"], str)
    assert isinstance(data["largest_loss"], str)
    assert _is_iso_utc(data["timestamp"]) is True
