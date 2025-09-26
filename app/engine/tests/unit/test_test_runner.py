"""Test the progressive test runner."""

from unittest.mock import MagicMock, patch
import subprocess

import pytest

from app.engine.tests.test_runner import (
    LevelResult,
    RunConfig,
    generate_summary_report,
    parse_pytest_output,
    run_progressive_tests,
    run_tests_at_level,
)


class TestParseTestOutput:
    """Test parsing pytest output."""

    def test_parse_passed_only(self):
        """Should parse output with only passed tests."""
        output = "===== 5 passed in 1.23s ====="
        passed, failed, skipped = parse_pytest_output(output)
        assert passed == 5
        assert failed == 0
        assert skipped == 0

    def test_parse_mixed_results(self):
        """Should parse output with mixed results."""
        output = "===== 3 passed, 2 failed, 1 skipped in 2.45s ====="
        passed, failed, skipped = parse_pytest_output(output)
        assert passed == 3
        assert failed == 2
        assert skipped == 1

    def test_parse_failed_only(self):
        """Should parse output with only failures."""
        output = "===== 10 failed in 0.5s ====="
        passed, failed, skipped = parse_pytest_output(output)
        assert passed == 0
        assert failed == 10
        assert skipped == 0

    def test_parse_multiline_output(self):
        """Should handle multiline output."""
        output = """
collected 5 items

test_foo.py::test_one PASSED
test_foo.py::test_two FAILED
test_bar.py::test_three PASSED

===== 2 passed, 1 failed in 0.1s =====
"""
        passed, failed, skipped = parse_pytest_output(output)
        assert passed == 2
        assert failed == 1
        assert skipped == 0


class TestRunTestsAtLevel:
    """Test running tests at a specific level."""

    @patch("subprocess.run")
    def test_run_empty_level(self, mock_run):
        """Should handle empty test list gracefully."""
        config = RunConfig()
        result = run_tests_at_level(0, [], config)

        assert result.level == 0
        assert result.passed == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.output == "No tests at this level"
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_run_single_test_success(self, mock_run):
        """Should run a single test file successfully."""
        mock_run.return_value = MagicMock(
            stdout="===== 1 passed in 0.1s =====",
            stderr="",
            returncode=0
        )

        config = RunConfig(verbose=True)
        result = run_tests_at_level(1, ["test_foo.py"], config)

        assert result.level == 1
        assert result.passed == 1
        assert result.failed == 0
        assert len(result.test_files) == 1

        # Check pytest command
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pytest" in cmd
        assert "test_foo.py" in cmd
        assert "-v" in cmd  # verbose flag

    @patch("subprocess.run")
    def test_run_with_coverage(self, mock_run):
        """Should include coverage args when enabled."""
        mock_run.return_value = MagicMock(
            stdout="===== 2 passed in 0.2s =====",
            stderr="",
            returncode=0
        )

        config = RunConfig(coverage=True)
        result = run_tests_at_level(2, ["test_a.py", "test_b.py"], config)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "--cov=app.engine" in cmd
        assert "--cov-report=term-missing" in cmd
        assert "--cov-report=html:coverage/level_2" in cmd

    @patch("subprocess.run")
    def test_run_with_parallel(self, mock_run):
        """Should include parallel args when enabled."""
        mock_run.return_value = MagicMock(
            stdout="===== 10 passed in 1.0s =====",
            stderr="",
            returncode=0
        )

        config = RunConfig(parallel=True)
        result = run_tests_at_level(3, ["test1.py", "test2.py", "test3.py"], config)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        assert "auto" in cmd

    @patch("subprocess.run")
    def test_handle_subprocess_error(self, mock_run):
        """Should handle subprocess exceptions gracefully."""
        mock_run.side_effect = Exception("Command not found")

        config = RunConfig()
        result = run_tests_at_level(1, ["test_foo.py"], config)

        assert result.failed == 1  # Mark as failed
        assert "Error running tests" in result.output
        assert "Command not found" in result.output


class TestRunProgressiveTests:
    """Test running tests progressively."""

    @patch("app.engine.tests.test_runner.categorize_existing_tests")
    @patch("app.engine.tests.test_runner.run_tests_at_level")
    def test_run_all_levels_success(self, mock_run_level, mock_categorize):
        """Should run all levels successfully."""
        mock_categorize.return_value = {
            0: ["test_import.py"],
            1: ["test_unit1.py", "test_unit2.py"],
            2: ["test_service.py"],
            3: ["test_integration.py"],
            4: []  # No E2E tests
        }

        mock_run_level.side_effect = [
            LevelResult(0, 1, 0, 0, 0.1, "OK", ["test_import.py"]),
            LevelResult(1, 2, 0, 0, 0.2, "OK", ["test_unit1.py", "test_unit2.py"]),
            LevelResult(2, 1, 0, 0, 0.3, "OK", ["test_service.py"]),
            LevelResult(3, 1, 0, 0, 0.4, "OK", ["test_integration.py"]),
        ]

        config = RunConfig(start_level=0, end_level=4)
        results = run_progressive_tests(config)

        assert len(results) == 4
        assert sum(r.passed for r in results) == 5
        assert sum(r.failed for r in results) == 0
        assert mock_run_level.call_count == 4

    @patch("app.engine.tests.test_runner.categorize_existing_tests")
    @patch("app.engine.tests.test_runner.run_tests_at_level")
    def test_stop_on_failure(self, mock_run_level, mock_categorize):
        """Should stop on first failure when configured."""
        mock_categorize.return_value = {
            0: ["test_import.py"],
            1: ["test_unit.py"],
            2: ["test_service.py"],
        }

        mock_run_level.side_effect = [
            LevelResult(0, 1, 0, 0, 0.1, "OK", ["test_import.py"]),
            LevelResult(1, 0, 1, 0, 0.2, "FAIL", ["test_unit.py"]),  # Failure
            # Level 2 should not be called
        ]

        config = RunConfig(stop_on_failure=True, end_level=2)
        results = run_progressive_tests(config)

        assert len(results) == 2  # Stopped after level 1
        assert results[1].failed == 1
        assert mock_run_level.call_count == 2  # Not 3

    @patch("app.engine.tests.test_runner.categorize_existing_tests")
    @patch("app.engine.tests.test_runner.run_tests_at_level")
    def test_continue_on_failure(self, mock_run_level, mock_categorize):
        """Should continue on failure when configured."""
        mock_categorize.return_value = {
            0: ["test_import.py"],
            1: ["test_unit.py"],
            2: ["test_service.py"],
        }

        mock_run_level.side_effect = [
            LevelResult(0, 1, 0, 0, 0.1, "OK", ["test_import.py"]),
            LevelResult(1, 0, 1, 0, 0.2, "FAIL", ["test_unit.py"]),  # Failure
            LevelResult(2, 1, 0, 0, 0.3, "OK", ["test_service.py"]),
        ]

        config = RunConfig(stop_on_failure=False, end_level=2)
        results = run_progressive_tests(config)

        assert len(results) == 3  # Continued despite failure
        assert mock_run_level.call_count == 3


class TestGenerateSummaryReport:
    """Test summary report generation."""

    def test_generate_report_all_passed(self):
        """Should generate clean report when all pass."""
        results = [
            LevelResult(0, 5, 0, 0, 1.0, "OK", ["test1.py"]),
            LevelResult(1, 10, 0, 2, 2.0, "OK", ["test2.py"]),
            LevelResult(2, 3, 0, 0, 1.5, "OK", ["test3.py"]),
        ]

        report = generate_summary_report(results)

        assert "PROGRESSIVE TEST SUMMARY" in report
        assert "Total Passed: 18" in report
        assert "Total Failed: 0" in report
        assert "Total Skipped: 2" in report
        assert "Total Duration: 4.50s" in report
        assert "✅" in report
        assert "RECOMMENDATIONS" not in report  # No failures

    def test_generate_report_with_failures(self):
        """Should include recommendations for failures."""
        results = [
            LevelResult(0, 5, 0, 0, 1.0, "OK", ["test1.py"]),
            LevelResult(1, 8, 2, 0, 2.0, "FAIL", ["test2.py"]),
        ]

        report = generate_summary_report(results)

        assert "Total Failed: 2" in report
        assert "❌" in report
        assert "RECOMMENDATIONS" in report
        assert "Level 1 had 2 failures" in report
        assert "--verbose" in report

    def test_generate_report_empty_results(self):
        """Should handle empty results."""
        report = generate_summary_report([])

        assert "Total Passed: 0" in report
        assert "Total Failed: 0" in report