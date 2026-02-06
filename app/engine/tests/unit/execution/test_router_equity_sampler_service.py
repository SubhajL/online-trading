from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.engine.execution.router_equity_sampler_service import (
    RouterEquitySamplerConfig,
    RouterEquitySamplerService,
)


@pytest.mark.asyncio
async def test_samples_once_on_start_and_inserts_equity_sample() -> None:
    router_client = AsyncMock()
    router_client.get_internal_equity.return_value = (  # type: ignore[attr-defined]
        Decimal("10000"),
        datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
    )

    db_adapter = AsyncMock()
    db_adapter.insert_equity_sample.return_value = True  # type: ignore[attr-defined]

    service = RouterEquitySamplerService(
        db_adapter=db_adapter,
        router_client=router_client,
        config=RouterEquitySamplerConfig(venue="USD_M", poll_interval_seconds=60),
    )

    await service.start()
    await service.stop()

    db_adapter.insert_equity_sample.assert_awaited_once_with(
        equity=Decimal("10000"),
        timestamp=datetime(2026, 2, 6, 12, 0, tzinfo=UTC),
    )
