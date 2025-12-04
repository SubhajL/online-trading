"""Tests for contract mappers that transform internal models to schema format."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.engine.contracts.mappers import (
    CandleEventMapper,
    SMCEventMapper,
    ZoneEventMapper,
)
from app.engine.models import Candle, TimeFrame
from app.engine.smc_types import (
    Pivot,
    SMCEvent,
    SMCEventKind,
    StructureState,
    Zone,
    ZoneSide,
)

# Test constants
SAMPLE_ZONE_STRENGTH = 0.75

# Required fields from candles.v1.schema.json
CANDLES_REQUIRED_FIELDS = {
    "version",
    "venue",
    "symbol",
    "timeframe",
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trades",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "is_closed",
}

# Required fields from smc_events.v1.schema.json
SMC_EVENTS_REQUIRED_FIELDS = {
    "version",
    "venue",
    "symbol",
    "timeframe",
    "event_time",
    "event_type",
    "direction",
    "price_level",
    "previous_pivot_price",
    "previous_pivot_time",
    "broken_pivot_price",
    "broken_pivot_time",
}

# Required fields from zones.v1.schema.json
ZONES_REQUIRED_FIELDS = {
    "version",
    "venue",
    "symbol",
    "timeframe",
    "zone_id",
    "zone_type",
    "direction",
    "upper_bound",
    "lower_bound",
    "created_time",
    "candle_count",
    "strength",
    "touches",
    "is_active",
}


@pytest.fixture
def sample_candle() -> Candle:
    """Create a sample candle for testing."""
    return Candle(
        symbol="BTCUSDT",
        timeframe=TimeFrame.H1,
        open_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 15, 11, 0, 0, tzinfo=UTC),
        open_price=Decimal("50000.00"),
        high_price=Decimal("51000.00"),
        low_price=Decimal("49500.00"),
        close_price=Decimal("50500.00"),
        volume=Decimal("1000.5"),
        quote_volume=Decimal("50250000.00"),
        trades=5000,
        taker_buy_base_volume=Decimal("600.3"),
        taker_buy_quote_volume=Decimal("30150000.00"),
    )


@pytest.fixture
def sample_smc_event() -> SMCEvent:
    """Create a sample SMC event for testing."""
    trigger_pivot = Pivot(
        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        price=Decimal("50000.00"),
        is_high=True,
        strength=3,
        bar_index=100,
    )
    reference_pivot = Pivot(
        timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
        price=Decimal("49500.00"),
        is_high=False,
        strength=2,
        bar_index=95,
    )
    return SMCEvent(
        kind=SMCEventKind.CHOCH,
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        price=Decimal("50200.00"),
        from_state=StructureState.BEARISH,
        to_state=StructureState.BULLISH,
        trigger_pivot=trigger_pivot,
        reference_pivot=reference_pivot,
        strength=Decimal("0.85"),
    )


@pytest.fixture
def sample_zone() -> Zone:
    """Create a sample zone for testing."""
    return Zone(
        zone_id=uuid4(),
        symbol="ETHUSDT",
        timeframe=TimeFrame.H4,
        zone_type="FVG",
        side=ZoneSide.LOW,
        top_price=Decimal("3200.00"),
        bottom_price=Decimal("3150.00"),
        created_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
        created_bar_index=50,
        expiry_bars=20,
        touches=2,
        strength=Decimal(str(SAMPLE_ZONE_STRENGTH)),
    )


class TestCandleEventMapper:
    """Tests for CandleEventMapper."""

    def test_candle_mapper_includes_all_required_fields(
        self,
        sample_candle: Candle,
    ) -> None:
        """Output should include all fields required by candles.v1 schema."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")
        assert CANDLES_REQUIRED_FIELDS.issubset(result.keys())

    def test_candle_mapper_stringifies_decimal_prices(
        self,
        sample_candle: Candle,
    ) -> None:
        """Price fields should be stringified decimals."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")

        assert result["open"] == "50000.00"
        assert result["high"] == "51000.00"
        assert result["low"] == "49500.00"
        assert result["close"] == "50500.00"
        assert isinstance(result["open"], str)
        assert isinstance(result["high"], str)
        assert isinstance(result["low"], str)
        assert isinstance(result["close"], str)

    def test_candle_mapper_includes_taker_buy_fields(
        self,
        sample_candle: Candle,
    ) -> None:
        """Taker buy volume fields should be present and stringified."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")

        assert "taker_buy_volume" in result
        assert "taker_buy_quote_volume" in result
        assert result["taker_buy_volume"] == "600.3"
        assert result["taker_buy_quote_volume"] == "30150000.00"

    def test_candle_mapper_includes_version(self, sample_candle: Candle) -> None:
        """Output should include schema version."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")
        assert "version" in result
        assert result["version"] == "1.0.0"

    def test_candle_mapper_includes_is_closed(self, sample_candle: Candle) -> None:
        """Output should include is_closed field."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")
        assert "is_closed" in result
        assert result["is_closed"] is True

        result_unclosed = CandleEventMapper.to_schema(
            sample_candle,
            venue="binance",
            is_closed=False,
        )
        assert result_unclosed["is_closed"] is False

    def test_candle_mapper_formats_datetime_as_iso(
        self,
        sample_candle: Candle,
    ) -> None:
        """Datetime fields should be ISO8601 formatted strings."""
        result = CandleEventMapper.to_schema(sample_candle, venue="binance")

        assert isinstance(result["open_time"], str)
        assert isinstance(result["close_time"], str)
        # Check ISO8601 format with Z suffix
        assert result["open_time"].endswith("Z") or "+00:00" in result["open_time"]


class TestSMCEventMapper:
    """Tests for SMCEventMapper."""

    def test_smc_mapper_includes_all_required_fields(
        self,
        sample_smc_event: SMCEvent,
    ) -> None:
        """Output should include all fields required by smc_events.v1 schema."""
        result = SMCEventMapper.to_schema(
            sample_smc_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert SMC_EVENTS_REQUIRED_FIELDS.issubset(result.keys())

    def test_smc_mapper_lowercases_event_type(
        self,
        sample_smc_event: SMCEvent,
    ) -> None:
        """Event type should be lowercase per schema (choch, bos)."""
        # Test CHOCH -> choch
        result = SMCEventMapper.to_schema(
            sample_smc_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert result["event_type"] == "choch"

        # Test BOS -> bos
        bos_event = sample_smc_event.model_copy(update={"kind": SMCEventKind.BOS})
        result_bos = SMCEventMapper.to_schema(
            bos_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert result_bos["event_type"] == "bos"

    def test_smc_mapper_maps_direction_correctly(
        self,
        sample_smc_event: SMCEvent,
    ) -> None:
        """Direction should be lowercase per schema (bullish, bearish)."""
        # BULLISH -> bullish
        result = SMCEventMapper.to_schema(
            sample_smc_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert result["direction"] == "bullish"

        # BEARISH -> bearish
        bearish_event = sample_smc_event.model_copy(
            update={"to_state": StructureState.BEARISH},
        )
        result_bearish = SMCEventMapper.to_schema(
            bearish_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )
        assert result_bearish["direction"] == "bearish"

    def test_smc_mapper_includes_pivot_data(
        self,
        sample_smc_event: SMCEvent,
    ) -> None:
        """Output should include pivot price and time data."""
        result = SMCEventMapper.to_schema(
            sample_smc_event,
            venue="binance",
            symbol="BTCUSDT",
            timeframe="1h",
        )

        assert result["price_level"] == "50200.00"
        assert "previous_pivot_price" in result
        assert "previous_pivot_time" in result
        assert "broken_pivot_price" in result
        assert "broken_pivot_time" in result


class TestZoneEventMapper:
    """Tests for ZoneEventMapper."""

    def test_zone_mapper_includes_all_required_fields(self, sample_zone: Zone) -> None:
        """Output should include all fields required by zones.v1 schema."""
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")
        assert ZONES_REQUIRED_FIELDS.issubset(result.keys())

    def test_zone_mapper_uses_schema_zone_types(self, sample_zone: Zone) -> None:
        """Zone type should map to schema values (order_block, fair_value_gap)."""
        # FVG -> fair_value_gap
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")
        assert result["zone_type"] == "fair_value_gap"

        # OB_BULL -> order_block
        ob_bull_zone = sample_zone.model_copy(update={"zone_type": "OB_BULL"})
        result_ob = ZoneEventMapper.to_schema(ob_bull_zone, venue="binance")
        assert result_ob["zone_type"] == "order_block"

        # OB_BEAR -> order_block
        ob_bear_zone = sample_zone.model_copy(update={"zone_type": "OB_BEAR"})
        result_bear = ZoneEventMapper.to_schema(ob_bear_zone, venue="binance")
        assert result_bear["zone_type"] == "order_block"

    def test_zone_mapper_maps_side_to_direction(self, sample_zone: Zone) -> None:
        """Zone side should map to direction (HIGH -> supply, LOW -> demand)."""
        # LOW -> demand
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")
        assert result["direction"] == "demand"

        # HIGH -> supply
        supply_zone = sample_zone.model_copy(update={"side": ZoneSide.HIGH})
        result_supply = ZoneEventMapper.to_schema(supply_zone, venue="binance")
        assert result_supply["direction"] == "supply"

    def test_zone_mapper_stringifies_prices(self, sample_zone: Zone) -> None:
        """Price fields should be stringified decimals."""
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")

        assert result["upper_bound"] == "3200.00"
        assert result["lower_bound"] == "3150.00"
        assert isinstance(result["upper_bound"], str)
        assert isinstance(result["lower_bound"], str)

    def test_zone_mapper_includes_strength_as_float(self, sample_zone: Zone) -> None:
        """Strength should be a float between 0 and 1."""
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")

        assert "strength" in result
        assert isinstance(result["strength"], float)
        assert 0 <= result["strength"] <= 1
        assert result["strength"] == SAMPLE_ZONE_STRENGTH

    def test_zone_mapper_includes_is_active(self, sample_zone: Zone) -> None:
        """Output should include is_active field."""
        result = ZoneEventMapper.to_schema(sample_zone, venue="binance")

        # Zone fixture doesn't have is_active, mapper should handle
        assert "is_active" in result
        assert isinstance(result["is_active"], bool)
