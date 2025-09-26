"""Test dependency verification checks."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.engine.preflight.check_results import CheckResult, CheckStatus
from app.engine.preflight.verify_dependencies import (
    check_python_packages,
    check_python_version,
    check_system_commands,
)


class TestCheckPythonVersion:
    """Test Python version checking."""

    @patch("sys.version_info", (3, 11, 5))
    def test_python_version_sufficient(self):
        """Should pass when Python version meets requirements."""
        result = check_python_version()

        assert result.status == CheckStatus.PASSED
        assert "3.11.5" in result.message
        assert result.details["current_version"] == "3.11.5"
        assert result.details["min_version"] == "3.11"
        assert result.details["meets_requirement"] is True

    @patch("sys.version_info", (3, 9, 10))
    def test_python_version_too_old(self):
        """Should fail when Python version is too old."""
        result = check_python_version()

        assert result.status == CheckStatus.FAILED
        assert "3.9.10" in result.message
        assert "3.11" in result.message
        assert result.details["meets_requirement"] is False

    @patch("sys.version_info", (3, 13, 0))
    def test_python_version_newer(self):
        """Should pass when Python version is newer than required."""
        result = check_python_version()

        assert result.status == CheckStatus.PASSED
        assert "3.13.0" in result.message


class TestCheckPythonPackages:
    """Test Python package verification."""

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_all_packages_installed(self, mock_read_text, mock_exists):
        """Should pass when all required packages are installed."""
        mock_exists.return_value = True
        mock_read_text.return_value = "pytest==7.4.0\naiohttp==3.8.5\npandas==2.0.0"

        with patch("subprocess.run") as mock_run:
            # Mock successful pip freeze output
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pytest==7.4.0\naiohttp==3.8.5\npandas==2.0.0\nextra-package==1.0.0"
            )

            result = check_python_packages()

        assert result.status == CheckStatus.PASSED
        assert "All required packages are installed" in result.message
        assert result.details["total_required"] == 3
        assert result.details["missing_packages"] == []

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_missing_packages(self, mock_read_text, mock_exists):
        """Should fail when packages are missing."""
        mock_exists.return_value = True
        mock_read_text.return_value = "pytest==7.4.0\naiohttp==3.8.5\npandas==2.0.0"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pytest==7.4.0"  # Missing aiohttp and pandas
            )

            result = check_python_packages()

        assert result.status == CheckStatus.FAILED
        assert len(result.details["missing_packages"]) == 2
        assert "aiohttp" in result.details["missing_packages"]
        assert "pandas" in result.details["missing_packages"]

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_version_mismatches(self, mock_read_text, mock_exists):
        """Should warn when package versions don't match."""
        mock_exists.return_value = True
        mock_read_text.return_value = "pytest==7.4.0\naiohttp==3.8.5"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="pytest==6.0.0\naiohttp==3.8.5"  # Wrong pytest version
            )

            result = check_python_packages()

        assert result.status == CheckStatus.WARNING
        assert "version_mismatches" in result.details
        assert "pytest" in result.details["version_mismatches"]

    @patch("pathlib.Path.exists")
    def test_requirements_file_missing(self, mock_exists):
        """Should fail when requirements.txt doesn't exist."""
        mock_exists.return_value = False

        result = check_python_packages()

        assert result.status == CheckStatus.FAILED
        assert "requirements.txt not found" in result.message


class TestCheckSystemCommands:
    """Test system command availability."""

    @patch("shutil.which")
    def test_all_commands_available(self, mock_which):
        """Should pass when all required commands exist."""
        # Return path for all commands
        mock_which.return_value = "/usr/bin/command"

        result = check_system_commands()

        assert result.status == CheckStatus.PASSED
        assert "All required system commands are available" in result.message
        assert result.details["missing_commands"] == []

    @patch("shutil.which")
    def test_missing_commands(self, mock_which):
        """Should fail when required commands are missing."""
        # Return None for docker and psql, path for others
        def which_side_effect(cmd):
            if cmd in ["docker", "psql"]:
                return None
            return f"/usr/bin/{cmd}"

        mock_which.side_effect = which_side_effect

        result = check_system_commands()

        assert result.status == CheckStatus.FAILED
        assert len(result.details["missing_commands"]) == 2
        assert "docker" in result.details["missing_commands"]
        assert "psql" in result.details["missing_commands"]

    @patch("shutil.which")
    def test_optional_commands_missing(self, mock_which):
        """Should warn when optional commands are missing."""
        # Return None for optional command
        def which_side_effect(cmd):
            if cmd == "gh":  # GitHub CLI is optional
                return None
            return f"/usr/bin/{cmd}"

        mock_which.side_effect = which_side_effect

        result = check_system_commands()

        # Should still pass but with warnings
        if "optional_missing" in result.details and result.details["optional_missing"]:
            assert result.status == CheckStatus.WARNING
        else:
            assert result.status == CheckStatus.PASSED