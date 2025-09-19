"""
Type definitions for the trading engine.

This module contains all Pydantic models and type definitions used across
the trading platform, including events, market data, signals, and decisions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

UUID = uuid.UUID
uuid4 = uuid.uuid4
Enum = enum.Enum


# ============================================================================
# Base Types and Enums
# ============================================================================

class TimeFrame(str, Enum):
    """Supported timeframes for candle data"""
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
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type enumeration"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class OrderStatus(str, Enum):
    """Order status enumeration"""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class EventType(str, Enum):
    """Event type enumeration for the event bus"""
    CANDLE_UPDATE = "candle_update"
    FEATURES_CALCULATED = "features_calculated"
    SMC_SIGNAL = "smc_signal"
    RETEST_SIGNAL = "retest_signal"
    REGIME_UPDATE = "regime_update"
    VOLATILITY_UPDATE = "volatility_update"
    NEWS_ALERT = "news_alert"
    FUNDING_ALERT = "funding_alert"
    TRADING_DECISION = "trading_decision"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    POSITION_UPDATE = "position_update"
    HEALTH_CHECK = "health_check"
    ERROR = "error"


class MarketRegime(str, Enum):
    """Market regime classification"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    LOW_VOLATILITY = "low_volatility"


class SMCStructure(str, Enum):
    """Smart Money Concepts structure types"""
    HIGHER_HIGH = "HH"
    HIGHER_LOW = "HL"
    LOWER_HIGH = "LH"
    LOWER_LOW = "LL"
    EQUAL_HIGH = "EH"
    EQUAL_LOW = "EL"


class ZoneType(str, Enum):
    """Supply/Demand zone types"""
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
    timeframe: Optional[TimeFrame] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: str(v),
            UUID: lambda v: str(v)
        }


# ============================================================================
# Market Data Models
# ============================================================================

class Candle(BaseModel):
    """OHLCV candle data"""
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

    @validator('open_price', 'high_price', 'low_price', 'close_price',
              'volume', 'quote_volume', 'taker_buy_base_volume', 'taker_buy_quote_volume')
    def ensure_positive(cls, v):
        if v <= 0:
            raise ValueError('Price and volume values must be positive')
        return v


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


# ============================================================================
# Technical Analysis Models
# ============================================================================

class TechnicalIndicators(BaseModel):
    """Technical indicators calculated for a candle"""
    symbol: str
    timeframe: TimeFrame
    timestamp: datetime

    # Moving Averages
    ema_9: Optional[Decimal] = None
    ema_21: Optional[Decimal] = None
    ema_50: Optional[Decimal] = None
    ema_200: Optional[Decimal] = None

    # RSI
    rsi_14: Optional[Decimal] = None

    # MACD
    macd_line: Optional[Decimal] = None
    macd_signal: Optional[Decimal] = None
    macd_histogram: Optional[Decimal] = None

    # ATR
    atr_14: Optional[Decimal] = None

    # Bollinger Bands
    bb_upper: Optional[Decimal] = None
    bb_middle: Optional[Decimal] = None
    bb_lower: Optional[Decimal] = None
    bb_width: Optional[Decimal] = None
    bb_percent: Optional[Decimal] = None


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
    volume_profile: Optional[Decimal] = None


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
    tested_at: Optional[datetime] = None


class MarketStructure(BaseModel):
    """Market structure analysis"""
    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    structure_type: SMCStructure
    price: Decimal
    previous_structure: Optional[SMCStructure] = None
    trend_direction: Optional[str] = None  # "bullish", "bearish", "neutral"


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
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    confidence: Decimal = Field(ge=0, le=1)
    zone: Optional[SupplyDemandZone] = None
    reasoning: str


class RetestSignal(BaseModel):
    """Retest signal for zones and levels"""
    signal_id: UUID = Field(default_factory=uuid4)
    symbol: str
    timeframe: TimeFrame
    timestamp: datetime
    level_price: Decimal
    retest_type: str  # "support_retest", "resistance_retest", "zone_retest"
    success_probability: Decimal = Field(ge=0, le=1)
    volume_confirmation: bool
    confluence_factors: List[str] = Field(default_factory=list)


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
    allowed_symbols: List[str] = Field(default_factory=list)
    trading_hours: Optional[Dict[str, Any]] = None


class PositionSizing(BaseModel):
    """Position sizing calculation"""
    symbol: str
    entry_price: Decimal
    stop_loss: Decimal
    risk_amount: Decimal
    position_size: Decimal
    leverage: Decimal = Field(default=Decimal("1"))
    margin_required: Decimal


# ============================================================================
# Trading Decision Models
# ============================================================================

class TradingDecision(BaseModel):
    """Trading decision with full context"""
    decision_id: UUID = Field(default_factory=uuid4)
    symbol: str
    timestamp: datetime
    action: str  # "BUY", "SELL", "HOLD", "CLOSE"

    # Entry details
    entry_price: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    order_type: Optional[OrderType] = None

    # Risk management
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    position_sizing: Optional[PositionSizing] = None

    # Signal context
    signals: List[Union[SMCSignal, RetestSignal]] = Field(default_factory=list)
    technical_indicators: Optional[TechnicalIndicators] = None
    market_regime: Optional[MarketRegime] = None

    # Decision rationale
    confidence: Decimal = Field(ge=0, le=1)
    reasoning: str
    risk_reward_ratio: Optional[Decimal] = None

    # Guards and filters
    news_sentiment: Optional[str] = None
    funding_rate_impact: Optional[Decimal] = None
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
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: str = "GTC"
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Field(default=Decimal("0"))
    average_fill_price: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Associated decision
    decision_id: Optional[UUID] = None


class Position(BaseModel):
    """Position representation"""
    position_id: UUID = Field(default_factory=uuid4)
    symbol: str
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal = Field(default=Decimal("0"))
    margin_used: Decimal
    leverage: Decimal = Field(default=Decimal("1"))
    opened_at: datetime
    updated_at: datetime

    # Risk management
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None

    # Associated decision
    decision_id: Optional[UUID] = None


# ============================================================================
# Event Models
# ============================================================================

class CandleUpdateEvent(BaseEvent):
    """Candle update event"""
    event_type: EventType = EventType.CANDLE_UPDATE
    candle: Candle


class FeaturesCalculatedEvent(BaseEvent):
    """Features calculated event"""
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
    """Order placed event"""
    event_type: EventType = EventType.ORDER_PLACED
    order: Order


class OrderFilledEvent(BaseEvent):
    """Order filled event"""
    event_type: EventType = EventType.ORDER_FILLED
    order: Order
    fill_price: Decimal
    fill_quantity: Decimal
    fill_timestamp: datetime


class PositionUpdateEvent(BaseEvent):
    """Position update event"""
    event_type: EventType = EventType.POSITION_UPDATE
    position: Position


class ErrorEvent(BaseEvent):
    """Error event"""
    event_type: EventType = EventType.ERROR
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    component: str


# ============================================================================
# Health and Metrics Models
# ============================================================================

class HealthStatus(BaseModel):
    """Health status model"""
    service: str
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: datetime
    details: Dict[str, Any] = Field(default_factory=dict)
    response_time_ms: Optional[float] = None


class SystemMetrics(BaseModel):
    """System metrics"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, float]
    active_connections: int
    events_processed: int
    errors_count: int
    uptime_seconds: float


class TradingMetrics(BaseModel):
    """Trading performance metrics"""
    timestamp: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_pnl: Decimal
    max_drawdown: Decimal
    sharpe_ratio: Optional[Decimal] = None
    profit_factor: Optional[Decimal] = None
    average_win: Decimal
    average_loss: Decimal
    largest_win: Decimal
    largest_loss: Decimal


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
    password: Optional[str] = None
    database: int = 0
    max_connections: int = 10


class BinanceConfig(BaseModel):
    """Binance API configuration"""
    api_key: str
    api_secret: str
    testnet: bool = True
    base_url: Optional[str] = None
    ws_base_url: Optional[str] = None


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
    features: Dict[str, bool] = Field(default_factory=dict)

    # Monitoring
    metrics_enabled: bool = True
    health_check_interval: int = 30


# ============================================================================
# Export all types
# ============================================================================

__all__ = [
    # Enums
    "TimeFrame", "OrderSide", "OrderType", "OrderStatus", "EventType",
    "MarketRegime", "SMCStructure", "ZoneType",

    # Base types
    "BaseEvent",

    # Market data
    "Candle", "Ticker",

    # Technical analysis
    "TechnicalIndicators",

    # Smart Money Concepts
    "PivotPoint", "SupplyDemandZone", "MarketStructure",

    # Signals
    "SMCSignal", "RetestSignal",

    # Risk management
    "RiskParameters", "PositionSizing",

    # Trading
    "TradingDecision", "Order", "Position",

    # Events
    "CandleUpdateEvent", "FeaturesCalculatedEvent", "SMCSignalEvent",
    "RetestSignalEvent", "TradingDecisionEvent", "OrderPlacedEvent",
    "OrderFilledEvent", "PositionUpdateEvent", "ErrorEvent",

    # Health and metrics
    "HealthStatus", "SystemMetrics", "TradingMetrics",

    # Configuration
    "DatabaseConfig", "RedisConfig", "BinanceConfig", "EngineConfig"
]