from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TERMINAL_ORDER_STATUSES = frozenset({"FILLED", "REJECTED", "CANCELED", "CANCELLED", "EXPIRED"})


def _status(payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    value = payload.get("status")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def _decimal_value(payload: Mapping[str, Any], key: str) -> Decimal | None:
    value = payload.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _observation_time(payload: Mapping[str, Any]) -> datetime | None:
    value = payload.get("update_time")
    if isinstance(value, datetime):
        observed_at = value
    elif isinstance(value, str) and value.strip():
        try:
            observed_at = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if observed_at.tzinfo is None:
        return observed_at.replace(tzinfo=UTC)
    return observed_at.astimezone(UTC)


def is_terminal_transition_allowed(
    prior_payload: Mapping[str, Any] | None,
    current_payload: Mapping[str, Any],
) -> bool:
    prior = _status(prior_payload)
    current = _status(current_payload)
    if current is None:
        return False
    if prior_payload is None:
        return True
    if prior is None:
        return False
    if prior not in TERMINAL_ORDER_STATUSES:
        return True
    if current == prior:
        return True
    if prior not in {"CANCELED", "CANCELLED", "EXPIRED"} or current != "FILLED":
        return False

    quantity = _decimal_value(current_payload, "quantity")
    prior_executed = _decimal_value(prior_payload, "executed_qty")
    current_executed = _decimal_value(current_payload, "executed_qty")
    prior_time = _observation_time(prior_payload)
    current_time = _observation_time(current_payload)
    if (
        quantity is None
        or prior_executed is None
        or current_executed is None
        or prior_time is None
        or current_time is None
        or quantity <= 0
        or prior_executed < 0
        or current_executed < 0
    ):
        return False
    return (
        current_executed == quantity
        and current_executed > prior_executed
        and current_time >= prior_time
    )


class OrderUpdateEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    aggregate_id: str = Field(min_length=1, max_length=256)
    sequence: int = Field(ge=1)
    event_version: Literal[1]
    event_type: Literal["order_update.v1"]
    occurred_at: str
    payload: dict[str, Any]

    def payload_hash(self) -> str:
        canonical = json.dumps(
            self.payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
