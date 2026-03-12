from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.engine.contracts.contract_publisher import ContractPublisher
from app.engine.models import (
    Candle,
    CandleOrigin,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    OrderUpdate,
    OrderUpdateEvent,
    RetestSignal,
    RetestSignalEvent,
    TechnicalIndicators,
    TimeFrame,
    TradingDecision,
    TradingDecisionEvent,
)
from app.engine.smc_types import (
    Pivot,
    SMCEvent,
    SMCEventKind,
    StructureBreakEvent,
    StructureState,
    Zone,
    ZoneEvent,
    ZoneSide,
)


class _FakeBus:
    def __init__(self) -> None:
        self.subscribe = AsyncMock(return_value="sub-id")
        self.unsubscribe = AsyncMock(return_value=True)


@pytest.mark.asyncio
async def test_contract_publisher_publishes_candles_v1_for_realtime_only() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    candle = Candle(
        venue="SPOT",
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        open_time=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        close_time=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        close_price=Decimal("105"),
        volume=Decimal("1"),
        quote_volume=Decimal("100"),
        trades=1,
        taker_buy_base_volume=Decimal("0.5"),
        taker_buy_quote_volume=Decimal("50"),
        bar_index=1,
    )

    await publisher.on_candle_update(
        CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=candle,
            origin=CandleOrigin.BACKFILL,
        ),
    )
    assert redis.publish.await_count == 0

    await publisher.on_candle_update(
        CandleUpdateEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            candle=candle,
            origin=CandleOrigin.REALTIME,
        ),
    )
    redis.publish.assert_awaited()
    channel, payload = redis.publish.await_args.args
    assert channel == "engine:candles.v1"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["timeframe"] == "15m"


@pytest.mark.asyncio
async def test_contract_publisher_publishes_features_v1_payload_shape() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    features = TechnicalIndicators(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        ema_21=Decimal("101"),
        ema_200=Decimal("99"),
        rsi_14=Decimal("55"),
        macd_line=Decimal("1.2"),
        macd_signal=Decimal("1.0"),
        macd_histogram=Decimal("0.2"),
        atr_14=Decimal("10"),
        bb_upper=Decimal("120"),
        bb_middle=Decimal("100"),
        bb_lower=Decimal("80"),
    )

    event = FeaturesCalculatedEvent(
        timestamp=datetime.now(UTC),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        features=features,
        metadata={
            "venue": "SPOT",
            "open_time": datetime(2025, 1, 1, 0, 0, tzinfo=UTC).isoformat(),
            "close_time": datetime(2025, 1, 1, 0, 15, tzinfo=UTC).isoformat(),
        },
    )

    await publisher.on_features_calculated(event)
    channel, payload = redis.publish.await_args.args
    assert channel == "engine:features.v1"
    assert payload["ema_short"] is not None
    assert "volume_ma" in payload


@pytest.mark.asyncio
async def test_contract_publisher_publishes_signals_raw_v1() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    signal = RetestSignal(
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        level_price=Decimal("100"),
        direction="BUY",
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        take_profit_2=Decimal("115"),
        take_profit_3=Decimal("120"),
        retest_type="zone_retest",
        success_probability=Decimal("0.7"),
        volume_confirmation=True,
        confluence_factors=["bos_confirmation"],
        venue="SPOT",
    )

    await publisher.on_retest_signal(
        RetestSignalEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            signal=signal,
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:signals_raw.v1"
    assert payload["signal_type"] == "long"
    assert payload["take_profit_3"] == "120"


@pytest.mark.asyncio
async def test_contract_publisher_publishes_decision_v1() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    decision = TradingDecision(
        symbol="BTCUSDT",
        timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        action="BUY",
        entry_price=Decimal("100"),
        quantity=Decimal("0.01"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        confidence=Decimal("0.8"),
        reasoning="test",
        venue="SPOT",
    )

    await publisher.on_trading_decision(
        TradingDecisionEvent(
            timestamp=datetime.now(UTC),
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            decision=decision,
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:decision.v1"
    assert payload["action"] == "open_long"


@pytest.mark.asyncio
async def test_contract_publisher_publishes_smc_events_v1() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    pivot = Pivot(
        timestamp=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        price=Decimal("100"),
        is_high=True,
        strength=1,
        bar_index=1,
    )
    smc_event = SMCEvent(
        kind=SMCEventKind.BOS,
        timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        price=Decimal("101"),
        from_state=StructureState.NEUTRAL,
        to_state=StructureState.BULLISH,
        trigger_pivot=pivot,
        reference_pivot=pivot,
        strength=Decimal("1.0"),
    )

    await publisher.on_smc_event(
        StructureBreakEvent(
            timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            smc_event=smc_event,
            current_state=StructureState.BULLISH,
            key_levels={},
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:smc_events.v1"
    assert payload["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_contract_publisher_publishes_zones_v1() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    zone = Zone(
        zone_id=uuid4(),
        symbol="BTCUSDT",
        timeframe=TimeFrame.M15,
        zone_type="FVG",
        side=ZoneSide.LOW,
        top_price=Decimal("100"),
        bottom_price=Decimal("95"),
        created_at=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        created_bar_index=1,
        expiry_bars=10,
        strength=Decimal("0.5"),
        touches=0,
    )

    await publisher.on_zone_event(
        ZoneEvent(
            timestamp=datetime.now(UTC),
            venue="SPOT",
            symbol="BTCUSDT",
            timeframe=TimeFrame.M15,
            zone=zone,
            action="created",
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:zones.v1"
    assert payload["zone_id"] == str(zone.zone_id)


@pytest.mark.asyncio
async def test_contract_publisher_publishes_order_update_v1() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    update = OrderUpdate(
        venue="SPOT",
        symbol="BTCUSDT",
        order_id=123,
        client_order_id="cid",
        status="NEW",
        side="BUY",
        order_type="LIMIT",
        price=Decimal("100"),
        quantity=Decimal("1"),
        executed_qty=Decimal("0"),
        update_time=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        reason=None,
    )

    await publisher.on_order_update(
        OrderUpdateEvent(
            timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            symbol="BTCUSDT",
            metadata={"decision_id": "dec-1", "reduce_only": True},
            update=update,
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:order_update.v1"
    assert payload["decision_id"] == "dec-1"
    assert payload["status"] == "new"


@pytest.mark.asyncio
async def test_contract_publisher_publishes_order_update_v1_with_uuid_decision_id() -> None:
    redis = AsyncMock()
    bus = _FakeBus()
    publisher = ContractPublisher(bus=bus, redis=redis)
    await publisher.start()

    decision_id = uuid4()
    update = OrderUpdate(
        venue="SPOT",
        symbol="BTCUSDT",
        order_id=123,
        client_order_id="cid",
        status="NEW",
        side="BUY",
        order_type="LIMIT",
        price=Decimal("100"),
        quantity=Decimal("1"),
        executed_qty=Decimal("0"),
        update_time=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
        reason=None,
    )

    await publisher.on_order_update(
        OrderUpdateEvent(
            timestamp=datetime(2025, 1, 1, 0, 15, tzinfo=UTC),
            symbol="BTCUSDT",
            metadata={"decision_id": decision_id},
            update=update,
        ),
    )

    channel, payload = redis.publish.await_args.args
    assert channel == "engine:order_update.v1"
    assert payload["decision_id"] == str(decision_id)
