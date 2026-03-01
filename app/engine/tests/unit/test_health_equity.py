"""Unit tests for /health/equity endpoint logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db_adapter() -> MagicMock:
    """Create mock database adapter."""
    adapter = MagicMock()
    adapter.get_latest_equity_sample = AsyncMock()
    adapter.get_paper_equity_components = AsyncMock()
    return adapter


def _make_paper_components(
    fees: Decimal = Decimal("0"),
    realized: Decimal = Decimal("0"),
    unrealized: Decimal = Decimal("0"),
    funding: Decimal = Decimal("0"),
) -> MagicMock:
    """Create mock paper equity components."""
    mock = MagicMock()
    mock.total_fees = fees
    mock.realized_pnl = realized
    mock.unrealized_pnl = unrealized
    mock.total_funding = funding
    return mock


@pytest.mark.asyncio
async def test_returns_latest_sample_and_components(
    mock_db_adapter: MagicMock,
) -> None:
    """Returns equity, timestamp, and paper components when data available."""
    from app.engine.main import services

    now = datetime.now(UTC)
    mock_db_adapter.get_latest_equity_sample.return_value = (Decimal("10000"), now)
    mock_db_adapter.get_paper_equity_components.return_value = _make_paper_components(
        fees=Decimal("50"),
        realized=Decimal("200"),
        unrealized=Decimal("-100"),
        funding=Decimal("10"),
    )

    services["database"] = mock_db_adapter

    # Import and call the endpoint function directly
    from app.engine.main import equity_health_check

    result = await equity_health_check()

    assert result.status == "healthy"
    assert result.equity == Decimal("10000")
    assert result.timestamp is not None
    assert result.age_seconds is not None
    assert result.paper_components is not None
    assert result.paper_components["total_fees"] == "50"
    assert result.paper_components["realized_pnl"] == "200"
    assert result.paper_components["unrealized_pnl"] == "-100"
    assert result.paper_components["total_funding"] == "10"


@pytest.mark.asyncio
async def test_returns_stale_status_when_sample_old(
    mock_db_adapter: MagicMock,
) -> None:
    """Age > 120s marks status stale."""
    from app.engine.main import services

    old_ts = datetime.now(UTC) - timedelta(seconds=200)
    mock_db_adapter.get_latest_equity_sample.return_value = (Decimal("10000"), old_ts)
    mock_db_adapter.get_paper_equity_components.return_value = _make_paper_components()

    services["database"] = mock_db_adapter

    from app.engine.main import equity_health_check

    result = await equity_health_check()

    assert result.status == "stale"
    assert result.age_seconds is not None
    assert result.age_seconds >= 200


@pytest.mark.asyncio
async def test_returns_missing_when_no_samples(
    mock_db_adapter: MagicMock,
) -> None:
    """No samples returns status=missing, equity=null."""
    from app.engine.main import services

    mock_db_adapter.get_latest_equity_sample.return_value = (None, None)
    mock_db_adapter.get_paper_equity_components.return_value = None

    services["database"] = mock_db_adapter

    from app.engine.main import equity_health_check

    result = await equity_health_check()

    assert result.status == "missing"
    assert result.equity is None
    assert result.timestamp is None
    assert "No equity samples" in result.message


@pytest.mark.asyncio
async def test_returns_zero_status_when_equity_zero(
    mock_db_adapter: MagicMock,
) -> None:
    """Equity=0 returns status=zero for alerting."""
    from app.engine.main import services

    now = datetime.now(UTC)
    mock_db_adapter.get_latest_equity_sample.return_value = (Decimal("0"), now)
    mock_db_adapter.get_paper_equity_components.return_value = _make_paper_components(
        fees=Decimal("10000"),
    )

    services["database"] = mock_db_adapter

    from app.engine.main import equity_health_check

    result = await equity_health_check()

    assert result.status == "zero"
    assert result.equity == Decimal("0")
    assert "Equity is zero" in result.message


@pytest.mark.asyncio
async def test_handles_database_service_missing() -> None:
    """Missing db service returns 503."""
    from fastapi import HTTPException

    from app.engine.main import services

    # Remove database from services
    if "database" in services:
        del services["database"]

    from app.engine.main import equity_health_check

    with pytest.raises(HTTPException) as exc_info:
        await equity_health_check()

    assert exc_info.value.status_code == 503
    assert "database" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_normalizes_naive_timestamp_to_utc(
    mock_db_adapter: MagicMock,
) -> None:
    """Naive timestamp treated as UTC."""
    from app.engine.main import services

    # Naive datetime (no tzinfo)
    naive_ts = datetime(2026, 2, 4, 12, 0, 0)
    mock_db_adapter.get_latest_equity_sample.return_value = (Decimal("5000"), naive_ts)
    mock_db_adapter.get_paper_equity_components.return_value = _make_paper_components()

    services["database"] = mock_db_adapter

    from app.engine.main import equity_health_check

    result = await equity_health_check()

    # Timestamp should be in ISO format
    assert result.timestamp is not None
    assert "2026-02-04T12:00:00" in result.timestamp
