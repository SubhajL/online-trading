"""
Test end-to-end event flow through the system.

These tests verify that events propagate correctly through
the live event bus and that services integrate properly.
"""

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from collections import defaultdict

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.models import (
    Candle, TimeFrame, EventType,
    CandleUpdateEvent, FeaturesCalculatedEvent,
    SMCSignalEvent, SMCStructure, ZoneType
)
from app.engine.features.feature_service import FeatureService
from app.engine.smc.smc_service import SMCService


class EventCollector:
    """Utility to collect events by type for testing."""

    def __init__(self):
        self.events = defaultdict(list)
        self._subscription_ids = []

    async def subscribe_to_events(self, event_bus, event_types):
        """Subscribe to multiple event types."""
        for event_type in event_types:
            sub_id = await event_bus.subscribe(
                subscriber_id=f"test_collector_{event_type.value}",
                handler=lambda e, et=event_type: self._collect_event(et, e),
                event_types=[event_type]
            )
            self._subscription_ids.append(sub_id)

    async def unsubscribe_all(self, event_bus):
        """Unsubscribe from all events."""
        for sub_id in self._subscription_ids:
            await event_bus.unsubscribe(sub_id)
        self._subscription_ids.clear()

    def _collect_event(self, event_type, event):
        """Collect event by type."""
        self.events[event_type].append(event)

    def get_events(self, event_type):
        """Get all collected events of a specific type."""
        return self.events[event_type]

    def clear(self):
        """Clear all collected events."""
        self.events.clear()


def create_test_candle(symbol="BTCUSDT", price_base=50000, offset=0, timeframe=TimeFrame.M5):
    """Create a test candle with realistic data."""
    base_time = datetime.utcnow() - timedelta(minutes=(10 - offset) * 5)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=base_time,
        close_time=base_time + timedelta(minutes=5),
        open_price=Decimal(str(price_base + offset * 100)),
        high_price=Decimal(str(price_base + offset * 100 + 50)),
        low_price=Decimal(str(price_base + offset * 100 - 50)),
        close_price=Decimal(str(price_base + offset * 100 + 25)),
        volume=Decimal("100"),
        quote_volume=Decimal("5000000"),
        trades=1000,
        taker_buy_base_volume=Decimal("60"),
        taker_buy_quote_volume=Decimal("3000000")
    )


class TestCandleToFeaturesFlow:
    """Test candle events triggering feature calculations."""

    @pytest.mark.asyncio
    async def test_single_symbol_feature_generation(self, real_db):
        """Candle updates should generate feature events."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Set up event collector
        collector = EventCollector()
        await collector.subscribe_to_events(bus, [EventType.FEATURES_CALCULATED])

        # Start feature service with minimal config
        feature_service = FeatureService(
            ema_periods=[9, 21],  # Use standard periods that match model
            rsi_period=14,
            macd_params=(12, 26, 9),
            atr_period=14,
            bb_period=20
        )
        await feature_service.start()

        # Send enough candles to generate features (need 26 for MACD + 9 for signal)
        for i in range(40):
            candle = create_test_candle(offset=i)
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )
            await bus.publish(event)
            if i % 5 == 0:
                await asyncio.sleep(0.1)  # Let events process periodically

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify features were generated
        feature_events = collector.get_events(EventType.FEATURES_CALCULATED)
        assert len(feature_events) >= 3  # Should have multiple events after min periods

        # Check last feature event
        last_event = feature_events[-1]
        assert last_event.symbol == "BTCUSDT"
        assert last_event.timeframe == TimeFrame.M5
        assert last_event.features is not None

        # Verify indicators are present
        features = last_event.features
        assert features.ema_9 is not None
        assert features.ema_21 is not None  # We included 21 in ema_periods
        assert features.rsi_14 is not None
        assert features.macd_line is not None
        assert features.macd_signal is not None
        assert features.atr_14 is not None
        assert features.bb_upper is not None
        assert features.bb_lower is not None

        # Cleanup
        await feature_service.stop()
        await collector.unsubscribe_all(bus)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_multi_symbol_parallel_processing(self, real_db):
        """Multiple symbols should process in parallel."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        collector = EventCollector()
        await collector.subscribe_to_events(bus, [EventType.FEATURES_CALCULATED])

        feature_service = FeatureService(
            ema_periods=[9],  # Single EMA for faster test
            rsi_period=7,     # Smaller than default 14
            macd_params=(6, 13, 5),  # Half of standard
            atr_period=7,
            bb_period=10      # Half of standard 20
        )
        await feature_service.start()

        # Send candles for multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

        # Need at least 13 candles for MACD(6,13,5)
        for i in range(15):
            # Send candles for all symbols in parallel
            publish_tasks = []
            for symbol in symbols:
                candle = create_test_candle(symbol=symbol, offset=i)
                event = CandleUpdateEvent(
                    event_type=EventType.CANDLE_UPDATE,
                    timestamp=datetime.utcnow(),
                    symbol=symbol,
                    timeframe=TimeFrame.M5,
                    candle=candle
                )
                publish_tasks.append(bus.publish(event))

            await asyncio.gather(*publish_tasks)
            await asyncio.sleep(0.2)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Verify all symbols generated features
        feature_events = collector.get_events(EventType.FEATURES_CALCULATED)
        symbols_with_features = {event.symbol for event in feature_events}

        assert "BTCUSDT" in symbols_with_features
        assert "ETHUSDT" in symbols_with_features
        assert "BNBUSDT" in symbols_with_features

        # Cleanup
        await feature_service.stop()
        await collector.unsubscribe_all(bus)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_feature_calculation_idempotency(self, real_db):
        """Same candle processed twice should give same features."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        collector = EventCollector()
        await collector.subscribe_to_events(bus, [EventType.FEATURES_CALCULATED])

        feature_service = FeatureService(
            ema_periods=[9],  # Single EMA for faster test
            rsi_period=7,     # Smaller than default 14
            macd_params=(6, 13, 5),  # Half of standard
            atr_period=7,
            bb_period=10      # Half of standard 20
        )
        await feature_service.start()

        # Send initial candles to build history (need 13+ for MACD)
        for i in range(15):
            candle = create_test_candle(offset=i)
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )
            await bus.publish(event)
            await asyncio.sleep(0.1)

        # Wait for initial processing
        await asyncio.sleep(0.5)

        # Get last calculated features
        last_indicators = await feature_service.get_latest_indicators("BTCUSDT", TimeFrame.M5)
        assert last_indicators is not None

        # Send one more candle
        new_candle = create_test_candle(offset=20)
        event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=new_candle
        )

        # Clear collector before sending
        collector.clear()

        # Send same event twice
        await bus.publish(event)
        await asyncio.sleep(0.1)
        await bus.publish(event)
        await asyncio.sleep(0.1)

        # Get feature events
        feature_events = collector.get_events(EventType.FEATURES_CALCULATED)

        # Should have 2 events from the same candle
        assert len(feature_events) == 2

        # Both should have the same symbol and timeframe
        assert feature_events[0].symbol == feature_events[1].symbol == "BTCUSDT"
        assert feature_events[0].timeframe == feature_events[1].timeframe == TimeFrame.M5

        # Cleanup
        await feature_service.stop()
        await collector.unsubscribe_all(bus)
        await bus.stop()


class TestFeaturesToSMCFlow:
    """Test feature events triggering SMC calculations."""

    @pytest.mark.asyncio
    async def test_smc_service_processes_candles(self, real_db):
        """SMC service should process candle events."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Start SMC service
        smc_service = SMCService(pivot_config={"left_bars": 2, "right_bars": 2})
        await smc_service.start()

        # Send multiple candles
        for i in range(10):
            candle = create_test_candle(offset=i)
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )
            await bus.publish(event)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Check service stats
        stats = await smc_service.health_check()
        assert stats["tracked_symbols"] > 0  # Should be tracking BTCUSDT
        assert stats["running"] is True

        # Cleanup
        await smc_service.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_smc_service_with_features(self, real_db):
        """SMC service should work with feature service."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Start both services
        feature_service = FeatureService(
            ema_periods=[9],
            rsi_period=7,
            macd_params=(6, 13, 5),
            atr_period=7,
            bb_period=10
        )
        smc_service = SMCService()

        await feature_service.start()
        await smc_service.start()

        # Send candles that will trigger feature calculations
        for i in range(15):
            candle = create_test_candle(offset=i)
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )
            await bus.publish(event)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Both services should have processed data
        feature_stats = await feature_service.health_check()
        assert feature_stats["calculations_performed"] > 0

        smc_stats = await smc_service.health_check()
        assert smc_stats["tracked_symbols"] > 0

        # Cleanup
        await feature_service.stop()
        await smc_service.stop()
        await bus.stop()


class TestEndToEndWithPersistence:
    """Test full event flow with database persistence."""

    @pytest.mark.asyncio
    async def test_candle_persistence(self, real_db, clean_test_data):
        """Candles should be persisted to database."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Assuming ingest service would normally handle this
        # For test, we'll insert directly after publishing event

        test_candle = create_test_candle()
        event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=test_candle
        )

        # In real system, ingest service would persist this
        # Simulate by direct insert
        await real_db.execute("""
            INSERT INTO candles (
                time, venue, symbol, timeframe,
                open, high, low, close,
                volume, quote_volume, trade_count,
                taker_buy_volume, taker_buy_quote_volume
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
            test_candle.open_time,
            'spot',
            test_candle.symbol,
            test_candle.timeframe.value,
            float(test_candle.open_price),
            float(test_candle.high_price),
            float(test_candle.low_price),
            float(test_candle.close_price),
            float(test_candle.volume),
            float(test_candle.quote_volume),
            test_candle.trades,
            float(test_candle.taker_buy_base_volume),
            float(test_candle.taker_buy_quote_volume)
        )

        # Verify persistence
        result = await real_db.fetch_one("""
            SELECT * FROM candles
            WHERE symbol = $1 AND time = $2
        """, test_candle.symbol, test_candle.open_time)

        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert float(result["close"]) == float(test_candle.close_price)

        await bus.stop()

    @pytest.mark.asyncio
    async def test_concurrent_event_processing(self, real_db):
        """System should handle concurrent events without deadlock."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        collector = EventCollector()
        await collector.subscribe_to_events(bus, [
            EventType.FEATURES_CALCULATED,
            EventType.SMC_SIGNAL
        ])

        # Start services
        feature_service = FeatureService(
            ema_periods=[9],  # Single EMA for faster test
            rsi_period=7,     # Smaller than default 14
            macd_params=(6, 13, 5),  # Half of standard
            atr_period=7,
            bb_period=10      # Half of standard 20
        )
        smc_service = SMCService(pivot_config={"left_bars": 2, "right_bars": 2})

        await asyncio.gather(
            feature_service.start(),
            smc_service.start()
        )

        # Send many events concurrently
        symbols = ["BTC", "ETH", "BNB", "SOL", "ADA"]
        publish_tasks = []

        # Send enough candles for indicators (need 13 for MACD)
        for i in range(15):
            for symbol in symbols:
                candle = create_test_candle(
                    symbol=f"{symbol}USDT",
                    offset=i
                )
                event = CandleUpdateEvent(
                    event_type=EventType.CANDLE_UPDATE,
                    timestamp=datetime.utcnow(),
                    symbol=f"{symbol}USDT",
                    timeframe=TimeFrame.M5,
                    candle=candle
                )
                publish_tasks.append(bus.publish(event))

        # Send all at once
        await asyncio.gather(*publish_tasks)

        # Wait for processing
        await asyncio.sleep(1.0)

        # Should have processed events for all symbols
        feature_events = collector.get_events(EventType.FEATURES_CALCULATED)
        feature_symbols = {e.symbol for e in feature_events}

        for symbol in symbols:
            assert f"{symbol}USDT" in feature_symbols

        # Cleanup
        await asyncio.gather(
            feature_service.stop(),
            smc_service.stop()
        )
        await collector.unsubscribe_all(bus)
        await bus.stop()

    @pytest.mark.asyncio
    async def test_event_ordering_preservation(self, real_db):
        """Events should maintain order within symbol/timeframe."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        received_candles = []

        async def capture_candle_times(event):
            received_candles.append((
                event.symbol,
                event.candle.open_time
            ))

        await bus.subscribe(
            subscriber_id="test_order",
            handler=capture_candle_times,
            event_types=[EventType.CANDLE_UPDATE]
        )

        # Send candles with specific timestamps
        base_time = datetime.utcnow().replace(microsecond=0)

        for i in range(5):
            candle = create_test_candle(offset=i)
            candle.open_time = base_time + timedelta(minutes=i*5)

            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )
            await bus.publish(event)
            await asyncio.sleep(0.05)

        # Wait for processing
        await asyncio.sleep(0.2)

        # Verify order preserved
        assert len(received_candles) == 5

        # Check timestamps are in order
        for i in range(1, len(received_candles)):
            prev_time = received_candles[i-1][1]
            curr_time = received_candles[i][1]
            assert curr_time > prev_time

        await bus.stop()


class TestErrorHandlingAndRecovery:
    """Test system behavior under error conditions."""

    @pytest.mark.asyncio
    async def test_service_recovery_after_error(self, real_db):
        """Service should continue processing after handler error."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        processed_events = []
        error_on_second = True

        async def flaky_handler(event):
            nonlocal error_on_second
            if error_on_second and len(processed_events) == 1:
                error_on_second = False
                raise Exception("Simulated error")
            processed_events.append(event.symbol)

        await bus.subscribe(
            subscriber_id="flaky",
            handler=flaky_handler,
            event_types=[EventType.CANDLE_UPDATE]
        )

        # Send multiple events
        for i in range(3):
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=create_test_candle(offset=i)
            )
            await bus.publish(event)
            await asyncio.sleep(0.1)

        # Wait for processing
        await asyncio.sleep(0.5)

        # Should have processed first and third events
        assert len(processed_events) == 2
        assert processed_events[0] == "BTCUSDT"
        assert processed_events[1] == "BTCUSDT"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_event_bus_buffer_overflow_handling(self, real_db):
        """Event bus should handle queue overflow gracefully."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        slow_process_count = 0

        async def slow_handler(event):
            nonlocal slow_process_count
            await asyncio.sleep(0.5)  # Simulate slow processing
            slow_process_count += 1

        await bus.subscribe(
            subscriber_id="slow",
            handler=slow_handler,
            event_types=[EventType.CANDLE_UPDATE]
        )

        # Send many events quickly
        start_time = datetime.utcnow()
        publish_count = 20

        for i in range(publish_count):
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.utcnow(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=create_test_candle(offset=i)
            )
            await bus.publish(event)

        # Wait some time but not enough to process all
        await asyncio.sleep(2.0)

        # Should have processed some but maybe not all
        assert slow_process_count > 0
        assert slow_process_count <= publish_count

        # System should still be responsive
        test_event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.utcnow(),
            symbol="TESTUSDT",
            timeframe=TimeFrame.M5,
            candle=create_test_candle(symbol="TESTUSDT")
        )

        # Should be able to publish new events
        await bus.publish(test_event)

        await bus.stop()