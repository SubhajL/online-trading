"""Test for preflight check result types."""

from dataclasses import fields
from typing import get_type_hints

import pytest

from app.engine.preflight.check_results import CheckResult, CheckStatus, PreflightResults


class TestCheckResult:
    """Test the CheckResult data structure."""

    def test_check_result_has_required_fields(self):
        """CheckResult should have status, message, and details fields."""
        result = CheckResult(
            status=CheckStatus.PASSED,
            message="Test passed",
            details={}
        )

        assert result.status == CheckStatus.PASSED
        assert result.message == "Test passed"
        assert result.details == {}

    def test_check_status_enum_values(self):
        """CheckStatus should have PASSED, WARNING, and FAILED values."""
        assert CheckStatus.PASSED.value == "passed"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.FAILED.value == "failed"

    def test_check_result_is_immutable(self):
        """CheckResult should be immutable (frozen dataclass)."""
        result = CheckResult(
            status=CheckStatus.PASSED,
            message="Test",
            details={}
        )

        with pytest.raises(AttributeError):
            result.status = CheckStatus.FAILED

    def test_check_result_with_detailed_errors(self):
        """CheckResult details should support error information."""
        details = {
            "missing_vars": ["BINANCE_API_KEY", "TELEGRAM_BOT_TOKEN"],
            "invalid_vars": {"DB_PORT": "not_a_number"},
            "suggestions": ["Set BINANCE_API_KEY in .env file"]
        }

        result = CheckResult(
            status=CheckStatus.FAILED,
            message="Environment variables check failed",
            details=details
        )

        assert result.details["missing_vars"] == ["BINANCE_API_KEY", "TELEGRAM_BOT_TOKEN"]
        assert result.details["invalid_vars"]["DB_PORT"] == "not_a_number"


class TestPreflightResults:
    """Test the aggregated preflight results structure."""

    def test_preflight_results_structure(self):
        """PreflightResults should aggregate multiple check results."""
        env_check = CheckResult(CheckStatus.PASSED, "Environment OK", {})
        dep_check = CheckResult(CheckStatus.WARNING, "Optional deps missing", {})

        results = PreflightResults(
            checks={
                "environment": env_check,
                "dependencies": dep_check
            },
            overall_status=CheckStatus.WARNING,
            total_time_seconds=1.5,
            can_proceed=True
        )

        assert results.checks["environment"].status == CheckStatus.PASSED
        assert results.checks["dependencies"].status == CheckStatus.WARNING
        assert results.overall_status == CheckStatus.WARNING
        assert results.can_proceed is True

    def test_preflight_results_failed_prevents_proceed(self):
        """Failed checks should prevent proceeding."""
        results = PreflightResults(
            checks={
                "critical": CheckResult(CheckStatus.FAILED, "Critical failure", {})
            },
            overall_status=CheckStatus.FAILED,
            total_time_seconds=0.1,
            can_proceed=False
        )

        assert results.overall_status == CheckStatus.FAILED
        assert results.can_proceed is False

    def test_preflight_results_check_ordering(self):
        """Checks should maintain insertion order."""
        checks = {
            "first": CheckResult(CheckStatus.PASSED, "First", {}),
            "second": CheckResult(CheckStatus.PASSED, "Second", {}),
            "third": CheckResult(CheckStatus.PASSED, "Third", {})
        }

        results = PreflightResults(
            checks=checks,
            overall_status=CheckStatus.PASSED,
            total_time_seconds=0.5,
            can_proceed=True
        )

        assert list(results.checks.keys()) == ["first", "second", "third"]