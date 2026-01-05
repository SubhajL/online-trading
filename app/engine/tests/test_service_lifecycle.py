"""
Test service lifecycle - start, stop, event subscription.

These tests verify that services can properly start up,
subscribe to events, process them, and shut down cleanly.
"""

import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock

import pytest

from app.engine.bus import create_event_bus, set_event_bus
from app.engine.models import (
    Candle, TimeFrame, EventType,
    CandleUpdateEvent, FeaturesCalculatedEvent
)
from app.engine.features.feature_service import FeatureService
from app.engine.smc.smc_service import SMCService


def create_test_candle(symbol="BTCUSDT", price_offset=0):
    """Create a valid test candle."""
    return Candle(
        venue="spot",
        symbol=symbol,
        timeframe=TimeFrame.M5,
        open_time=datetime.now(),
        close_time=datetime.now(),
        open_price=Decimal("50000") + Decimal(str(price_offset)),
        high_price=Decimal("50100") + Decimal(str(price_offset)),
        low_price=Decimal("49900") + Decimal(str(price_offset)),
        close_price=Decimal("50050") + Decimal(str(price_offset)),
        volume=Decimal("100"),
        quote_volume=Decimal("5000000"),
        trades=1000,
        taker_buy_base_volume=Decimal("60"),
        taker_buy_quote_volume=Decimal("3000000")
    )


class TestServiceStartStop:
    """Test basic service lifecycle operations."""

    @pytest.mark.asyncio
    async def test_feature_service_lifecycle(self):
        """Feature service should start, run, and stop cleanly."""
        # Set up event bus
        bus = create_event_bus()
        set_event_bus(bus)

        # Create service
        service = FeatureService()

        # Start service
        await service.start()
        assert service._running is True
        assert service._subscription_id is not None

        # Stop service
        await service.stop()
        assert service._running is False
        # Subscription should be cleaned up
        await asyncio.sleep(0.1)  # Give time for cleanup

    @pytest.mark.asyncio
    async def test_smc_service_lifecycle(self):
        """SMC service should start, run, and stop cleanly."""
        # Set up event bus
        bus = create_event_bus()
        set_event_bus(bus)

        # Create service
        service = SMCService()

        # Start service
        await service.start()
        assert service._running is True
        assert service._subscription_id is not None

        # Stop service
        await service.stop()
        assert service._running is False

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self):
        """Services should handle multiple start/stop cycles."""
        bus = create_event_bus()
        set_event_bus(bus)

        service = FeatureService()

        # First cycle
        await service.start()
        assert service._running is True
        await service.stop()
        assert service._running is False

        # Second cycle should also work
        await service.start()
        assert service._running is True
        await service.stop()
        assert service._running is False

    @pytest.mark.asyncio
    async def test_concurrent_service_startup(self):
        """Multiple services should start concurrently without issues."""
        bus = create_event_bus()
        set_event_bus(bus)

        feature_service = FeatureService()
        smc_service = SMCService()

        # Start both services concurrently
        await asyncio.gather(
            feature_service.start(),
            smc_service.start()
        )

        assert feature_service._running is True
        assert smc_service._running is True

        # Stop both services
        await asyncio.gather(
            feature_service.stop(),
            smc_service.stop()
        )

        assert feature_service._running is False
        assert smc_service._running is False


class TestEventSubscription:
    """Test event subscription and handling."""

    @pytest.mark.asyncio
    async def test_feature_service_receives_candle_events(self):
        """Feature service should receive and process candle events."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Create service with minimal periods for testing
        service = FeatureService(
            ema_periods=[2, 3],  # Small EMAs
            rsi_period=2,
            macd_params=(2, 3, 2),
            atr_period=2,
            bb_period=2
        )
        await service.start()

        # Create test candle event
        candle = Candle(
            venue="spot",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            open_time=datetime.now(),
            close_time=datetime.now(),
            open_price=Decimal("50000"),
            high_price=Decimal("50100"),
            low_price=Decimal("49900"),
            close_price=Decimal("50050"),
            volume=Decimal("100"),
            quote_volume=Decimal("5000000"),
            trades=1000,
            taker_buy_base_volume=Decimal("60"),
            taker_buy_quote_volume=Decimal("3000000")
        )

        event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=candle
        )

        # Track if features were calculated
        features_published = []

        async def capture_features(event_data):
            features_published.append(event_data)

        await bus.subscribe(
            subscriber_id="test_capture",
            handler=capture_features,
            event_types=[EventType.FEATURES_CALCULATED]
        )

        # Need to send at least 3 candles (max of our periods)
        for i in range(3):
            candle = Candle(
                venue="spot",
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                open_time=datetime.now(),
                close_time=datetime.now(),
                open_price=Decimal("50000") + Decimal(str(i * 100)),
                high_price=Decimal("50100") + Decimal(str(i * 100)),
                low_price=Decimal("49900") + Decimal(str(i * 100)),
                close_price=Decimal("50050") + Decimal(str(i * 100)),
                volume=Decimal("100"),
                quote_volume=Decimal("5000000"),
                trades=1000,
                taker_buy_base_volume=Decimal("60"),
                taker_buy_quote_volume=Decimal("3000000")
            )

            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                timeframe=TimeFrame.M5,
                candle=candle
            )

            await bus.publish(event)
            await asyncio.sleep(0.1)  # Small delay between candles

        # Wait for processing
        await asyncio.sleep(0.5)

        # Should have published features
        assert len(features_published) > 0
        assert features_published[0].symbol == "BTCUSDT"

        await service.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_event_handler_error_isolation(self):
        """One handler's error shouldn't affect other handlers."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Create handlers
        successful_calls = []
        failing_handler = AsyncMock(side_effect=Exception("Handler error"))
        successful_handler = AsyncMock(side_effect=lambda x: successful_calls.append(x))

        # Subscribe both handlers
        await bus.subscribe(
            subscriber_id="failing",
            handler=failing_handler,
            event_types=[EventType.CANDLE_UPDATE]
        )

        await bus.subscribe(
            subscriber_id="successful",
            handler=successful_handler,
            event_types=[EventType.CANDLE_UPDATE]
        )

        # Create test event
        event = CandleUpdateEvent(
            event_type=EventType.CANDLE_UPDATE,
            timestamp=datetime.now(),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M5,
            candle=create_test_candle()
        )

        # Publish event
        await bus.publish(event)
        await asyncio.sleep(0.2)

        # Verify failing handler was called and failed
        failing_handler.assert_called()

        # Verify successful handler was still called
        assert len(successful_calls) == 1

        await bus.stop()


class TestGracefulShutdown:
    """Test graceful shutdown scenarios."""

    @pytest.mark.asyncio
    async def test_service_drains_queue_before_shutdown(self):
        """Service should process pending events before shutdown."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        # Track processed events
        processed_events = []

        # Custom handler that tracks events
        class TrackingFeatureService(FeatureService):
            async def _handle_candle_update(self, event_data):
                processed_events.append(event_data.candle.symbol)
                # Call parent to maintain buffer
                await super()._handle_candle_update(event_data)

        service = TrackingFeatureService(
            ema_periods=[2],  # Minimal for testing
            rsi_period=2,
            macd_params=(2, 3, 2),
            atr_period=2,
            bb_period=2
        )
        await service.start()

        # Publish multiple events quickly
        for i in range(3):
            event = CandleUpdateEvent(
                event_type=EventType.CANDLE_UPDATE,
                timestamp=datetime.now(),
                symbol=f"TEST{i}USDT",
                timeframe=TimeFrame.M5,
                candle=create_test_candle(symbol=f"TEST{i}USDT")
            )
            await bus.publish(event)

        # Small delay to ensure events are queued
        await asyncio.sleep(0.05)

        # Stop service - it should process remaining events
        await service.stop()

        # All events should have been processed
        assert len(processed_events) == 3
        assert set(processed_events) == {"TEST0USDT", "TEST1USDT", "TEST2USDT"}

        await bus.stop()

    @pytest.mark.asyncio
    async def test_service_cleanup_on_unexpected_stop(self):
        """Service should clean up resources even on unexpected stop."""
        bus = create_event_bus()
        set_event_bus(bus)
        await bus.start()

        service = FeatureService()
        await service.start()

        # Simulate unexpected stop by directly setting running to False
        service._running = False

        # Proper stop should still work without errors
        await service.stop()

        # Service should be in clean state
        assert service._running is False

        await bus.stop()