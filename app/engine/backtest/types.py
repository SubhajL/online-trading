"""
Core types for backtesting engine.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class OrderType(Enum):
    """Order types supported by backtest engine."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderSide(Enum):
    """Order sides."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order status."""
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class FillReason(Enum):
    """Reason for order fill."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    LIQUIDATION = "liquidation"


class ExitReason(Enum):
    """Reason for trade exit."""
    TP = "tp"  # Take profit
    SL = "sl"  # Stop loss
    MANUAL = "manual"
    TIMEOUT = "timeout"


@dataclass
class BacktestOrder:
    """Backtesting order representation."""
    id: UUID = field(default_factory=uuid4)
    client_order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    type: OrderType = OrderType.MARKET
    quantity: Decimal = Decimal("0")
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal("0")
    remaining_quantity: Decimal = Decimal("0")
    reduce_only: bool = False
    order_time: datetime = field(default_factory=datetime.utcnow)
    fill_time: Optional[datetime] = None

    def __post_init__(self):
        """Initialize remaining quantity."""
        if self.remaining_quantity == Decimal("0"):
            self.remaining_quantity = self.quantity


@dataclass
class BacktestFill:
    """Backtesting fill representation."""
    id: UUID = field(default_factory=uuid4)
    order_id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    fill_time: datetime = field(default_factory=datetime.utcnow)
    fill_reason: FillReason = FillReason.MARKET
    candle_open_time: Optional[datetime] = None
    candle_high: Optional[Decimal] = None
    candle_low: Optional[Decimal] = None


@dataclass
class BacktestPosition:
    """Backtesting position representation."""
    symbol: str = ""
    side: Optional[str] = None  # "LONG" or "SHORT"
    quantity: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    mark_price: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    breakeven_moved: bool = False
    trail_price: Optional[Decimal] = None
    trail_offset: Optional[Decimal] = None
    opened_at: Optional[datetime] = None


@dataclass
class BacktestTrade:
    """Completed trade for reporting."""
    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: str = ""  # "long" or "short"
    entry_time: datetime = field(default_factory=datetime.utcnow)
    exit_time: Optional[datetime] = None
    entry_price: Decimal = Decimal("0")
    exit_price: Optional[Decimal] = None
    size: Decimal = Decimal("0")
    gross_pnl: Optional[Decimal] = None
    gross_pnl_r: Optional[Decimal] = None  # in R units
    fees: Decimal = Decimal("0")
    slippage: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")
    net_pnl: Optional[Decimal] = None
    net_pnl_r: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profits: list[dict] = field(default_factory=list)
    exit_reason: Optional[ExitReason] = None
    duration_minutes: Optional[int] = None
    signal_type: Optional[str] = None
    signal_confidence: Optional[Decimal] = None
    regime: Optional[str] = None
    market_conditions: dict = field(default_factory=dict)


@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    # Costs and execution
    fee_bps_spot: Decimal = Decimal("10")  # 0.1%
    slippage_bps: Decimal = Decimal("2")   # 0.02%
    funding_model: str = "disabled"        # or path to series

    # Session and guards
    session_enabled: bool = True
    session_exclude: list[str] = field(default_factory=list)
    news_block_before_min: int = 15
    news_block_after_min: int = 15

    # Risk and RR
    tp_ladder: list[dict] = field(default_factory=lambda: [
        {"r": Decimal("1.5"), "size": Decimal("0.4")},
        {"r": Decimal("2.0"), "size": Decimal("0.3")},
        {"r": Decimal("3.0"), "size": Decimal("0.3")}
    ])
    move_to_breakeven_on: str = "TP1"
    trail_after: str = "TP2"

    # WFO settings
    train_days: int = 90
    test_days: int = 30


@dataclass
class BacktestMetrics:
    """Backtesting performance metrics."""
    total_pnl: Decimal = Decimal("0")
    total_pnl_pct: Decimal = Decimal("0")
    profit_factor: Optional[Decimal] = None
    sharpe_ratio: Optional[Decimal] = None
    sortino_ratio: Optional[Decimal] = None
    calmar_ratio: Optional[Decimal] = None
    max_drawdown_pct: Decimal = Decimal("0")
    max_drawdown_duration_hours: int = 0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    hit_rate_pct: Decimal = Decimal("0")
    avg_win_r: Decimal = Decimal("0")
    avg_loss_r: Decimal = Decimal("0")
    avg_r: Decimal = Decimal("0")
    largest_win_r: Decimal = Decimal("0")
    largest_loss_r: Decimal = Decimal("0")

    # Exposure and costs
    exposure_pct: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    total_slippage: Decimal = Decimal("0")
    total_funding: Decimal = Decimal("0")

    # Runtime
    runtime_ms: int = 0


@dataclass
class BacktestResult:
    """Complete backtesting result."""
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    drawdown_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    artifacts_path: Optional[str] = None
    git_sha: str = ""
    config_hash: str = ""