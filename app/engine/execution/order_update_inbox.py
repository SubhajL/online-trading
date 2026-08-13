from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TERMINAL_ORDER_STATUSES = frozenset({"FILLED", "REJECTED", "CANCELED", "CANCELLED", "EXPIRED"})


def is_terminal_transition_allowed(prior_status: str, current_status: str) -> bool:
    prior = prior_status.upper()
    current = current_status.upper()
    return prior not in TERMINAL_ORDER_STATUSES or current == prior


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
