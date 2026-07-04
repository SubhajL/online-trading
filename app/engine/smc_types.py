from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer

from .models import BaseEvent, EventType, TimeFrame


class StructureState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PivotMethod(str, Enum):
    N_BAR = "N_BAR"
    ZIGZAG = "ZIGZAG"


class SMCEventKind(str, Enum):
    CHOCH = "CHOCH"
    BOS = "BOS"
    STRUCTURE_UPDATE = "STRUCTURE_UPDATE"


class SwingType(str, Enum):
    HH = "HH"  # Higher High
    HL = "HL"  # Higher Low
    LH = "LH"  # Lower High
    LL = "LL"  # Lower Low
    EH = "EH"  # Equal High
    EL = "EL"  # Equal Low


class ZoneSide(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class Pivot(BaseModel):
    timestamp: datetime
    price: Decimal
    is_high: bool
    strength: int = 1
    bar_index: int

    @field_serializer("price")
    def _ser_price(self, v: Decimal) -> str:
        return str(v)


class StructurePoint(BaseModel):
    pivot: Pivot
    swing_type: SwingType


class SMCEvent(BaseModel):
    kind: SMCEventKind
    timestamp: datetime
    price: Decimal
    from_state: StructureState
    to_state: StructureState
    trigger_pivot: Pivot
    reference_pivot: Pivot | None = None
    strength: Decimal = Field(default=Decimal("1.0"))

    @field_serializer("price", "strength")
    def _ser_decimal(self, v: Decimal) -> str:
        return str(v)


class Zone(BaseModel):
    zone_id: UUID
    symbol: str
    timeframe: TimeFrame
    zone_type: str  # FVG, OB_BULL, OB_BEAR
    side: ZoneSide
    top_price: Decimal
    bottom_price: Decimal
    created_at: datetime
    created_bar_index: int
    expiry_bars: int
    touches: int = 0
    strength: Decimal = Field(default=Decimal("1.0"))

    @field_serializer("top_price", "bottom_price", "strength")
    def _ser_zone_dec(self, v: Decimal) -> str:
        return str(v)

    @property
    def mid_price(self) -> Decimal:
        return (self.top_price + self.bottom_price) / 2


class StructureBreakEvent(BaseEvent):
    event_type: EventType = EventType.SMC_EVENT
    venue: str
    smc_event: SMCEvent
    current_state: StructureState
    key_levels: dict[str, Any]  # state, HL, LH, last_hh, last_ll


class ZoneEvent(BaseEvent):
    event_type: EventType = EventType.ZONE_UPDATE
    venue: str
    zone: Zone
    action: str  # "created", "touched", "expired"


class StructureTracker(BaseModel):
    symbol: str
    timeframe: TimeFrame
    state: StructureState = StructureState.NEUTRAL
    last_hh: Pivot | None = None
    last_hl: Pivot | None = None
    last_lh: Pivot | None = None
    last_ll: Pivot | None = None
    pivots: list[StructurePoint] = Field(default_factory=list)
    max_pivots: int = 100
    # Per-kind registration watermarks: pivots confirm half_n bars late and are
    # re-detected every candle over the rolling window, so registration accepts
    # only bar indices above the highest already accepted for each pivot kind.
    last_registered_high_bar_index: int | None = None
    last_registered_low_bar_index: int | None = None
    # Reference pivots (by bar_index) that already emitted a BOS; the same
    # broken level must not re-fire on every subsequent close beyond it.
    last_bos_bull_ref_bar_index: int | None = None
    last_bos_bear_ref_bar_index: int | None = None
