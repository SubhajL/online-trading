"""Data structures for preflight check results."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CheckStatus(Enum):
    """Status of a preflight check."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class CheckResult:
    """Result from a single preflight check."""

    status: CheckStatus
    message: str
    details: dict[str, Any]


@dataclass(frozen=True)
class PreflightResults:
    """Aggregated results from all preflight checks."""

    checks: dict[str, CheckResult]
    overall_status: CheckStatus
    total_time_seconds: float
    can_proceed: bool
