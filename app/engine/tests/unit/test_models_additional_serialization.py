import json
from datetime import datetime, timezone
from decimal import Decimal

from app.engine.models import Ticker, TimeFrame


def test_ticker_models_serialize_decimals_strings():
    t = Ticker(
        symbol="BTCUSDT",
        price_change=Decimal("-100.01"),
        price_change_percent=Decimal("-0.50"),
        weighted_avg_price=Decimal("50000.1234"),
        prev_close_price=Decimal("50100.1"),
        last_price=Decimal("49999.99"),
        last_qty=Decimal("0.5"),
        bid_price=Decimal("49990.1"),
        ask_price=Decimal("50010.2"),
        open_price=Decimal("50100.0"),
        high_price=Decimal("50500.0"),
        low_price=Decimal("49000.0"),
        volume=Decimal("1234.5678"),
        quote_volume=Decimal("60000000.0"),
        open_time=datetime.now(timezone.utc),
        close_time=datetime.now(timezone.utc),
        count=1000,
    )

    d = json.loads(t.model_dump_json())

    # All Decimal fields serialized as strings
    assert isinstance(d["price_change"], str)
    assert isinstance(d["price_change_percent"], str)
    assert isinstance(d["weighted_avg_price"], str)
    assert isinstance(d["prev_close_price"], str)
    assert isinstance(d["last_price"], str)
    assert isinstance(d["last_qty"], str)
    assert isinstance(d["bid_price"], str)
    assert isinstance(d["ask_price"], str)
    assert isinstance(d["open_price"], str)
    assert isinstance(d["high_price"], str)
    assert isinstance(d["low_price"], str)
    assert isinstance(d["volume"], str)
    assert isinstance(d["quote_volume"], str)


def test_ticker_models_timestamp_tz_aware():
    t = Ticker(
        symbol="ETHUSDT",
        price_change=Decimal("1.0"),
        price_change_percent=Decimal("0.1"),
        weighted_avg_price=Decimal("2500.5"),
        prev_close_price=Decimal("2499.0"),
        last_price=Decimal("2501.0"),
        last_qty=Decimal("2.0"),
        bid_price=Decimal("2500.0"),
        ask_price=Decimal("2501.0"),
        open_price=Decimal("2490.0"),
        high_price=Decimal("2510.0"),
        low_price=Decimal("2480.0"),
        volume=Decimal("9876.543"),
        quote_volume=Decimal("20000000.0"),
        open_time=datetime.now(),  # naive intentionally
        close_time=datetime.now(),  # naive intentionally
        count=42,
    )

    d = json.loads(t.model_dump_json())
    assert "Z" in d["open_time"] or "+00:00" in d["open_time"]
    assert "Z" in d["close_time"] or "+00:00" in d["close_time"]


def test_technical_indicators_models_serialize_decimals_strings_and_nones():
    from app.engine.models import TechnicalIndicators

    ti = TechnicalIndicators(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M5,
        timestamp=datetime.now(timezone.utc),
        ema_9=Decimal("10.1"),
        ema_21=None,
        rsi_14=Decimal("55.55"),
        macd_line=None,
        macd_signal=Decimal("0.1234"),
        macd_histogram=Decimal("-0.5"),
        atr_14=Decimal("100.0"),
        bb_upper=None,
        bb_middle=Decimal("11.11"),
        bb_lower=Decimal("9.99"),
        bb_width=None,
        bb_percent=Decimal("0.75"),
    )

    d = json.loads(ti.model_dump_json())

    # Provided decimals are strings, missing remain null
    assert d["ema_9"] == "10.1"
    assert d["ema_21"] is None
    assert d["rsi_14"] == "55.55"
    assert d["macd_line"] is None
    assert d["macd_signal"] == "0.1234"
    assert d["macd_histogram"] == "-0.5"
    assert d["atr_14"] == "100.0"
    assert d["bb_upper"] is None
    assert d["bb_middle"] == "11.11"
    assert d["bb_lower"] == "9.99"
    assert d["bb_width"] is None
    assert d["bb_percent"] == "0.75"


def test_technical_indicators_models_timestamp_tz_aware():
    from app.engine.models import TechnicalIndicators

    ti = TechnicalIndicators(
        symbol="ETHUSDT",
        timeframe=TimeFrame.M1,
        timestamp=datetime.now(),  # naive intentionally
    )

    d = json.loads(ti.model_dump_json())
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]


def test_market_structure_models_serialization():
    from app.engine.models import MarketStructure, SMCStructure

    ms = MarketStructure(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        timestamp=datetime.now(),  # naive intentionally
        structure_type=SMCStructure.HIGHER_HIGH,
        price=Decimal("30000.5"),
        previous_structure=None,
        trend_direction="bullish",
    )

    d = json.loads(ms.model_dump_json())
    assert d["price"] == "30000.5"
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]


def test_health_status_timestamp_serialization():
    from app.engine.models import HealthStatus

    hs = HealthStatus(
        service="ingest",
        status="healthy",
        timestamp=datetime.now(),  # naive intentionally
        details={"ok": True},
        response_time_ms=12.34,
    )

    d = json.loads(hs.model_dump_json())
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]
    # floats and other fields unchanged
    assert isinstance(d["response_time_ms"], float)


def test_system_metrics_timestamp_serialization():
    from app.engine.models import SystemMetrics

    sm = SystemMetrics(
        timestamp=datetime.now(),  # naive intentionally
        cpu_usage=0.5,
        memory_usage=0.75,
        disk_usage=0.60,
        network_io={"in": 1000.0, "out": 500.0},
        active_connections=10,
        events_processed=100,
        errors_count=0,
        uptime_seconds=12.0,
    )

    d = json.loads(sm.model_dump_json())
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]


def test_trading_metrics_serialization():
    from app.engine.models import TradingMetrics

    tm = TradingMetrics(
        timestamp=datetime.now(timezone.utc),
        total_trades=10,
        winning_trades=6,
        losing_trades=4,
        win_rate=Decimal("0.6"),
        total_pnl=Decimal("1234.56"),
        max_drawdown=Decimal("-0.12"),
        sharpe_ratio=None,
        profit_factor=Decimal("1.8"),
        average_win=Decimal("2.5"),
        average_loss=Decimal("-1.2"),
        largest_win=Decimal("5.0"),
        largest_loss=Decimal("-3.0"),
    )

    d = json.loads(tm.model_dump_json())
    # Decimals are strings; None stays null
    assert d["win_rate"] == "0.6"
    assert d["total_pnl"] == "1234.56"
    assert d["max_drawdown"] == "-0.12"
    assert d["sharpe_ratio"] is None
    assert d["profit_factor"] == "1.8"
    assert d["average_win"] == "2.5"
    assert d["average_loss"] == "-1.2"
    assert d["largest_win"] == "5.0"
    assert d["largest_loss"] == "-3.0"
    assert "Z" in d["timestamp"] or "+00:00" in d["timestamp"]
