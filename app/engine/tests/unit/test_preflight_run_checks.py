"""Test the preflight check orchestrator."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("yaml", reason="PyYAML is not installed")

from app.engine.preflight.check_results import CheckResult, CheckStatus, PreflightResults
from app.engine.preflight.run_checks import generate_preflight_report, run_all_checks


class TestRunAllChecks:
    """Test the main check orchestrator."""

    @patch("app.engine.preflight.run_checks.PREFLIGHT_CHECKS", [
        ("environment", lambda: CheckResult(CheckStatus.PASSED, "Env OK", {})),
        ("python_version", lambda: CheckResult(CheckStatus.PASSED, "Python OK", {})),
        ("packages", lambda: CheckResult(CheckStatus.PASSED, "Packages OK", {})),
    ])
    def test_run_all_checks_success(self):
        """Should run all checks and return success when all pass."""
        result = run_all_checks()

        assert result.overall_status == CheckStatus.PASSED
        assert result.can_proceed is True
        assert len(result.checks) >= 3
        assert "environment" in result.checks
        assert "python_version" in result.checks
        assert "packages" in result.checks

    @patch("app.engine.preflight.run_checks.PREFLIGHT_CHECKS", [
        ("environment", lambda: CheckResult(
            CheckStatus.WARNING,
            "Env has warnings",
            {"optional": ["Some optional var missing"]}
        )),
        ("python_version", lambda: CheckResult(CheckStatus.PASSED, "Python OK", {})),
    ])
    def test_run_all_checks_with_warnings(self):
        """Should allow proceeding with warnings."""
        result = run_all_checks()

        assert result.overall_status == CheckStatus.WARNING
        assert result.can_proceed is True

    @patch("app.engine.preflight.run_checks.PREFLIGHT_CHECKS", [
        ("environment", lambda: CheckResult(
            CheckStatus.FAILED,
            "Env failed",
            {"missing": ["REQUIRED_VAR"]}
        )),
        ("python_version", lambda: CheckResult(CheckStatus.PASSED, "Python OK", {})),
    ])
    def test_run_all_checks_fail_fast(self):
        """Should stop on first failure when fail_fast=True."""
        result = run_all_checks(fail_fast=True)

        assert result.overall_status == CheckStatus.FAILED
        assert result.can_proceed is False
        # Should have stopped after first check
        assert len(result.checks) == 1

    @patch("app.engine.preflight.run_checks.PREFLIGHT_CHECKS", [
        ("environment", lambda: Exception("Unexpected error")),
    ])
    def test_run_all_checks_with_exception(self):
        """Should handle check exceptions gracefully."""
        def raise_error():
            raise Exception("Unexpected error")

        with patch("app.engine.preflight.run_checks.PREFLIGHT_CHECKS", [("environment", raise_error)]):
            result = run_all_checks()

        assert result.overall_status == CheckStatus.FAILED
        assert result.can_proceed is False
        assert "environment" in result.checks
        assert "Unexpected error" in result.checks["environment"].details.get("error", "")


class TestGeneratePreflightReport:
    """Test report generation."""

    def test_generate_report_all_passed(self):
        """Should generate clean report when all checks pass."""
        results = PreflightResults(
            checks={
                "environment": CheckResult(CheckStatus.PASSED, "Env OK", {}),
                "python": CheckResult(CheckStatus.PASSED, "Python OK", {}),
            },
            overall_status=CheckStatus.PASSED,
            total_time_seconds=1.5,
            can_proceed=True
        )

        report = generate_preflight_report(results)

        assert "✅ PASSED" in report
        assert "All preflight checks passed" in report
        assert "1.50s" in report

    def test_generate_report_with_failures(self):
        """Should highlight failures in report."""
        results = PreflightResults(
            checks={
                "environment": CheckResult(
                    CheckStatus.FAILED,
                    "Missing vars",
                    {"missing": ["API_KEY", "DB_URL"]}
                ),
                "python": CheckResult(CheckStatus.PASSED, "Python OK", {}),
            },
            overall_status=CheckStatus.FAILED,
            total_time_seconds=0.5,
            can_proceed=False
        )

        report = generate_preflight_report(results)

        assert "❌ FAILED" in report
        assert "Cannot proceed" in report
        assert "Missing vars" in report
        assert "API_KEY" in report

    def test_generate_report_with_warnings(self):
        """Should show warnings in report."""
        results = PreflightResults(
            checks={
                "packages": CheckResult(
                    CheckStatus.WARNING,
                    "Version mismatches",
                    {"version_mismatches": {"pytest": {"required": "7.0", "installed": "6.0"}}}
                ),
            },
            overall_status=CheckStatus.WARNING,
            total_time_seconds=2.0,
            can_proceed=True
        )

        report = generate_preflight_report(results)

        assert "⚠️  WARNING" in report
        assert "Can proceed with warnings" in report
        assert "Version mismatches" in report