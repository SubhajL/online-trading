"""Test configuration verification checks."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.preflight.check_results import CheckResult, CheckStatus
from app.engine.preflight.verify_configuration import (
    check_database_schema,
    validate_yaml_configs,
    verify_service_connectivity,
)


class TestValidateYamlConfigs:
    """Test YAML configuration validation."""

    @patch("app.engine.preflight.verify_configuration.Path")
    @patch("yaml.safe_load")
    def test_valid_yaml_configs(self, mock_yaml_load, mock_path_class):
        """Should pass when all YAML configs are valid."""
        # Create mock path instances
        mock_config1 = MagicMock()
        mock_config1.name = "config.yaml"
        mock_config1.read_text.return_value = "key: value"
        mock_config1.__str__.return_value = "config.yaml"

        mock_config2 = MagicMock()
        mock_config2.name = "settings.yaml"
        mock_config2.read_text.return_value = "key: value"
        mock_config2.__str__.return_value = "settings.yaml"

        # Mock Path(".").glob() to return our mock files
        mock_path_instance = MagicMock()
        mock_path_instance.glob.return_value = [mock_config1, mock_config2]
        mock_path_class.return_value = mock_path_instance

        # Mock valid YAML content
        mock_yaml_load.return_value = {"key": "value"}

        result = validate_yaml_configs()

        assert result.status == CheckStatus.PASSED
        assert "All configuration files are valid" in result.message
        assert result.details["total_files"] == 2
        assert result.details["invalid_files"] == []

    @patch("app.engine.preflight.verify_configuration.Path")
    def test_no_yaml_configs(self, mock_path_class):
        """Should warn when no YAML configs found."""
        mock_path_instance = MagicMock()
        mock_path_instance.glob.return_value = []
        mock_path_instance.exists.return_value = False  # .env doesn't exist
        mock_path_class.return_value = mock_path_instance

        result = validate_yaml_configs()

        assert result.status == CheckStatus.WARNING
        assert "No configuration files found" in result.message

    @patch("app.engine.preflight.verify_configuration.Path")
    @patch("yaml.safe_load")
    def test_invalid_yaml_syntax(self, mock_yaml_load, mock_path_class):
        """Should fail on YAML syntax errors."""
        mock_bad_file = MagicMock()
        mock_bad_file.name = "bad.yaml"
        mock_bad_file.read_text.return_value = "bad: yaml: content"
        mock_bad_file.__str__.return_value = "bad.yaml"

        mock_path_instance = MagicMock()
        mock_path_instance.glob.return_value = [mock_bad_file]
        mock_path_class.return_value = mock_path_instance

        mock_yaml_load.side_effect = Exception("Invalid YAML")

        result = validate_yaml_configs()

        assert result.status == CheckStatus.FAILED
        assert len(result.details["invalid_files"]) == 1
        assert "bad.yaml" in result.details["invalid_files"][0]

    @patch("app.engine.preflight.verify_configuration.Path")
    @patch("yaml.safe_load")
    def test_missing_required_keys(self, mock_yaml_load, mock_path_class):
        """Should fail when required keys are missing."""
        mock_engine_config = MagicMock()
        mock_engine_config.name = "config.yaml"
        mock_engine_config.read_text.return_value = "some: config"
        mock_engine_config.__str__.return_value = "app/engine/config.yaml"

        mock_path_instance = MagicMock()
        mock_path_instance.glob.return_value = [mock_engine_config]
        mock_path_class.return_value = mock_path_instance

        # Missing required keys like 'engine' or 'trading'
        mock_yaml_load.return_value = {"some": "config"}

        result = validate_yaml_configs()

        # Should detect missing required keys for engine config
        assert result.status == CheckStatus.FAILED
        assert "validation_errors" in result.details


class TestCheckDatabaseSchema:
    """Test database schema verification."""

    @pytest.mark.asyncio
    @patch("asyncpg.create_pool")
    async def test_schema_exists(self, mock_create_pool):
        """Should pass when all required tables exist."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()

        # Mock successful queries
        mock_conn.fetchval.side_effect = [
            True,  # candles table exists
            True,  # is hypertable
            5,     # has indexes
        ]
        mock_conn.fetch.return_value = [
            {"table_name": "candles"},
            {"table_name": "orders"},
            {"table_name": "positions"},
        ]

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_create_pool.return_value = mock_pool

        result = await check_database_schema()

        assert result.status == CheckStatus.PASSED
        assert "Database schema is properly configured" in result.message

    @pytest.mark.asyncio
    @patch("asyncpg.create_pool")
    async def test_missing_tables(self, mock_create_pool):
        """Should fail when required tables are missing."""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()

        # Return only some tables
        mock_conn.fetch.return_value = [
            {"table_name": "candles"},
        ]

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_create_pool.return_value = mock_pool

        result = await check_database_schema()

        assert result.status == CheckStatus.FAILED
        assert "missing_tables" in result.details
        assert len(result.details["missing_tables"]) > 0

    @pytest.mark.asyncio
    @patch("asyncpg.create_pool")
    async def test_database_connection_failure(self, mock_create_pool):
        """Should fail when cannot connect to database."""
        mock_create_pool.side_effect = Exception("Connection refused")

        result = await check_database_schema()

        assert result.status == CheckStatus.FAILED
        assert "Failed to connect to database" in result.message


class TestVerifyServiceConnectivity:
    """Test service connectivity verification."""

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    @patch("aioredis.from_url")
    @patch("asyncpg.connect")
    async def test_all_services_reachable(self, mock_pg, mock_redis, mock_get):
        """Should pass when all services are reachable."""
        # Mock successful connections
        mock_pg.return_value = AsyncMock()

        mock_redis_client = AsyncMock()
        mock_redis_client.ping.return_value = True
        mock_redis.return_value = mock_redis_client

        # Mock HTTP responses
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_get.return_value.__aenter__.return_value = mock_response

        result = await verify_service_connectivity()

        assert result.status == CheckStatus.PASSED
        assert "All services are reachable" in result.message

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    @patch("aioredis.from_url")
    @patch("asyncpg.connect")
    async def test_some_services_unreachable(self, mock_pg, mock_redis, mock_get):
        """Should fail when some services cannot be reached."""
        # Database connects successfully
        mock_pg.return_value = AsyncMock()

        # Redis fails
        mock_redis.side_effect = Exception("Connection refused")

        # HTTP fails
        mock_get.side_effect = Exception("Connection timeout")

        result = await verify_service_connectivity()

        assert result.status == CheckStatus.FAILED
        assert "unreachable_services" in result.details
        assert "redis" in result.details["unreachable_services"]