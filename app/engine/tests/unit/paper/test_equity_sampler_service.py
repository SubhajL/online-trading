"""Unit tests for EquitySamplerService."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.adapters.db.timescale_adapter import PaperEquityComponents
from app.engine.paper.equity_sampler_service import (
    EquitySamplerConfig,
    EquitySamplerService,
    calculate_current_equity,
)


class TestCalculateCurrentEquity:
    """Tests for pure equity calculation function."""

    def test_returns_starting_balance_when_no_activity(self) -> None:
        """Starting balance with zero components returns starting balance."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        assert result == Decimal("10000")

    def test_subtracts_fees_from_equity(self) -> None:
        """Fees reduce equity."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("50"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        assert result == Decimal("9950")

    def test_adds_positive_realized_pnl(self) -> None:
        """Positive realized PnL increases equity."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("0"),
            realized_pnl=Decimal("500"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        assert result == Decimal("10500")

    def test_subtracts_negative_realized_pnl(self) -> None:
        """Negative realized PnL decreases equity (loss)."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("0"),
            realized_pnl=Decimal("-300"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        assert result == Decimal("9700")

    def test_adds_unrealized_pnl(self) -> None:
        """Unrealized PnL affects equity."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("200"),
            total_funding=Decimal("0"),
        )
        assert result == Decimal("10200")

    def test_subtracts_funding_payments(self) -> None:
        """Funding payments (paid) reduce equity."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("100"),
        )
        assert result == Decimal("9900")

    def test_combines_all_components_correctly(self) -> None:
        """All components combine in formula: balance - fees + realized + unrealized - funding."""
        result = calculate_current_equity(
            starting_balance=Decimal("10000"),
            total_fees=Decimal("50"),
            realized_pnl=Decimal("500"),
            unrealized_pnl=Decimal("-100"),
            total_funding=Decimal("25"),
        )
        # 10000 - 50 + 500 - 100 - 25 = 10325
        assert result == Decimal("10325")


class TestEquitySamplerServiceSampleOnce:
    """Tests for _sample_once method."""

    @pytest.mark.asyncio
    async def test_inserts_computed_equity_with_timestamp(self) -> None:
        """_sample_once fetches components, computes equity, inserts with timestamp."""
        db_adapter = AsyncMock()
        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("10"),
            realized_pnl=Decimal("100"),
            unrealized_pnl=Decimal("50"),
            total_funding=Decimal("5"),
        )
        db_adapter.insert_equity_sample.return_value = True

        fixed_time = datetime(2026, 2, 4, 12, 0, tzinfo=UTC)
        config = EquitySamplerConfig(
            starting_balance=Decimal("10000"),
            poll_interval_seconds=60,
        )
        service = EquitySamplerService(
            db_adapter=db_adapter,
            config=config,
            now_fn=lambda: fixed_time,
        )

        await service._sample_once()

        # Expected: 10000 - 10 + 100 + 50 - 5 = 10135
        db_adapter.insert_equity_sample.assert_awaited_once_with(
            equity=Decimal("10135"),
            timestamp=fixed_time,
            source_timestamp=fixed_time,
        )

    @pytest.mark.asyncio
    async def test_uses_zeros_when_no_positions(self) -> None:
        """When no positions exist, components are zero and equity equals starting balance."""
        db_adapter = AsyncMock()
        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        db_adapter.insert_equity_sample.return_value = True

        fixed_time = datetime(2026, 2, 4, 12, 0, tzinfo=UTC)
        config = EquitySamplerConfig(starting_balance=Decimal("5000"))
        service = EquitySamplerService(
            db_adapter=db_adapter,
            config=config,
            now_fn=lambda: fixed_time,
        )

        await service._sample_once()

        db_adapter.insert_equity_sample.assert_awaited_once_with(
            equity=Decimal("5000"),
            timestamp=fixed_time,
            source_timestamp=fixed_time,
        )


class TestEquitySamplerServiceLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_background_task(self) -> None:
        """start() creates and runs background task."""
        db_adapter = AsyncMock()
        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        db_adapter.insert_equity_sample.return_value = True

        config = EquitySamplerConfig(
            starting_balance=Decimal("10000"),
            poll_interval_seconds=60,
        )
        service = EquitySamplerService(db_adapter=db_adapter, config=config)

        await service.start()
        assert service._running is True
        assert service._task is not None

        # Give task time to run first sample
        await asyncio.sleep(0.05)
        assert db_adapter.get_paper_equity_components.await_count >= 1

        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task_cleanly(self) -> None:
        """stop() cancels running task and waits for cleanup."""
        db_adapter = AsyncMock()
        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        db_adapter.insert_equity_sample.return_value = True

        config = EquitySamplerConfig(
            starting_balance=Decimal("10000"),
            poll_interval_seconds=60,
        )
        service = EquitySamplerService(db_adapter=db_adapter, config=config)

        await service.start()
        await service.stop()

        assert service._running is False
        assert service._task is None

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Calling start() twice does not create duplicate tasks."""
        db_adapter = AsyncMock()
        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        db_adapter.insert_equity_sample.return_value = True

        config = EquitySamplerConfig(starting_balance=Decimal("10000"))
        service = EquitySamplerService(db_adapter=db_adapter, config=config)

        await service.start()
        first_task = service._task
        await service.start()  # Second call
        second_task = service._task

        assert first_task is second_task
        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self) -> None:
        """Calling stop() twice is safe."""
        db_adapter = AsyncMock()
        config = EquitySamplerConfig(starting_balance=Decimal("10000"))
        service = EquitySamplerService(db_adapter=db_adapter, config=config)

        # Stop without ever starting
        await service.stop()
        await service.stop()  # Should not raise

        assert service._running is False


class TestEquitySamplerServiceRun:
    """Tests for _run loop behavior."""

    @pytest.mark.asyncio
    async def test_samples_immediately_then_sleeps(self) -> None:
        """_run samples immediately on start, then sleeps poll_interval."""
        db_adapter = AsyncMock()
        sample_times: list[datetime] = []

        def track_time() -> datetime:
            t = datetime.now(UTC)
            sample_times.append(t)
            return t

        db_adapter.get_paper_equity_components.return_value = PaperEquityComponents(
            total_fees=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            total_funding=Decimal("0"),
        )
        db_adapter.insert_equity_sample.return_value = True

        config = EquitySamplerConfig(
            starting_balance=Decimal("10000"),
            poll_interval_seconds=1,  # Short for testing
        )
        service = EquitySamplerService(
            db_adapter=db_adapter,
            config=config,
            now_fn=track_time,
        )

        await service.start()
        await asyncio.sleep(0.05)  # First sample should be immediate
        assert len(sample_times) >= 1

        await service.stop()
