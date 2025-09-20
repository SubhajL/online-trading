import os
import pytest
from unittest import mock


class TestDatabaseConfig:
    def test_pool_config_from_env(self):
        """Test database pool configuration from environment variables"""
        from app.engine.database.connection import get_pool_config

        env_vars = {
            "POSTGRES_MAX_CONNECTIONS": "50",
            "POSTGRES_MIN_CONNECTIONS": "10",
            "POSTGRES_IDLE_TIMEOUT": "60000",
            "POSTGRES_CONNECTION_TIMEOUT": "30000",
        }

        with mock.patch.dict(os.environ, env_vars):
            config = get_pool_config()

            assert config["max_size"] == 50
            assert config["min_size"] == 10
            assert config["command_timeout"] == 60.0  # milliseconds to seconds
            assert config["timeout"] == 30.0  # connection timeout

    def test_pool_config_defaults(self):
        """Test default pool configuration when env vars not set"""
        from app.engine.database.connection import get_pool_config

        with mock.patch.dict(os.environ, {}, clear=True):
            config = get_pool_config()

            assert config["max_size"] == 20
            assert config["min_size"] == 5
            assert config["command_timeout"] == 30.0  # 30 seconds default
            assert config["timeout"] == 60.0  # 60 seconds default

    def test_database_isolation(self):
        """Test that test database uses separate connection"""
        from app.engine.database.test_utils import get_test_database_url

        # Test with TEST_DATABASE_URL set
        test_url = "postgresql://test_user:test_pass@localhost:5432/test_db"
        with mock.patch.dict(os.environ, {"TEST_DATABASE_URL": test_url}):
            url = get_test_database_url()
            assert url == test_url
            assert "test" in url

        # Test fallback to modifying DATABASE_URL
        main_url = "postgresql://user:pass@localhost:5432/main_db"
        with mock.patch.dict(os.environ, {"DATABASE_URL": main_url}, clear=True):
            url = get_test_database_url()
            assert url == "postgresql://user:pass@localhost:5432/main_db_test"
            assert url != main_url

    def test_migration_timeout_handling(self):
        """Test migration timeout configuration"""
        from app.engine.database.migrations import get_migration_config

        env_vars = {
            "MIGRATION_TIMEOUT": "300000",  # 5 minutes in ms
            "MIGRATION_BATCH_SIZE": "500",
            "MIGRATION_DRY_RUN": "true",
        }

        with mock.patch.dict(os.environ, env_vars):
            config = get_migration_config()

            assert config["timeout"] == 300.0  # converted to seconds
            assert config["batch_size"] == 500
            assert config["dry_run"] is True

    def test_backup_before_migration(self):
        """Test backup creation before migration"""
        from app.engine.database.migrations import backup_before_migration

        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            # Test with backup enabled
            with mock.patch.dict(os.environ, {"MIGRATION_AUTO_BACKUP": "true"}):
                backup_file = backup_before_migration("postgresql://localhost/testdb")
                assert backup_file is not None
                assert "backup" in backup_file
                mock_run.assert_called_once()

            mock_run.reset_mock()

            # Test with backup disabled
            with mock.patch.dict(os.environ, {"MIGRATION_AUTO_BACKUP": "false"}):
                backup_file = backup_before_migration("postgresql://localhost/testdb")
                assert backup_file is None
                mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_migration_metrics_exported(self):
        """Test that migration metrics are properly exported"""
        from app.engine.database.migrations import setup_migration_metrics, record_migration_metric

        metrics = setup_migration_metrics()
        assert "migration_duration_seconds" in metrics
        assert "migration_success_total" in metrics
        assert "migration_failure_total" in metrics

        # Test recording metrics
        with mock.patch("time.time", side_effect=[100, 110]):  # 10 second migration
            record_migration_metric(metrics, "apply_migration", success=True)
            # Metrics would be exported to Prometheus here