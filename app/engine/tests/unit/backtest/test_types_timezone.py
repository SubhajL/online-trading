from datetime import timezone

from app.engine.backtest.types import BacktestFill, BacktestOrder, BacktestTrade


def test_backtest_order_time_timezone_aware():
    o = BacktestOrder()
    assert o.order_time.tzinfo is not None
    assert o.order_time.tzname() in ("UTC", "UTC+00:00", "Coordinated Universal Time")


def test_backtest_fill_time_timezone_aware():
    f = BacktestFill()
    assert f.fill_time.tzinfo is not None
    assert f.fill_time.tzname() in ("UTC", "UTC+00:00", "Coordinated Universal Time")


def test_backtest_trade_entry_time_timezone_aware():
    t = BacktestTrade()
    assert t.entry_time.tzinfo is not None
    assert t.entry_time.tzname() in ("UTC", "UTC+00:00", "Coordinated Universal Time")
