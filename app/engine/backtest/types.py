"""
Core types for backtesting engine.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
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
    quantity: Decimal = Decimal(0)
    price: Decimal | None = None
    stop_price: Decimal | None = None
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: Decimal = Decimal(0)
    remaining_quantity: Decimal = Decimal(0)
    reduce_only: bool = False
    order_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    fill_time: datetime | None = None

    def __post_init__(self):
        """Initialize remaining quantity."""
        if self.remaining_quantity == Decimal(0):
            self.remaining_quantity = self.quantity


@dataclass
class BacktestFill:
    """Backtesting fill representation."""

    id: UUID = field(default_factory=uuid4)
    order_id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    quantity: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    slippage: Decimal = Decimal(0)
    fill_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    fill_reason: FillReason = FillReason.MARKET
    candle_open_time: datetime | None = None
    candle_high: Decimal | None = None
    candle_low: Decimal | None = None


@dataclass
class BacktestPosition:
    """Backtesting position representation."""

    symbol: str = ""
    side: str | None = None  # "LONG" or "SHORT"
    quantity: Decimal = Decimal(0)
    entry_quantity: Decimal = Decimal(0)
    entry_price: Decimal = Decimal(0)
    mark_price: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    total_fees: Decimal = Decimal(0)
    total_funding: Decimal = Decimal(0)
    total_slippage: Decimal = Decimal(0)
    risked_amount: Decimal = Decimal(0)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    breakeven_moved: bool = False
    trail_price: Decimal | None = None
    trail_offset: Decimal | None = None
    opened_at: datetime | None = None


@dataclass
class BacktestTrade:
    """Completed trade for reporting.

    For merged/partially-exited positions this is an aggregate row: size is the
    total entered quantity, entry_price the final average, exit_price the last
    fill — so (exit-entry)*size need not equal gross_pnl.
    """

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    side: str = ""  # "long" or "short"
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    exit_time: datetime | None = None
    entry_price: Decimal = Decimal(0)
    exit_price: Decimal | None = None
    size: Decimal = Decimal(0)
    gross_pnl: Decimal | None = None
    gross_pnl_r: Decimal | None = None  # in R units
    fees: Decimal = Decimal(0)
    slippage: Decimal = Decimal(0)
    funding: Decimal = Decimal(0)
    net_pnl: Decimal | None = None
    net_pnl_r: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profits: list[dict] = field(default_factory=list)
    exit_reason: ExitReason | None = None
    duration_minutes: int | None = None
    signal_type: str | None = None
    signal_confidence: Decimal | None = None
    regime: str | None = None
    market_conditions: dict = field(default_factory=dict)


@dataclass
class BacktestConfig:
    """Backtesting configuration."""

    # Costs and execution
    fee_bps_spot: Decimal = Decimal(10)  # 0.1%
    slippage_bps: Decimal = Decimal(2)  # 0.02%
    funding_model: str = "disabled"  # or path to series

    # Session and guards
    session_enabled: bool = True
    session_exclude: list[str] = field(default_factory=list)
    news_block_before_min: int = 15
    news_block_after_min: int = 15

    # Risk and RR
    tp_ladder: list[dict] = field(
        default_factory=lambda: [
            {"r": Decimal("1.5"), "size": Decimal("0.4")},
            {"r": Decimal("2.0"), "size": Decimal("0.3")},
            {"r": Decimal("3.0"), "size": Decimal("0.3")},
        ],
    )
    move_to_breakeven_on: str = "TP1"
    trail_after: str = "TP2"

    # Strategy pipeline
    pivot_n: int = 3
    retest_max_wait_bars: int = 8
    cooldown_seconds: int = 300
    risk_per_trade: Decimal = Decimal("0.005")
    warmup_bars: int = 50

    # Strategy variant knobs (0 = disabled)
    # htf_ema_period: trend-alignment gate — veto signals against a slow EMA
    #   (long only when close > EMA, short only when close < EMA).
    # min_stop_bps: fee-aware minimum stop distance in bps of entry price;
    #   widens too-tight structure stops so notional (and thus fee/risk) drops.
    htf_ema_period: int = 0
    # htf_ema_fast: when >0 alongside htf_ema_period, require strict EMA stacking
    #   (long: close > fast EMA > slow EMA; short mirrored) — a stricter, more
    #   selective trend gate than the single-EMA version.
    htf_ema_fast: int = 0
    min_stop_bps: Decimal = Decimal(0)
    # Diagnostic only: mirror every trade around its entry (LONG<->SHORT,
    # stop/target swapped). If inverting turns a loser profitable, the signal
    # has negative directional edge, not merely zero edge.
    invert_signals: bool = False

    # WFO settings
    train_days: int = 90
    test_days: int = 30


@dataclass
class BacktestMetrics:
    """Backtesting performance metrics."""

    total_pnl: Decimal = Decimal(0)
    total_pnl_pct: Decimal = Decimal(0)
    profit_factor: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None
    max_drawdown_pct: Decimal = Decimal(0)
    max_drawdown_duration_hours: int = 0

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    hit_rate_pct: Decimal = Decimal(0)
    avg_win_r: Decimal = Decimal(0)
    avg_loss_r: Decimal = Decimal(0)
    avg_r: Decimal = Decimal(0)
    largest_win_r: Decimal = Decimal(0)
    largest_loss_r: Decimal = Decimal(0)

    # Exposure and costs
    exposure_pct: Decimal = Decimal(0)
    total_fees: Decimal = Decimal(0)
    total_slippage: Decimal = Decimal(0)
    total_funding: Decimal = Decimal(0)

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
    artifacts_path: str | None = None
    git_sha: str = ""
    config_hash: str = ""
