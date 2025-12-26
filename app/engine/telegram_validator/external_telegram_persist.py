"""
Persistence helpers for external Telegram benchmarking.

Separates ingestion (Telethon / network) from pure mapping logic and DB writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .captain_image_levels import TradeLevels
from .captain_ingest import build_external_signal_fields


@dataclass(frozen=True)
class ExternalTelegramMessageIngest:
    source: str
    chat_id: int
    message_id: int
    grouped_id: int | None
    timestamp: datetime
    text: str | None
    raw_json: dict[str, Any] | None
    photo_bytes: bytes | None
    ocr_levels: TradeLevels | None


def build_external_media_relative_path(
    *,
    source: str,
    chat_id: int,
    message_id: int,
    extension: str,
) -> Path:
    filename = f"{message_id}.{extension.lstrip('.')}"
    return Path(source) / str(chat_id) / filename


async def persist_external_telegram_ingest(
    adapter: Any,
    ingest: ExternalTelegramMessageIngest,
    *,
    media_root: Path,
) -> None:
    """Persist raw message + parsed signal, optionally writing media to disk."""
    photo_path: str | None = None
    has_photo = ingest.photo_bytes is not None

    if ingest.photo_bytes is not None:
        rel_path = build_external_media_relative_path(
            source=ingest.source,
            chat_id=ingest.chat_id,
            message_id=ingest.message_id,
            extension="jpg",
        )
        abs_path = media_root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(ingest.photo_bytes)
        photo_path = rel_path.as_posix()

    await adapter.upsert_external_telegram_message(
        source=ingest.source,
        chat_id=ingest.chat_id,
        message_id=ingest.message_id,
        grouped_id=ingest.grouped_id,
        timestamp=ingest.timestamp,
        text=ingest.text,
        has_photo=has_photo,
        photo_path=photo_path,
        raw_json=ingest.raw_json,
    )

    fields = build_external_signal_fields(text=ingest.text, ocr_levels=ingest.ocr_levels)
    await adapter.upsert_external_telegram_signal(
        source=ingest.source,
        chat_id=ingest.chat_id,
        message_id=ingest.message_id,
        timestamp=ingest.timestamp,
        kind=fields["kind"],
        strategy=fields["strategy"],
        symbol=fields["symbol"],
        timeframe=fields["timeframe"],
        direction=fields["direction"],
        entry_price=fields["entry_price"],
        stop_loss=fields["stop_loss"],
        take_profits=fields["take_profits"],
        parse_confidence=fields["parse_confidence"],
        parse_sources=fields["parse_sources"],
        ocr_raw_text=fields["ocr_raw_text"],
    )
