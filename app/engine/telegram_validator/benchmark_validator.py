"""
End-to-end benchmark validation: match external Telegram signals to internal data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .benchmark_matcher import (
    ExternalSignal,
    InternalSignalCandidate,
    ValidationScore,
    score_match,
    select_best_candidate,
)
from .validation_snapshot import (
    InternalMatchSnapshot,
    build_validation_snapshot,
    serialize_snapshot_payload,
)


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _empty_score() -> ValidationScore:
    return ValidationScore(
        score=0.0,
        breakdown={
            "direction": 0.0,
            "time": 0.0,
            "entry": 0.0,
            "symbol": 0.0,
            "timeframe": 0.0,
        },
    )


async def validate_external_signals(
    adapter: Any,
    *,
    source: str,
    start_time: datetime,
    end_time: datetime,
    time_window_seconds: int,
    entry_tolerance: float,
) -> None:
    """Validate external signals vs internal candidates and persist validations."""
    tolerance = Decimal(str(entry_tolerance))
    external_rows = await adapter.get_external_telegram_signals(
        source=source,
        start_time=start_time,
        end_time=end_time,
        limit=5000,
    )

    for row in external_rows:
        if row.get("kind") != "TRADE_SIGNAL":
            continue

        external = ExternalSignal(
            source=row["source"],
            chat_id=int(row["chat_id"]),
            message_id=int(row["message_id"]),
            timestamp=row["timestamp"],
            symbol=row.get("symbol"),
            timeframe=row.get("timeframe"),
            direction=row.get("direction"),
            entry_price=_as_decimal(row.get("entry_price")),
        )

        if not external.symbol or not external.direction:
            score = _empty_score()
            await adapter.upsert_external_telegram_signal_validation(
                source=external.source,
                chat_id=external.chat_id,
                message_id=external.message_id,
                timestamp=external.timestamp,
                internal_kind=None,
                internal_id=None,
                internal_timestamp=None,
                score=score.score,
                breakdown=score.breakdown,
            )
            continue

        w0 = external.timestamp - timedelta(seconds=time_window_seconds)
        w1 = external.timestamp + timedelta(seconds=time_window_seconds)

        decision_rows = await adapter.get_trading_decisions_in_window(
            symbol=external.symbol,
            start_time=w0,
            end_time=w1,
            limit=500,
        )

        candidates: list[InternalSignalCandidate] = []
        for d in decision_rows:
            action = str(d.get("action") or "").upper()
            direction = action if action in {"BUY", "SELL"} else None
            candidates.append(
                InternalSignalCandidate(
                    kind="trading_decision",
                    id=str(d["id"]),
                    timestamp=d["timestamp"],
                    symbol=str(d["symbol"]),
                    timeframe=None,
                    direction=direction,  # type: ignore[arg-type]
                    entry_price=_as_decimal(d.get("entry_price")),
                ),
            )

        if external.timeframe:
            smc_rows = await adapter.get_smc_signals_in_window(
                symbol=external.symbol,
                timeframe=external.timeframe,
                start_time=w0,
                end_time=w1,
                limit=500,
            )
            for s in smc_rows:
                direction_raw = str(s.get("direction") or "").upper()
                direction = direction_raw if direction_raw in {"BUY", "SELL"} else None
                candidates.append(
                    InternalSignalCandidate(
                        kind="smc_signal",
                        id=str(s["id"]),
                        timestamp=s["timestamp"],
                        symbol=str(s["symbol"]),
                        timeframe=str(s.get("timeframe")) if s.get("timeframe") else None,
                        direction=direction,  # type: ignore[arg-type]
                        entry_price=_as_decimal(s.get("entry_price")),
                    ),
                )

        best = select_best_candidate(
            external,
            candidates,
            time_window_seconds=time_window_seconds,
            entry_tolerance=tolerance,
        )

        if best is None:
            score = _empty_score()
            internal_kind = None
            internal_id = None
            internal_ts = None
            internal_match = None
        else:
            score = score_match(
                external,
                best,
                time_window_seconds=time_window_seconds,
                entry_tolerance=tolerance,
            )
            internal_kind = best.kind
            internal_id = best.id
            internal_ts = best.timestamp
            # Build internal match snapshot for reproducibility
            internal_match = InternalMatchSnapshot(
                kind=best.kind,  # type: ignore[arg-type]
                internal_id=best.id,
                timestamp=best.timestamp.isoformat(),
                direction=best.direction,
                entry_price=str(best.entry_price) if best.entry_price else None,
            )

        # Build and persist validation snapshot for reproducibility
        snapshot = await build_validation_snapshot(
            adapter,
            source=external.source,
            chat_id=external.chat_id,
            message_id=external.message_id,
            symbol=external.symbol,
            timeframe=external.timeframe,
            validated_at=external.timestamp,
            internal_match=internal_match,
        )

        # Serialize and persist the snapshot
        payload = serialize_snapshot_payload(snapshot.payload)
        await adapter.upsert_benchmark_validation_snapshot(
            source=snapshot.source,
            chat_id=snapshot.chat_id,
            message_id=snapshot.message_id,
            validated_at=snapshot.validated_at,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            payload=payload,
        )

        await adapter.upsert_external_telegram_signal_validation(
            source=external.source,
            chat_id=external.chat_id,
            message_id=external.message_id,
            timestamp=external.timestamp,
            internal_kind=internal_kind,
            internal_id=internal_id,
            internal_timestamp=internal_ts,
            score=score.score,
            breakdown=score.breakdown,
        )
