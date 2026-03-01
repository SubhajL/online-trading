"""
Unit tests for persisting external Telegram messages and parsed signals.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

pytest.importorskip("pytesseract")

from app.engine.telegram_validator.captain_image_levels import TradeLevels
from app.engine.telegram_validator.external_telegram_persist import (
    ExternalTelegramMessageIngest,
    persist_external_telegram_ingest,
)


class _FakeAdapter:
    def __init__(self) -> None:
        self.message_calls: list[dict[str, object]] = []
        self.signal_calls: list[dict[str, object]] = []

    async def upsert_external_telegram_message(self, **kwargs: object) -> None:  # noqa: D401
        self.message_calls.append(kwargs)

    async def upsert_external_telegram_signal(self, **kwargs: object) -> None:  # noqa: D401
        self.signal_calls.append(kwargs)


@pytest.mark.asyncio
async def test_persist_external_telegram_ingest_writes_photo_and_upserts_tables(
    tmp_path,
) -> None:
    adapter = _FakeAdapter()

    levels = TradeLevels(
        entry=Decimal("4499.70"),
        stop_loss=Decimal("4525.87"),
        take_profits=[Decimal("4482.73"), Decimal("4430.57")],
        raw_ocr_text="Entry: 4499.70",
    )

    ingest = ExternalTelegramMessageIngest(
        source="captain",
        chat_id=2079536184,
        message_id=123,
        grouped_id=None,
        timestamp=datetime(2025, 12, 26, 8, 0, tzinfo=UTC),
        text="📈สัญญาณ : SELL\n🏅สินทรัพย์ : BTCUSD\n⏱️กรอบเวลา : M30\n🚨SMC Hybrid Signal🚨",
        raw_json={"id": 123},
        photo_bytes=b"fake-image-bytes",
        ocr_levels=levels,
    )

    await persist_external_telegram_ingest(adapter, ingest, media_root=tmp_path)

    assert adapter.message_calls
    assert adapter.signal_calls

    message = adapter.message_calls[0]
    assert message["source"] == "captain"
    assert message["chat_id"] == 2079536184
    assert message["message_id"] == 123
    assert message["has_photo"] is True
    assert isinstance(message["photo_path"], str)

    rel_path = message["photo_path"]
    assert (tmp_path / rel_path).exists()

    signal = adapter.signal_calls[0]
    assert signal["symbol"] == "BTCUSDT"
    assert signal["timeframe"] == "30m"
    assert signal["direction"] == "SELL"
    assert signal["entry_price"] == "4499.70"
    assert signal["stop_loss"] == "4525.87"
