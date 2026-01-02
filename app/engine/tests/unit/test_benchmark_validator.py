"""
Unit tests for benchmark validation runner (external vs internal matching).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.telegram_validator.benchmark_validator import validate_external_signals


class _FakeAdapter:
    def __init__(self) -> None:
        self.validations: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []

    async def get_external_telegram_signals(self, **kwargs):  # noqa: D401, ANN001
        start = kwargs["start_time"]
        end = kwargs["end_time"]
        assert start < end
        return [
            {
                "source": "captain",
                "chat_id": 1,
                "message_id": 10,
                "timestamp": kwargs["start_time"] + timedelta(minutes=1),
                "kind": "TRADE_SIGNAL",
                "strategy": "SMC_HYBRID",
                "symbol": "BTCUSDT",
                "timeframe": "30m",
                "direction": "SELL",
                "entry_price": None,
            },
        ]

    async def get_trading_decisions_in_window(self, **kwargs):  # noqa: D401, ANN001
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "timestamp": kwargs["start_time"] + timedelta(seconds=30),
                "symbol": kwargs["symbol"],
                "action": "SELL",
                "entry_price": None,
            },
        ]

    async def get_smc_signals_in_window(self, **kwargs):  # noqa: D401, ANN001
        return []

    async def get_active_zones_at_time(self, **kwargs):  # noqa: D401, ANN001
        """Return empty zones for unit test."""
        return []

    async def get_structure_events_at_time(self, **kwargs):  # noqa: D401, ANN001
        """Return empty events for unit test."""
        return []

    async def upsert_benchmark_validation_snapshot(self, **kwargs: object) -> str:  # noqa: D401
        """Store snapshot and return fake ID."""
        self.snapshots.append(kwargs)
        return "fake-snapshot-id"

    async def upsert_external_telegram_signal_validation(self, **kwargs: object) -> None:  # noqa: D401
        self.validations.append(kwargs)


@pytest.mark.asyncio
async def test_validate_external_signals_upserts_validation_rows() -> None:
    adapter = _FakeAdapter()
    start = datetime(2025, 12, 26, 8, 0, tzinfo=UTC)
    end = datetime(2025, 12, 26, 9, 0, tzinfo=UTC)

    await validate_external_signals(
        adapter,
        source="captain",
        start_time=start,
        end_time=end,
        time_window_seconds=300,
        entry_tolerance=0.002,
    )

    assert adapter.validations
    v = adapter.validations[0]
    assert v["source"] == "captain"
    assert v["chat_id"] == 1
    assert v["message_id"] == 10
    assert v["internal_kind"] == "trading_decision"
