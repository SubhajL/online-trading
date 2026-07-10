"""
Restart recovery for trend_live sleeves.

Open paper positions are mapped back to their (strategy × symbol) sleeve via
the deterministic client_order_id the entry order carries
(`trend-{strategy}-{symbol}-1d-{yyyymmdd}-{action}`), so a restarted engine
resumes desired-state diffing against its real broker state instead of
re-entering.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .decision_service import OpenSleeve

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)

_EXPECTED_DATE_LENGTH = 8
_MIN_ID_PARTS = 6

_OPEN_TREND_SLEEVES_SQL = """
    SELECT DISTINCT ON (p.symbol, p.paper_session_id)
        p.symbol, p.paper_session_id, p.side, o.client_order_id
    FROM paper_positions p
    JOIN paper_orders o
      ON o.paper_session_id = p.paper_session_id
     AND o.symbol = p.symbol
    WHERE p.quantity > 0
      AND o.reduce_only = FALSE
      AND o.client_order_id LIKE 'trend-%'
    ORDER BY p.symbol, p.paper_session_id, o.order_time DESC
"""


def parse_trend_client_order_id(client_order_id: str) -> tuple[str, str] | None:
    """Extract (strategy_id, symbol) from a trend id; None for foreign ids."""
    parts = client_order_id.split("-")
    if len(parts) < _MIN_ID_PARTS or parts[0] != "trend":
        return None
    _, strategy_id, symbol, timeframe, date_token = parts[:5]
    if timeframe != "1d":
        return None
    if len(date_token) != _EXPECTED_DATE_LENGTH or not date_token.isdigit():
        return None
    return strategy_id, symbol


async def load_open_trend_sleeves(db_pool: asyncpg.Pool) -> list[OpenSleeve]:
    """Load open trend positions and map them to sleeves via the entry order id."""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(_OPEN_TREND_SLEEVES_SQL)

    sleeves: list[OpenSleeve] = []
    for row in rows:
        parsed = parse_trend_client_order_id(row["client_order_id"])
        if parsed is None:
            logger.warning(
                "Skipping open paper position with unparsable trend id %s",
                row["client_order_id"],
            )
            continue
        strategy_id, symbol = parsed
        if symbol != row["symbol"]:
            logger.warning(
                "Trend id symbol %s does not match position symbol %s; skipping",
                symbol,
                row["symbol"],
            )
            continue
        sleeves.append(
            OpenSleeve(
                strategy_id=strategy_id,
                symbol=symbol,
                bracket_id=row["paper_session_id"],
                side=row["side"],
            ),
        )
    logger.info("Recovered %d open trend sleeves", len(sleeves))
    return sleeves
