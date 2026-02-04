"""
Type definitions for the trading engine.

This module contains all Pydantic models and type definitions used across
the trading platform, including events, market data, signals, and decisions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import enum as _enum
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field, field_serializer, field_validator
from pydantic.config import ConfigDict

UUID = uuid.UUID
uuid4 = uuid.uuid4
Enum = _enum.Enum


# ============================================================================
# Base Types and Enums
# ============================================================================


class TimeFrame(str, Enum):
    """Supported timeframes for candle data"""

    __slots__ = ()

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    D3 = "3d"
    W1 = "1w"
    MONTH1 = "1M"


class OrderSide(str, Enum):
    """Order side enumeration"""

    __slots__ = ()

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type enumeration"""

    __slots__ = ()

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderStatus(str, Enum):
    """Order status enumeration"""

    __slots__ = ()

    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionSide(str, Enum):
    """Position side enumeration"""

    __slots__ = ()

    LONG = "LONG"
    SHORT = "SHORT"


class CandleOrigin(str, Enum):
    """Origin of candle data for pipeline gating"""

    __slots__ = ()

    REALTIME = "realtime"
    BACKFILL = "backfill"
    GAP_FILL = "gap_fill"


def is_realtime_candle_event(origin: CandleOrigin) -> bool:
    """Check if candle origin should trigger trading pipeline.

    Only REALTIME events should trigger full pipeline processing
    (features calculation, SMC analysis, trading decisions).
    BACKFILL and GAP_FILL events are for data seeding/warm-up only.
    """
    return origin == CandleOrigin.REALTIME


class EventType(str, Enum):
    """Event type enumeration for the event bus"""

    __slots__ = ()

    CANDLE_UPDATE = "candle_update"
    FEATURES_CALCULATED = "features_calculated"
    SMC_SIGNAL = "smc_signal"
    SMC_EVENT = "smc_event"
    ZONE_UPDATE = "zone_update"
    RETEST_SIGNAL = "retest_signal"
    REGIME_UPDATE = "regime_update"
    VOLATILITY_UPDATE = "volatility_update"
    NEWS_ALERT = "news_alert"
    FUNDING_ALERT = "funding_alert"
    TRADING_DECISION = "trading_decision"
    ORDER_UPDATE = "order_update"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    POSITION_UPDATE = "position_update"
    HEALTH_CHECK = "health_check"
    ERROR = "error"
    STARTUP_COMPLETE = "startup_complete"


class MarketRegime(str, Enum):
    """Market regime classification"""

    __slots__ = ()

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"


class SMCStructure(str, Enum):
    """Smart Money Concepts structure types"""

    __slots__ = ()

    HIGHER_HIGH = "HH"
    HIGHER_LOW = "HL"
    LOWER_HIGH = "LH"
    LOWER_LOW = "LL"
    EQUAL_HIGH = "EH"
    EQUAL_LOW = "EL"


class ZoneType(str, Enum):
    """Supply/Demand zone types"""

    __slots__ = ()

    SUPPLY = "SUPPLY"
    DEMAND = "DEMAND"
    ORDER_BLOCK_BULLISH = "ORDER_BLOCK_BULLISH"
    ORDER_BLOCK_BEARISH = "ORDER_BLOCK_BEARISH"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"


# ============================================================================
# Base Event Model
# ============================================================================


class BaseEvent(BaseModel):
    """Base event model for all events in the system"""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    timestamp: datetime
    symbol: str
    timeframe: TimeFrame | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict()

    @field_serializer("timestamp")
    def _ser_ts(self, v: datetime) -> str:
        # Ensure timezone-aware ISO string
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()

    def __lt__(self, other: BaseEvent) -> bool:
        """Compare events by event_id for priority queue ordering.

        This is required when events have equal priority and timestamp
        in asyncio.PriorityQueue to provide stable ordering.
        """
        return str(self.event_id) < str(other.event_id)


class NonPositivePriceError(ValueError):
    def __init__(self) -> None:
        super().__init__("Price values must be positive")


class NegativeVolumeError(ValueError):
    def __init__(self) -> None:
        super().__init__("Volume values must be non-negative")


# ============================================================================
# Market Data Models
# ============================================================================


class Candle(BaseModel):
    """OHLCV candle data"""

    venue: str
    symbol: str
    timeframe: TimeFrame
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal
    bar_index: int | None = (
        None  # Bar index within the sequence (optional for backward compatibility)
    )

    @field_validator(
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        mode="after",
    )
    def ensure_price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise NonPositivePriceError
        return v

    @field_validator(
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        mode="after",
    )
    def ensure_volume_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise NegativeVolumeError
        return v

    @field_serializer(
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    )
    def _ser_decimal(self, v: Decimal) -> str:
        return str(v)


class Ticker(BaseModel):
    """24hr ticker data"""

    symbol: str
    price_change: Decimal
    price_change_percent: Decimal
    weighted_avg_price: Decimal
    prev_close_price: Decimal
    last_price: Decimal
    last_qty: Decimal
    bid_price: Decimal
    ask_price: Decimal
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    volume: Decimal
    quote_volume: Decimal
    open_time: datetime
    close_time: datetime
    count: int

    @field_serializer(
        "price_change",
        "price_change_percent",
        "weighted_avg_price",
        "prev_close_price",
        "last_price",
        "last_qty",
        "bid_price",
        "ask_price",
        "open_price",
        "high_price",
        "low_price",
        "volume",
        "quote_volume",
    )
    def _ser_ticker_decimals(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("open_time", "close_time")
    def _ser_ticker_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


# ============================================================================
# Technical Analysis Models
# ============================================================================


class TechnicalIndicators(BaseModel):
    """Technical indicators calculated for a candle"""

    symbol: str
    timeframe: TimeFrame
    timestamp: datetime

    # Moving Averages
    ema_9: Decimal | None = None
    ema_21: Decimal | None = None
    ema_50: Decimal | None = None
    ema_200: Decimal | None = None

    # RSI
    rsi_14: Decimal | None = None

    # MACD
    macd_line: Decimal | None = None
    macd_signal: Decimal | None = None
    macd_histogram: Decimal | None = None

    # ATR
    atr_14: Decimal | None = None

    # Bollinger Bands
    bb_upper: Decimal | None = None
    bb_middle: Decimal | None = None
    bb_lower: Decimal | None = None
    bb_width: Decimal | None = None
    bb_percent: Decimal | None = None

    @field_serializer(
        "ema_9",
        "ema_21",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd_line",
        "macd_signal",
        "macd_histogram",
        "atr_14",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "bb_width",
        "bb_percent",
    )
    def _ser_ti_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    @field_serializer("timestamp")
    def _ser_ti_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


# ============================================================================
# Smart Money Concepts Models
# ============================================================================


class PivotPoint(BaseModel):
    """Pivot point identification"""

    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    price: Decimal
    is_high: bool
    strength: int = Field(ge=1, le=10)
    volume_profile: Decimal | None = None

    @field_serializer("price", "volume_profile")
    def _ser_pp_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class SupplyDemandZone(BaseModel):
    """Supply/Demand zone identification"""

    zone_id: UUID = Field(default_factory=uuid4)
    symbol: str
    timeframe: TimeFrame
    zone_type: ZoneType
    top_price: Decimal
    bottom_price: Decimal
    created_at: datetime
    strength: int = Field(ge=1, le=10)
    volume_profile: Decimal
    touches: int = Field(default=0)
    is_active: bool = Field(default=True)
    tested_at: datetime | None = None

    @field_serializer("top_price", "bottom_price", "volume_profile")
    def _ser_zone_decimals(self, v: Decimal) -> str:
        return str(v)


class MarketStructure(BaseModel):
    """Market structure analysis"""

    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    structure_type: SMCStructure
    price: Decimal
    previous_structure: SMCStructure | None = None
    trend_direction: str | None = None  # "bullish", "bearish", "neutral"

    @field_serializer("price")
    def _ser_ms_price(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("timestamp")
    def _ser_ms_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


# ============================================================================
# Signal Models
# ============================================================================


class SMCSignal(BaseModel):
    """Smart Money Concepts signal"""

    signal_id: UUID = Field(default_factory=uuid4)
    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    signal_type: str  # "order_block_entry", "liquidity_grab", "fair_value_gap"
    direction: OrderSide
    entry_price: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    confidence: Decimal = Field(ge=0, le=1)
    zone: SupplyDemandZone | None = None
    reasoning: str

    @field_serializer("timestamp")
    def _ser_sig_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()

    @field_serializer("entry_price", "stop_loss", "take_profit", "confidence")
    def _ser_signal_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


# ============================================================================
# Additional Event Models for End-to-End Flows
# ============================================================================


class FeaturesUpdateEvent(BaseEvent):
    """Event emitted when features are updated/calculated for a symbol/timeframe."""

    event_type: EventType = EventType.FEATURES_CALCULATED
    symbol: str
    timeframe: TimeFrame
    features: TechnicalIndicators


class SignalEvent(BaseEvent):
    """Generic trading signal event wrapping an SMC signal."""

    event_type: EventType = EventType.SMC_SIGNAL
    signal: SMCSignal


class SMCEvent(BaseEvent):
    """Generic SMC event container used in test flows."""

    event_type: EventType = EventType.SMC_EVENT
    payload: dict[str, Any] = Field(default_factory=dict)


class ZoneEvent(BaseEvent):
    """Zone update event wrapping a supply/demand zone."""

    event_type: EventType = EventType.ZONE_UPDATE
    zone: SupplyDemandZone


class RetestSignal(BaseModel):
    """Retest signal for zones and levels"""

    signal_id: UUID = Field(default_factory=uuid4)
    venue: str
    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    level_price: Decimal
    direction: Literal["BUY", "SELL"]
    stop_loss: Decimal
    take_profit: Decimal
    take_profit_2: Decimal | None = None
    take_profit_3: Decimal | None = None
    retest_type: str  # "support_retest", "resistance_retest", "zone_retest"
    success_probability: Decimal = Field(ge=0, le=1)
    volume_confirmation: bool
    confluence_factors: list[str] = Field(default_factory=list)

    @field_serializer("timestamp")
    def _ser_rt_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()

    @field_serializer(
        "level_price",
        "stop_loss",
        "take_profit",
        "take_profit_2",
        "take_profit_3",
        "success_probability",
    )
    def _ser_retest_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


# ============================================================================
# Risk Management Models
# ============================================================================


class RiskParameters(BaseModel):
    """Risk management parameters"""

    max_position_size: Decimal = Field(gt=0)
    max_daily_loss: Decimal = Field(gt=0)
    max_drawdown: Decimal = Field(gt=0)
    risk_per_trade: Decimal = Field(gt=0, le=0.1)  # Max 10% per trade
    max_correlation: Decimal = Field(ge=0, le=1)
    max_open_positions: int = Field(ge=1)
    max_total_exposure_leverage: Decimal = Field(gt=0)
    max_symbol_exposure_pct: Decimal = Field(gt=0, le=1)
    max_position_notional_pct: Decimal = Field(gt=0, le=1)
    risk_data_max_age_seconds: int = Field(ge=1)
    drawdown_lookback_days: int = Field(ge=1)
    allowed_symbols: list[str] = Field(default_factory=list)
    trading_hours: dict[str, Any] | None = None


class PositionSizing(BaseModel):
    """Position sizing calculation"""

    symbol: str
    entry_price: Decimal
    stop_loss: Decimal
    risk_amount: Decimal
    position_size: Decimal
    leverage: Decimal = Field(default=Decimal(1))
    margin_required: Decimal


# ============================================================================
# Trading Decision Models
# ============================================================================


class TradingDecision(BaseModel):
    """Trading decision with full context"""

    decision_id: UUID = Field(default_factory=uuid4)
    venue: str
    symbol: str
    timestamp: datetime
    action: str  # "BUY", "SELL", "HOLD", "CLOSE"

    # Entry details
    entry_price: Decimal | None = None
    quantity: Decimal | None = None
    order_type: OrderType | None = None

    # Risk management
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    position_sizing: PositionSizing | None = None

    # Signal context
    signals: list[SMCSignal | RetestSignal] = Field(default_factory=list)
    technical_indicators: TechnicalIndicators | None = None
    market_regime: MarketRegime | None = None

    # Decision rationale
    confidence: Decimal = Field(ge=0, le=1)
    reasoning: str
    risk_reward_ratio: Decimal | None = None

    @field_serializer("timestamp")
    def _ser_td_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()

    @field_serializer(
        "entry_price",
        "quantity",
        "stop_loss",
        "take_profit",
        "confidence",
        "risk_reward_ratio",
    )
    def _ser_td_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    # Guards and filters
    news_sentiment: str | None = None
    funding_rate_impact: Decimal | None = None
    volatility_filter: bool = Field(default=True)


# ============================================================================
# Order and Position Models
# ============================================================================


class Order(BaseModel):
    """Order representation"""

    order_id: UUID = Field(default_factory=uuid4)
    client_order_id: str
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "GTC"
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Field(default=Decimal(0))
    average_fill_price: Decimal | None = None
    created_at: datetime
    updated_at: datetime | None = None

    # Associated decision
    decision_id: UUID | None = None


class OrderUpdate(BaseModel):
    """Order status update originating from the router/exchange."""

    venue: str | None = None
    symbol: str
    order_id: int | None = None
    client_order_id: str
    status: str
    side: str | None = None
    order_type: str | None = None
    price: Decimal | None = None
    quantity: Decimal | None = None
    executed_qty: Decimal | None = None
    update_time: datetime | None = None
    reason: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_serializer("price", "quantity", "executed_qty")
    def _ser_update_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)


class Position(BaseModel):
    """Position representation"""

    position_id: UUID = Field(default_factory=uuid4)
    symbol: str
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal = Field(default=Decimal(0))
    margin_used: Decimal
    leverage: Decimal = Field(default=Decimal(1))
    opened_at: datetime
    updated_at: datetime

    # Risk management
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    # Associated decision
    decision_id: UUID | None = None


# ============================================================================
# Event Models
# ============================================================================


class CandleUpdateEvent(BaseEvent):
    """Candle update event"""

    event_type: EventType = EventType.CANDLE_UPDATE
    candle: Candle
    origin: CandleOrigin = CandleOrigin.REALTIME


class FeaturesCalculatedEvent(BaseEvent):
    """Features calculated event"""

    event_type: EventType = EventType.FEATURES_CALCULATED
    features: TechnicalIndicators


class FeatureUpdateEvent(BaseEvent):
    """Feature update event (alias for FeaturesCalculatedEvent for compatibility)"""

    event_type: EventType = EventType.FEATURES_CALCULATED
    features: TechnicalIndicators


class SMCSignalEvent(BaseEvent):
    """SMC signal event"""

    event_type: EventType = EventType.SMC_SIGNAL
    signal: SMCSignal


class RetestSignalEvent(BaseEvent):
    """Retest signal event"""

    event_type: EventType = EventType.RETEST_SIGNAL
    signal: RetestSignal


class TradingDecisionEvent(BaseEvent):
    """Trading decision event"""

    event_type: EventType = EventType.TRADING_DECISION
    decision: TradingDecision


class OrderPlacedEvent(BaseEvent):
    """Order placed event.

    When emitted by RouterExecutionSubscriber with enriched context,
    includes decision and router_response for rich alert formatting.
    """

    event_type: EventType = EventType.ORDER_PLACED
    order: Order
    # Optional enriched context for alerts (backward compatible)
    decision: TradingDecision | None = None
    router_response: dict[str, Any] | None = None


class OrderUpdateEvent(BaseEvent):
    """Order update event emitted from router/exchange order updates."""

    event_type: EventType = EventType.ORDER_UPDATE
    update: OrderUpdate


class OrderFilledEvent(BaseEvent):
    """Order filled event"""

    event_type: EventType = EventType.ORDER_FILLED
    order: Order
    fill_price: Decimal
    fill_quantity: Decimal
    fill_timestamp: datetime

    @field_serializer("fill_price", "fill_quantity")
    def _ser_fill_decimals(self, v: Decimal) -> str:
        return str(v)


class PositionUpdateEvent(BaseEvent):
    """Position update event"""

    event_type: EventType = EventType.POSITION_UPDATE
    position: Position


class ErrorEvent(BaseEvent):
    """Error event"""

    event_type: EventType = EventType.ERROR
    error_type: str
    error_message: str
    stack_trace: str | None = None
    component: str


class StartupCompleteEvent(BaseEvent):
    """Startup/warmup complete event for alerting.

    Emitted when backfill completes or first realtime candle is received.
    """

    event_type: EventType = EventType.STARTUP_COMPLETE
    phase: str  # "backfill_complete" or "realtime_active"
    symbols: list[str]
    timeframes: list[str]
    candle_counts: dict[str, int]  # symbol -> count
    duration_seconds: float


# ============================================================================
# Health and Metrics Models
# ============================================================================


class HealthStatus(BaseModel):
    """Health status model"""

    service: str
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)
    response_time_ms: float | None = None

    @field_serializer("timestamp")
    def _ser_health_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


class SystemMetrics(BaseModel):
    """System metrics"""

    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: dict[str, float]
    active_connections: int
    events_processed: int
    errors_count: int
    uptime_seconds: float

    @field_serializer("timestamp")
    def _ser_sys_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


class TradingMetrics(BaseModel):
    """Trading performance metrics"""

    timestamp: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_pnl: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Decimal | None = None
    profit_factor: Decimal | None = None
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal

    @field_serializer(
        "win_rate",
        "total_pnl",
        "max_drawdown",
        "sharpe_ratio",
        "profit_factor",
        "average_win",
        "average_loss",
        "largest_win",
        "largest_loss",
    )
    def _ser_tm_decimals(self, v: Decimal | None) -> str | None:
        return None if v is None else str(v)

    @field_serializer("timestamp")
    def _ser_tm_ts(self, v: datetime) -> str:
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        return v.isoformat()


# ============================================================================
# Configuration Models
# ============================================================================


class DatabaseConfig(BaseModel):
    """Database configuration"""

    host: str
    port: int
    database: str
    username: str
    password: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


class RedisConfig(BaseModel):
    """Redis configuration"""

    host: str
    port: int = 6379
    password: str | None = None
    database: int = 0
    max_connections: int = 10


class BinanceConfig(BaseModel):
    """Binance API configuration"""

    api_key: str
    api_secret: str
    testnet: bool = True
    base_url: str | None = None
    ws_base_url: str | None = None


class EngineConfig(BaseModel):
    """Main engine configuration"""

    environment: str = "development"
    log_level: str = "INFO"

    # External services
    database: DatabaseConfig
    redis: RedisConfig
    binance: BinanceConfig

    # Trading configuration
    risk_parameters: RiskParameters

    # Feature flags
    features: dict[str, bool] = Field(default_factory=dict)

    # Monitoring
    metrics_enabled: bool = True
    health_check_interval: int = 30


# ============================================================================
# Transform Utilities
# ============================================================================


def kline_to_candle(data: dict[str, Any], _venue: str) -> Candle:
    """
    Convert Binance WebSocket kline data to Candle model.

    Args:
        data: Kline data from WebSocket message['k']
        venue: Trading venue ('spot' or 'usdm')

    Returns:
        Candle instance
    """
    return Candle(
        venue=_venue,
        symbol=data["s"],
        timeframe=TimeFrame(data["i"]),
        open_time=datetime.fromtimestamp(data["t"] / 1000, tz=UTC),
        close_time=datetime.fromtimestamp(data["T"] / 1000, tz=UTC),
        open_price=Decimal(data["o"]),
        high_price=Decimal(data["h"]),
        low_price=Decimal(data["l"]),
        close_price=Decimal(data["c"]),
        volume=Decimal(data["v"]),
        quote_volume=Decimal(data["q"]),
        trades=data["n"],
        taker_buy_base_volume=Decimal(data["V"]),
        taker_buy_quote_volume=Decimal(data["Q"]),
    )


def rest_kline_to_candle(
    data: list[Any],
    symbol: str,
    timeframe: str,
    _venue: str,
) -> Candle:
    """
    Convert Binance REST API kline array to Candle model.

    REST API returns array: [
        open_time, open, high, low, close, volume, close_time,
        quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
    ]

    Args:
        data: Kline array from REST API
        symbol: Trading pair symbol
        timeframe: Candle timeframe
        venue: Trading venue ('spot' or 'usdm')

    Returns:
        Candle instance
    """
    return Candle(
        venue=_venue,
        symbol=symbol,
        timeframe=TimeFrame(timeframe),
        open_time=datetime.fromtimestamp(data[0] / 1000, tz=UTC),
        close_time=datetime.fromtimestamp(data[6] / 1000, tz=UTC),
        open_price=Decimal(data[1]),
        high_price=Decimal(data[2]),
        low_price=Decimal(data[3]),
        close_price=Decimal(data[4]),
        volume=Decimal(data[5]),
        quote_volume=Decimal(data[7]),
        trades=int(data[8]),
        taker_buy_base_volume=Decimal(data[9]),
        taker_buy_quote_volume=Decimal(data[10]),
    )


# ============================================================================
# Export all types
# ============================================================================

__all__ = [
    "BaseEvent",
    "BinanceConfig",
    "Candle",
    "CandleOrigin",
    "CandleUpdateEvent",
    "DatabaseConfig",
    "EngineConfig",
    "ErrorEvent",
    "EventType",
    "FeatureUpdateEvent",
    "FeaturesCalculatedEvent",
    "HealthStatus",
    "MarketRegime",
    "MarketStructure",
    "NegativeVolumeError",
    "NonPositivePriceError",
    "Order",
    "OrderFilledEvent",
    "OrderPlacedEvent",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PivotPoint",
    "Position",
    "PositionSide",
    "PositionSizing",
    "PositionUpdateEvent",
    "RedisConfig",
    "RetestSignal",
    "RetestSignalEvent",
    "RiskParameters",
    "SMCSignal",
    "SMCSignalEvent",
    "SMCStructure",
    "SupplyDemandZone",
    "SystemMetrics",
    "TechnicalIndicators",
    "Ticker",
    "TimeFrame",
    "TradingDecision",
    "TradingDecisionEvent",
    "TradingMetrics",
    "ZoneType",
    "kline_to_candle",
    "rest_kline_to_candle",
]
