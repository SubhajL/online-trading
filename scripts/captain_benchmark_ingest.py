#!/usr/bin/env python3
"""
Ingest Captain Trading Telegram channel messages (text + photos) into TimescaleDB.

Requires a Telegram *user* session (Telethon) and DB credentials.

Environment:
- TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
- CAPTAIN_TRADING_CHANNEL (channel id or @username)
- DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from typing import Any

from telethon import TelegramClient, events
from telethon.tl.types import Message

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.adapters.db.timescale_adapter import TimescaleDBAdapter  # noqa: E402
from app.engine.telegram_validator.captain_image_levels import (  # noqa: E402
    extract_trade_levels_from_image_bytes,
)
from app.engine.telegram_validator.external_telegram_persist import (  # noqa: E402
    ExternalTelegramMessageIngest,
    persist_external_telegram_ingest,
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _parse_channel_identifier(value: str) -> str | int:
    stripped = value.strip()
    if stripped.startswith("@"):
        return stripped
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    return stripped


def _message_timestamp(message: Message) -> datetime:
    ts = message.date
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


async def _download_photo_bytes(client: TelegramClient, message: Message) -> bytes | None:
    if not message.photo:
        return None
    downloaded = await client.download_media(message, file=bytes)
    if isinstance(downloaded, (bytes, bytearray)):
        return bytes(downloaded)
    return None


def _safe_message_json(message: Message) -> dict[str, Any]:
    # Keep only JSON-safe metadata; full to_dict() can be very large.
    return {
        "id": message.id,
        "date": message.date.isoformat(),
        "grouped_id": getattr(message, "grouped_id", None),
        "has_photo": bool(message.photo),
    }


async def ingest_recent_messages(*, limit: int, listen: bool) -> None:
    _load_env_file(PROJECT_ROOT / ".env.telegram")

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone = os.getenv("TELEGRAM_PHONE")
    channel_raw = os.getenv("CAPTAIN_TRADING_CHANNEL")

    if not api_id or not api_hash or not phone or not channel_raw:
        raise SystemExit(
            "Missing TELEGRAM_API_ID/TELEGRAM_API_HASH/TELEGRAM_PHONE/CAPTAIN_TRADING_CHANNEL",
        )

    db = TimescaleDBAdapter(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "trading_engine"),
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
    )
    await db.initialize()

    media_root = PROJECT_ROOT / "data" / "external_telegram_media"

    session_dir = PROJECT_ROOT / ".telegram_sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / "captain_trading_session"

    channel = _parse_channel_identifier(channel_raw)

    client = TelegramClient(str(session_path), int(api_id), api_hash)
    await client.start(phone=phone)

    entity = await client.get_entity(channel)
    source = "captain"

    async def _ingest_message(message: Message) -> None:
        text = message.message
        photo_bytes = await _download_photo_bytes(client, message)

        ocr_levels = None
        if photo_bytes is not None:
            try:
                ocr_levels = extract_trade_levels_from_image_bytes(photo_bytes)
            except Exception:
                ocr_levels = None

        ingest = ExternalTelegramMessageIngest(
            source=source,
            chat_id=entity.id,
            message_id=message.id,
            grouped_id=getattr(message, "grouped_id", None),
            timestamp=_message_timestamp(message),
            text=text,
            raw_json=_safe_message_json(message),
            photo_bytes=photo_bytes,
            ocr_levels=ocr_levels,
        )
        await persist_external_telegram_ingest(db, ingest, media_root=media_root)

    if listen:

        @client.on(events.NewMessage(chats=[entity]))
        async def _handle_new_message(event) -> None:  # noqa: ANN001
            await _ingest_message(event.message)

        print(f"Listening for new messages on {channel_raw}… (Ctrl+C to stop)")
        await client.run_until_disconnected()
        return

    count = 0
    async for message in client.iter_messages(entity, limit=limit):
        await _ingest_message(message)
        count += 1

    print(f"Ingested {count} messages into TimescaleDB.")
    await client.disconnect()
    await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--listen", action="store_true")
    args = parser.parse_args()
    asyncio.run(ingest_recent_messages(limit=args.limit, listen=args.listen))


if __name__ == "__main__":
    main()

