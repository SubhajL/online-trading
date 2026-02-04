"""EquitySamplerService - Periodically samples paper trading equity.

This service runs as a background task that:
1. Fetches current position totals from paper_positions
2. Calculates current equity using the formula:
   equity = starting_balance - total_fees + realized_pnl + unrealized_pnl - total_funding
3. Inserts a fresh sample into equity_samples table

This keeps DecisionPublisher's risk snapshot from rejecting decisions due to stale equity.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter

logger = logging.getLogger(__name__)


def calculate_current_equity(
    starting_balance: Decimal,
    total_fees: Decimal,
    realized_pnl: Decimal,
    unrealized_pnl: Decimal,
    total_funding: Decimal,
) -> Decimal:
    """Calculate current equity from components.

    Formula: equity = starting_balance - total_fees + realized_pnl + unrealized_pnl - total_funding

    Args:
        starting_balance: Initial account balance
        total_fees: Sum of all trading fees paid
        realized_pnl: Sum of realized profit/loss from closed positions
        unrealized_pnl: Sum of unrealized profit/loss from open positions
        total_funding: Sum of funding payments (positive = paid, reduces equity)

    Returns:
        Current equity value
    """
    return starting_balance - total_fees + realized_pnl + unrealized_pnl - total_funding


@dataclass(frozen=True)
class EquitySamplerConfig:
    """Configuration for EquitySamplerService."""

    starting_balance: Decimal
    poll_interval_seconds: int = 60


class EquitySamplerService:
    """Background service that periodically samples paper trading equity.

    Follows the same lifecycle pattern as PipelineHealthService:
    - start() spawns a background task
    - stop() cancels the task cleanly
    - _run() loops: sample -> sleep -> repeat
    """

    def __init__(
        self,
        *,
        db_adapter: TimescaleDBAdapter,
        config: EquitySamplerConfig,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._db_adapter = db_adapter
        self._config = config
        self._now_fn = now_fn or (lambda: datetime.now(UTC))

        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the equity sampler background task.

        Samples immediately before returning to ensure equity is available,
        then spawns background task for periodic updates.
        """
        if self._running:
            logger.debug("EquitySamplerService already running")
            return

        self._running = True
        # Sample immediately BEFORE spawning task to avoid race with DecisionPublisher
        await self._sample_once()
        self._task = asyncio.create_task(self._run())
        logger.info("EquitySamplerService started")

    async def stop(self) -> None:
        """Stop the equity sampler and wait for cleanup."""
        if not self._running:
            return

        self._running = False
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        logger.info("EquitySamplerService stopped")

    async def _run(self) -> None:
        """Main loop: sleep then sample. First sample done in start()."""
        while self._running:
            await asyncio.sleep(self._config.poll_interval_seconds)
            if not self._running:
                break
            await self._sample_once()

    async def _sample_once(self) -> None:
        """Fetch equity components, calculate equity, and insert sample."""
        try:
            components = await self._db_adapter.get_paper_equity_components()

            equity = calculate_current_equity(
                starting_balance=self._config.starting_balance,
                total_fees=components.total_fees,
                realized_pnl=components.realized_pnl,
                unrealized_pnl=components.unrealized_pnl,
                total_funding=components.total_funding,
            )

            now = self._now_fn()
            success = await self._db_adapter.insert_equity_sample(
                equity=equity,
                timestamp=now,
            )

            if success:
                logger.debug("Inserted equity sample: %s at %s", equity, now)
            else:
                logger.warning("Failed to insert equity sample")

        except Exception:
            logger.exception("Error during equity sampling")
