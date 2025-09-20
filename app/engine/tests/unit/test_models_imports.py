"""Test that models can be imported without conflicts with Python builtins"""

import importlib
import sys
from types import ModuleType


def test_no_builtin_conflicts():
    """Ensure our module doesn't conflict with Python's built-in types module"""
    # Import Python's built-in types module
    builtin_types = importlib.import_module("types")

    # Verify it's the actual builtin module by checking for expected attributes
    assert hasattr(builtin_types, "ModuleType")
    assert hasattr(builtin_types, "FunctionType")
    assert hasattr(builtin_types, "MappingProxyType")
    assert isinstance(builtin_types, ModuleType)

    # The builtin module should be from Python's stdlib
    assert (
        "lib/python" in builtin_types.__file__
        or "types.py" not in builtin_types.__file__
    )


def test_models_imports():
    """Verify all model classes can be imported from models module"""
    from app.engine.models import (
        TimeFrame,
        OrderSide,
        OrderType,
        OrderStatus,
        PositionSide,
        MarketRegime,
        SMCStructure,
        ZoneType,
        Candle,
        TechnicalIndicators,
        SMCSignal,
        RetestSignal,
        TradingDecision,
        Order,
        Position,
        SupplyDemandZone,
    )

    # Test enum values
    assert TimeFrame.M1.value == "1m"
    assert OrderSide.BUY.value == "BUY"
    assert OrderType.LIMIT.value == "LIMIT"
    assert PositionSide.LONG.value == "LONG"
    assert MarketRegime.TRENDING_UP.value == "trending_up"

    # Test model instantiation
    from datetime import datetime

    candle = Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M1,
        open_time=datetime.fromtimestamp(1234567890),
        close_time=datetime.fromtimestamp(1234567950),
        open_price="100.0",
        high_price="110.0",
        low_price="95.0",
        close_price="105.0",
        volume="1000.0",
        quote_volume="105000.0",
        trades=50,
        taker_buy_base_volume="500.0",
        taker_buy_quote_volume="52500.0",
    )
    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == TimeFrame.M1


def test_all_imports_updated():
    """Verify no remaining imports from old types module"""
    # After renaming, attempting to import from types should fail
    try:
        from app.engine.types import TimeFrame

        # If we can still import from types, the rename isn't complete
        assert False, "Should not be able to import from app.engine.types after rename"
    except ImportError:
        # This is expected after successful rename
        pass
