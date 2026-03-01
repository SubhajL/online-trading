"""Test environment verification checks."""

import os
import socket
from unittest.mock import MagicMock, patch

import pytest

from app.engine.preflight.check_results import CheckResult, CheckStatus
from app.engine.preflight.verify_environment import (
    check_file_permissions,
    check_port_availability,
    check_required_env_vars,
)


class TestCheckRequiredEnvVars:
    """Test environment variable verification."""

    @patch.dict(os.environ, {
        "BINANCE_API_KEY": "test_api_key_long_enough",
        "BINANCE_SECRET_KEY": "test_secret_long_enough",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "TELEGRAM_BOT_TOKEN": "test_telegram_bot_token_long_enough",
        "TELEGRAM_CHAT_ID": "123456",
        "ROUTER_URL": "http://localhost:8080"
    }, clear=True)
    def test_all_required_vars_present(self):
        """Should pass when all required variables are set."""
        result = check_required_env_vars()

        assert result.status == CheckStatus.PASSED
        assert "required environment variables are set" in result.message
        assert result.details["total_checked"] > 0
        assert result.details["missing"] == []

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_required_vars(self):
        """Should fail when required variables are missing."""
        result = check_required_env_vars()

        assert result.status == CheckStatus.FAILED
        assert "Missing required environment variables" in result.message
        assert len(result.details["missing"]) > 0
        assert "BINANCE_API_KEY" in result.details["missing"]

    @patch.dict(os.environ, {
        "BINANCE_API_KEY": "",
        "POSTGRES_PORT": "not_a_number"
    }, clear=True)
    def test_invalid_env_var_values(self):
        """Should detect invalid variable values."""
        result = check_required_env_vars()

        assert result.status == CheckStatus.FAILED
        assert len(result.details["invalid"]) > 0
        assert "POSTGRES_PORT" in result.details["invalid"]

    @patch.dict(os.environ, {
        "BINANCE_API_KEY": "test_api_key_long_enough",
        "BINANCE_SECRET_KEY": "test_secret_long_enough",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "TELEGRAM_BOT_TOKEN": ""  # Optional but empty
    }, clear=True)
    def test_optional_vars_warning(self):
        """Should warn about missing optional variables."""
        result = check_required_env_vars()

        # Should be warning since optional var is empty
        assert result.status == CheckStatus.WARNING
        assert "optional" in result.details


class TestCheckPortAvailability:
    """Test port availability checks."""

    @patch("socket.socket")
    def test_ports_available(self, mock_socket_class):
        """Should pass when required ports are available."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0  # Port is open (service running)
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        result = check_port_availability()

        assert result.status == CheckStatus.PASSED
        assert "required services are running" in result.message
        assert result.details["postgres"]["status"] == "running"
        assert result.details["redis"]["status"] == "running"

    @patch("socket.socket")
    def test_ports_not_available(self, mock_socket_class):
        """Should fail when required services not running."""
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 1  # Connection refused
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        result = check_port_availability()

        assert result.status == CheckStatus.FAILED
        assert "Required services are not running" in result.message
        assert result.details["postgres"]["status"] == "not running"

    @patch("socket.socket")
    def test_mixed_port_availability(self, mock_socket_class):
        """Should handle mixed availability correctly."""
        mock_socket = MagicMock()
        # Return different values for different calls
        mock_socket.connect_ex.side_effect = [0, 1, 0, 0]  # Postgres OK, Redis not OK
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        result = check_port_availability()

        # Should fail if any required service is not running
        assert result.status == CheckStatus.FAILED


class TestCheckFilePermissions:
    """Test file permission checks."""

    @patch("os.path.exists")
    @patch("os.access")
    def test_all_permissions_ok(self, mock_access, mock_exists):
        """Should pass when all directories have correct permissions."""
        mock_exists.return_value = True
        mock_access.return_value = True

        result = check_file_permissions()

        assert result.status == CheckStatus.PASSED
        assert "File permissions are correctly set" in result.message

    @patch("os.path.exists")
    def test_missing_directories(self, mock_exists):
        """Should fail when required directories don't exist."""
        mock_exists.return_value = False

        result = check_file_permissions()

        assert result.status == CheckStatus.FAILED
        assert "missing_dirs" in result.details
        assert len(result.details["missing_dirs"]) > 0

    @patch("os.path.exists")
    @patch("os.access")
    def test_insufficient_permissions(self, mock_access, mock_exists):
        """Should fail when directories lack required permissions."""
        mock_exists.return_value = True
        mock_access.side_effect = lambda path, mode: mode != os.W_OK  # No write access

        result = check_file_permissions()

        assert result.status == CheckStatus.FAILED
        assert "permission_errors" in result.details
        assert len(result.details["permission_errors"]) > 0
