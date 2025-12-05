"""
Idempotency utilities for trading decisions.

Provides deterministic client order ID generation for ensuring order
idempotency with exchange APIs.
"""

import re
from uuid import UUID

BINANCE_MAX_CLIENT_ORDER_ID_LENGTH = 36
PREFIX = "eng"
ID_SHORT_LENGTH = 16
MAX_SUFFIX_LENGTH = 15  # 36 - len("eng-") - 16 - len("-") = 15

# Binance allows: letters, digits, underscore, and hyphen
VALID_SUFFIX_PATTERN = re.compile(r"^[A-Za-z0-9_-]*$")


class InvalidSuffixError(ValueError):
    """Raised when suffix contains invalid characters or is too long."""


def generate_client_order_id(decision_id: UUID, suffix: str = "") -> str:
    """Generate deterministic client order ID for idempotency.

    Creates a unique, reproducible client order ID that Binance uses for
    order deduplication. The same decision_id and suffix will always
    produce the same client order ID.

    Args:
        decision_id: The unique decision UUID
        suffix: Optional suffix to distinguish different orders from same
                decision (e.g., "entry", "sl", "tp1"). Max 15 chars.
                Only alphanumeric, underscore, and hyphen allowed.

    Returns:
        Client order ID in format: eng-{decision_id_short}-{suffix}
        Maximum length: 36 characters (Binance limit)

    Raises:
        InvalidSuffixError: If suffix is too long or contains invalid chars.
    """
    if suffix:
        if len(suffix) > MAX_SUFFIX_LENGTH:
            msg = f"Suffix '{suffix}' exceeds max length {MAX_SUFFIX_LENGTH}"
            raise InvalidSuffixError(msg)
        if not VALID_SUFFIX_PATTERN.match(suffix):
            msg = f"Suffix '{suffix}' contains invalid characters"
            raise InvalidSuffixError(msg)

    id_short = str(decision_id).replace("-", "")[:ID_SHORT_LENGTH]
    return f"{PREFIX}-{id_short}-{suffix}" if suffix else f"{PREFIX}-{id_short}"
