"""
Unit tests for database manager and connection pooling.
Written first following TDD principles.
"""

import pytest
import asyncio
import asyncpg
import redis.asyncio as redis
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any
from contextlib import asynccontextmanager

from app.engine.core.database import (
    DatabaseManager,
    ConnectionPool,
    TransactionContext,
    OptimisticLockMixin,
    DatabaseConfig,
    ConnectionError,
    TransactionError,
    OptimisticLockError,
    PoolExhaustionError,
)


class TestDatabaseConfig:
    def test_database_config_creation(self):
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

    def test_database_config_validation(self):
        with pytest.raises(ValueError):
            DatabaseConfig(
                postgres_url="invalid_url", redis_url="redis://localhost:6379/0"
            )


class TestConnectionPool:
    @pytest.fixture
    def pool_config(self):
        return DatabaseConfig(
            postgres_url="postgresql://user:pass@localhost:5432/test",
            redis_url="redis://localhost:6379/1",
            pool_size=5,
            max_overflow=10,
        )

    @pytest.mark.asyncio
    async def test_connection_pool_initialization(self, pool_config):
        with (
            patch(
                "app.engine.core.database.asyncpg.create_pool", new_callable=AsyncMock
            ) as mock_postgres,
            patch("app.engine.core.database.redis.from_url") as mock_redis,
        ):

            # Mock postgres pool
            mock_postgres_pool = AsyncMock()
            mock_postgres.return_value = mock_postgres_pool

            # Mock redis connection
            mock_redis_conn = AsyncMock()
            mock_redis.return_value = mock_redis_conn

            pool = ConnectionPool(pool_config)
            await pool.initialize()

            mock_postgres.assert_called_once_with(
                pool_config.postgres_url,
                min_size=pool_config.pool_size,
                max_size=pool_config.pool_size + pool_config.max_overflow,
                command_timeout=pool_config.pool_timeout,
                server_settings={"jit": "off", "application_name": "trading_engine"},
            )
            mock_redis.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_postgres_connection_success(self, pool_config):
        with (
            patch(
                "app.engine.core.database.asyncpg.create_pool", new_callable=AsyncMock
            ) as mock_create_pool,
            patch("app.engine.core.database.redis.from_url") as mock_redis,
        ):

            # Mock postgres pool
            mock_pool = AsyncMock()
            mock_connection = AsyncMock()

            # Create proper async context manager for acquire
            async_context_manager = AsyncMock()
            async_context_manager.__aenter__ = AsyncMock(return_value=mock_connection)
            async_context_manager.__aexit__ = AsyncMock(return_value=None)
            mock_pool.acquire.return_value = async_context_manager

            mock_create_pool.return_value = mock_pool
            mock_redis.return_value = AsyncMock()

            pool = ConnectionPool(pool_config)
            await pool.initialize()

            async with pool.get_postgres_connection() as conn:
                assert conn is mock_connection

    @pytest.mark.asyncio
    async def test_get_postgres_connection_pool_exhaustion(self, pool_config):
        with (
            patch(
                "app.engine.core.database.asyncpg.create_pool", new_callable=AsyncMock
            ) as mock_create_pool,
            patch("app.engine.core.database.redis.from_url") as mock_redis,
        ):

            mock_pool = AsyncMock()
            mock_pool.acquire.side_effect = asyncpg.TooManyConnectionsError()
            mock_create_pool.return_value = mock_pool
            mock_redis.return_value = AsyncMock()

            pool = ConnectionPool(pool_config)
            await pool.initialize()

            with pytest.raises(PoolExhaustionError):
                async with pool.get_postgres_connection():
                    pass

    @pytest.mark.asyncio
    async def test_connection_health_check(self, pool_config):
        with (
            patch(
                "app.engine.core.database.asyncpg.create_pool", new_callable=AsyncMock
            ) as mock_create_pool,
            patch("app.engine.core.database.redis.from_url") as mock_redis_create,
        ):

            mock_postgres_pool = AsyncMock()
            mock_redis_pool = AsyncMock()

            mock_create_pool.return_value = mock_postgres_pool
            mock_redis_create.return_value = mock_redis_pool

            # Mock successful health checks
            mock_postgres_conn = AsyncMock()
            mock_postgres_conn.fetchval.return_value = 1

            # Create proper async context manager for postgres acquire
            async_postgres_ctx = AsyncMock()
            async_postgres_ctx.__aenter__ = AsyncMock(return_value=mock_postgres_conn)
            async_postgres_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_postgres_pool.acquire.return_value = async_postgres_ctx

            mock_redis_pool.ping.return_value = True

            pool = ConnectionPool(pool_config)
            await pool.initialize()

            health = await pool.health_check()

            assert health["postgres"] is True
            assert health["redis"] is True


class TestTransactionContext:
    @pytest.mark.asyncio
    async def test_transaction_commit_success(self):
        mock_connection = AsyncMock()

        # Create proper mock transaction
        mock_transaction = Mock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_transaction.rollback = AsyncMock()

        # Make transaction() return the mock directly (not as coroutine)
        mock_connection.transaction = Mock(return_value=mock_transaction)

        # Mock execute method
        mock_connection.execute = AsyncMock(return_value="INSERT 0 1")

        async with TransactionContext(mock_connection) as tx:
            await tx.execute("INSERT INTO test VALUES ($1)", "value")

        mock_connection.transaction.assert_called_once()
        mock_transaction.start.assert_called_once()
        mock_transaction.commit.assert_called_once()
        mock_connection.execute.assert_called_once_with(
            "INSERT INTO test VALUES ($1)", "value"
        )

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_exception(self):
        mock_connection = AsyncMock()

        # Create proper async context manager for transaction
        mock_transaction = AsyncMock()
        mock_transaction.start = AsyncMock()
        mock_transaction.commit = AsyncMock()
        mock_transaction.rollback = AsyncMock()
        mock_connection.transaction.return_value = mock_transaction

        # Mock execute method
        mock_connection.execute = AsyncMock(return_value="INSERT 0 1")

        with pytest.raises(ValueError):
            async with TransactionContext(mock_connection) as tx:
                await tx.execute("INSERT INTO test VALUES ($1)", "value")
                raise ValueError("Test error")

        # Transaction should still be entered and exited (with exception)
        mock_connection.transaction.assert_called_once()
        mock_transaction.start.assert_called_once()
        mock_transaction.rollback.assert_called_once()
        mock_connection.execute.assert_called_once_with(
            "INSERT INTO test VALUES ($1)", "value"
        )

    @pytest.mark.asyncio
    async def test_transaction_deadlock_detection(self):
        mock_connection = AsyncMock()
        mock_transaction = AsyncMock()

        # Simulate deadlock on transaction start
        deadlock_error = asyncpg.DeadlockDetectedError()
        mock_transaction.__aenter__.side_effect = deadlock_error
        mock_connection.transaction.return_value = mock_transaction

        with pytest.raises(TransactionError):
            async with TransactionContext(mock_connection):
                pass


class TestOptimisticLockMixin:
    @pytest.fixture
    def optimistic_lock_mixin(self):
        return OptimisticLockMixin()

    @pytest.mark.asyncio
    async def test_update_with_version_success(self, optimistic_lock_mixin):
        mock_connection = AsyncMock()
        mock_connection.execute.return_value = "UPDATE 1"  # One row updated

        result = await optimistic_lock_mixin.update_with_version(
            mock_connection,
            "UPDATE test SET value = $1 WHERE id = $2 AND version = $3",
            "new_value",
            123,
            1,
        )

        assert result is True
        mock_connection.execute.assert_called_once_with(
            "UPDATE test SET value = $1 WHERE id = $2 AND version = $3",
            "new_value",
            123,
            1,
        )

    @pytest.mark.asyncio
    async def test_update_with_version_conflict(self, optimistic_lock_mixin):
        mock_connection = AsyncMock()
        mock_connection.execute.return_value = "UPDATE 0"  # No rows updated

        with pytest.raises(OptimisticLockError):
            await optimistic_lock_mixin.update_with_version(
                mock_connection,
                "UPDATE test SET value = $1 WHERE id = $2 AND version = $3",
                "new_value",
                123,
                1,
            )


class TestDatabaseManager:
    @pytest.fixture
    def db_config(self):
        return DatabaseConfig(
            postgres_url="postgresql://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/1",
            pool_size=5,
            max_overflow=10,
        )

    @pytest.mark.asyncio
    async def test_database_manager_initialization(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()

            mock_pool_class.assert_called_once_with(db_config)
            mock_pool.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connection_with_retry(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()

            # Create async context managers for connections
            mock_connection = AsyncMock()
            success_ctx = AsyncMock()
            success_ctx.__aenter__ = AsyncMock(return_value=mock_connection)
            success_ctx.__aexit__ = AsyncMock(return_value=None)

            # First call fails, second succeeds
            mock_pool.get_postgres_connection.side_effect = [
                ConnectionError("Connection failed"),
                success_ctx,
            ]
            mock_pool_class.return_value = mock_pool

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()

            async with db_manager.get_connection() as conn:
                assert conn is mock_connection
            assert mock_pool.get_postgres_connection.call_count == 2

    @pytest.mark.asyncio
    async def test_transaction_context_manager(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_connection = AsyncMock()

            # Mock connection context manager
            conn_ctx = AsyncMock()
            conn_ctx.__aenter__ = AsyncMock(return_value=mock_connection)
            conn_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_pool.get_postgres_connection.return_value = conn_ctx

            # Mock transaction
            mock_tx = AsyncMock()
            mock_tx.start = AsyncMock()
            mock_tx.commit = AsyncMock()
            mock_connection.transaction.return_value = mock_tx

            mock_pool_class.return_value = mock_pool

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()

            async with db_manager.transaction() as tx:
                assert isinstance(tx, TransactionContext)

    @pytest.mark.asyncio
    async def test_concurrent_connection_handling(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool

            # Mock multiple connection context managers
            connections = []
            for i in range(10):
                mock_conn = AsyncMock()
                conn_ctx = AsyncMock()
                conn_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
                conn_ctx.__aexit__ = AsyncMock(return_value=None)
                connections.append(conn_ctx)

            mock_pool.get_postgres_connection.side_effect = connections

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()

            # Simulate concurrent requests
            async def use_connection():
                async with db_manager.get_connection() as conn:
                    return conn

            tasks = [use_connection() for _ in range(10)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 10
            assert mock_pool.get_postgres_connection.call_count == 10

    @pytest.mark.asyncio
    async def test_health_check_aggregation(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool.health_check.return_value = {"postgres": True, "redis": False}
            mock_pool_class.return_value = mock_pool

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()

            health = await db_manager.health_check()

            assert health["postgres"] is True
            assert health["redis"] is False
            assert (
                health["overall"] is False
            )  # Should be False if any component unhealthy

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, db_config):
        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool

            db_manager = DatabaseManager(db_config)
            await db_manager.initialize()
            await db_manager.shutdown()

            mock_pool.close.assert_called_once()


class TestDatabaseManagerConcurrency:
    @pytest.mark.asyncio
    async def test_connection_pooling_under_load(self):
        """Verify pool handles concurrent requests properly"""
        config = DatabaseConfig(
            postgres_url="postgresql://test:test@localhost:5432/test",
            redis_url="redis://localhost:6379/1",
            pool_size=2,  # Small pool to test contention
            max_overflow=1,
        )

        with patch("app.engine.core.database.ConnectionPool") as mock_pool_class:
            mock_pool = AsyncMock()
            mock_pool_class.return_value = mock_pool

            # Mock connection context manager
            mock_connections = [AsyncMock() for _ in range(3)]
            connection_contexts = []
            for conn in mock_connections:
                ctx = AsyncMock()
                ctx.__aenter__ = AsyncMock(return_value=conn)
                ctx.__aexit__ = AsyncMock(return_value=None)
                connection_contexts.append(ctx)

            mock_pool.get_postgres_connection.side_effect = connection_contexts

            db_manager = DatabaseManager(config)
            await db_manager.initialize()

            # Simulate high concurrency
            async def use_connection():
                async with db_manager.transaction() as tx:
                    await asyncio.sleep(0.01)  # Simulate work
                    return tx

            tasks = [use_connection() for _ in range(3)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 3
            assert mock_pool.get_postgres_connection.call_count == 3


class TestDatabaseIntegration:
    """Integration tests that would run against real database in CI/CD"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_postgres_connection(self):
        """Test against real postgres - requires test database"""
        # This would be skipped in unit tests, run only in integration
        pytest.skip("Integration test - requires test database")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_redis_connection(self):
        """Test against real redis - requires test redis"""
        pytest.skip("Integration test - requires test redis")
