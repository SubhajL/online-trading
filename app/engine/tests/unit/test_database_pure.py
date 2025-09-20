"""
Unit tests for database layer pure logic.
Follows T-3: Separates pure-logic unit tests from DB-touching integration tests.
Follows T-4: Avoids heavy mocking.
"""

import pytest
from typing import Dict, Any

from app.engine.core.database import DatabaseConfig, OptimisticLockError, DatabaseError


class TestDatabaseConfig:
    """Pure logic tests for DatabaseConfig validation."""

    def test_database_config_creation(self):
        """Test config creation with valid parameters."""
        config = DatabaseConfig(
            postgres_url="postgresql://user:pass@localhost:5432/db",
            redis_url="redis://localhost:6379/0",
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            retry_attempts=3,
        )

        assert config.postgres_url == "postgresql://user:pass@localhost:5432/db"
        assert config.redis_url == "redis://localhost:6379/0"
        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.retry_attempts == 3

    def test_database_config_validation_invalid_postgres_url(self):
        """Test config validation rejects invalid PostgreSQL URL."""
        with pytest.raises(ValueError) as exc_info:
            DatabaseConfig(
                postgres_url="invalid_url", redis_url="redis://localhost:6379/0"
            )
        assert "Invalid PostgreSQL URL scheme" in str(exc_info.value)

    def test_database_config_validation_invalid_redis_url(self):
        """Test config validation rejects invalid Redis URL."""
        with pytest.raises(ValueError) as exc_info:
            DatabaseConfig(
                postgres_url="postgresql://user:pass@localhost:5432/db",
                redis_url="invalid_redis_url",
            )
        assert "Invalid Redis URL scheme" in str(exc_info.value)

    def test_database_config_validation_invalid_pool_size(self):
        """Test config validation rejects invalid pool size."""
        with pytest.raises(ValueError) as exc_info:
            DatabaseConfig(
                postgres_url="postgresql://user:pass@localhost:5432/db",
                redis_url="redis://localhost:6379/0",
                pool_size=0,
            )
        assert "pool_size must be positive" in str(exc_info.value)

    def test_database_config_validation_invalid_overflow(self):
        """Test config validation rejects negative max_overflow."""
        with pytest.raises(ValueError) as exc_info:
            DatabaseConfig(
                postgres_url="postgresql://user:pass@localhost:5432/db",
                redis_url="redis://localhost:6379/0",
                max_overflow=-1,
            )
        assert "max_overflow cannot be negative" in str(exc_info.value)

    def test_database_config_validation_invalid_timeout(self):
        """Test config validation rejects invalid pool timeout."""
        with pytest.raises(ValueError) as exc_info:
            DatabaseConfig(
                postgres_url="postgresql://user:pass@localhost:5432/db",
                redis_url="redis://localhost:6379/0",
                pool_timeout=0,
            )
        assert "pool_timeout must be positive" in str(exc_info.value)

    def test_database_config_defaults(self):
        """Test config uses sensible defaults."""
        config = DatabaseConfig(
            postgres_url="postgresql://user:pass@localhost:5432/db",
            redis_url="redis://localhost:6379/0",
        )

        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.retry_attempts == 3
        assert config.retry_delay == 0.1
        assert config.health_check_interval == 30


class TestOptimisticLockErrorHandling:
    """Pure logic tests for optimistic lock error conditions."""

    def test_optimistic_lock_error_message(self):
        """Test OptimisticLockError carries meaningful message."""
        error_msg = "Row was modified by another transaction"
        error = OptimisticLockError(error_msg)

        assert str(error) == error_msg
        assert isinstance(error, DatabaseError)

    def test_database_error_inheritance(self):
        """Test error hierarchy is correct."""
        error = OptimisticLockError("test")

        assert isinstance(error, DatabaseError)
        assert isinstance(error, Exception)
