"""
Smart Money Concepts Module

Implements Smart Money Concepts including:
- Pivot point detection (N-bar and ZigZag methods)
- Market structure tracking (HH/HL/LH/LL)
- CHOCH and BOS detection
- Fair Value Gap (FVG) identification
- Order block detection
- Zone management and expiration
"""

# Import types for easier access
from ..smc_types import (
    Pivot,
    PivotMethod,
    SMCEvent,
    SMCEventKind,
    StructureState,
    StructureTracker,
    SwingType,
    Zone,
    ZoneSide,
)
from .engine import SMCEngine
from .events import create_smc_event, create_zone_event, publish_events

from .pivots import (
    classify_pivot_relationship,
    detect_n_bar_pivots,
    detect_zigzag_pivots,
)
from .structure import detect_bos, detect_choch, get_key_levels, update_structure_state
from .zones import (
    detect_fair_value_gap,
    detect_order_block,
    expire_old_zones,
    zone_to_dict,
)

__all__ = [
    # New implementation
    "SMCEngine",
    "create_smc_event",
    "create_zone_event",
    "publish_events",
    "PivotMethod",
    "detect_n_bar_pivots",
    "detect_zigzag_pivots",
    "classify_pivot_relationship",
    "update_structure_state",
    "detect_choch",
    "detect_bos",
    "get_key_levels",
    "detect_fair_value_gap",
    "detect_order_block",
    "expire_old_zones",
    "zone_to_dict",
]
