"""
Unit tests for timeframe parsing utilities.
"""

from datetime import timedelta

from app.engine.telegram_validator.timeframe_utils import timeframe_to_timedelta


def test_timeframe_to_timedelta_parses_minutes_hours_days() -> None:
    assert timeframe_to_timedelta("30m") == timedelta(minutes=30)
    assert timeframe_to_timedelta("1h") == timedelta(hours=1)
    assert timeframe_to_timedelta("4h") == timedelta(hours=4)
    assert timeframe_to_timedelta("1d") == timedelta(days=1)
