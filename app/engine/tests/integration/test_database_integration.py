"""
Integration tests for database layer.
Follows T-3: Tests actual database operations.
Follows T-4: Uses real database connections instead of mocks.
"""

import pytest
import asyncio
import asyncpg
import redis.asyncio as redis
import os
from datetime import datetime
from typing import Dict, Any

from app.engine.core.database import (
    DatabaseManager,
    ConnectionPool,
    TransactionContext,
    OptimisticLockMixin,
    DatabaseConfig,
    ConnectionError,
    TransactionError,
    OptimisticLockError,
    PoolExhaustionError
)


def get_test_db_config() -> DatabaseConfig:
    """Get database config for testing."""
    return DatabaseConfig(
        postgres_url=os.getenv(
            "TEST_POSTGRES_URL",
            "postgresql://test:test@localhost:5432/test_db"
        ),
        redis_url=os.getenv(
            "TEST_REDIS_URL",
            "redis://localhost:6379/15"  # Use DB 15 for tests
        ),
        pool_size=2,  # Small pool for testing
        max_overflow=2,
        pool_timeout=5,
        retry_attempts=2
    )


@pytest.fixture
async def test_db_config():
    """Fixture for test database configuration."""
    return get_test_db_config()


@pytest.fixture
async def test_pool(test_db_config):
    """Fixture for initialized connection pool."""
    pool = ConnectionPool(test_db_config)
    await pool.initialize()
    yield pool
    await pool.close()


@pytest.fixture
async def test_db_manager(test_db_config):
    """Fixture for initialized database manager."""
    manager = DatabaseManager(test_db_config)
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
async def setup_test_table(test_pool):
    """Create test table for integration tests."""
    async with test_pool.get_postgres_connection() as conn:
        # Drop and recreate test table
        await conn.execute("DROP TABLE IF EXISTS test_table")
        await conn.execute("""
            CREATE TABLE test_table (
                id SERIAL PRIMARY KEY,
                value TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    yield
    # Cleanup
    async with test_pool.get_postgres_connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS test_table")


class TestConnectionPoolIntegration:
    """Integration tests for ConnectionPool."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pool_initialization_and_connection(self):
        """Test pool can initialize and provide connections."""
        config = get_test_db_config()
        pool = ConnectionPool(config)

        # Initialize pool
        await pool.initialize()

        # Get and use connection
        async with pool.get_postgres_connection() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

        # Get and use Redis connection
        async with pool.get_redis_connection() as redis_conn:
            await redis_conn.set("test_key", "test_value")
            value = await redis_conn.get("test_key")
            assert value == "test_value"
            await redis_conn.delete("test_key")

        # Cleanup
        await pool.close()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pool_health_check(self, test_pool):
        """Test health check reports correct status."""
        health = await test_pool.health_check()

        assert "postgres" in health
        assert "redis" in health
        assert health["postgres"] is True
        assert health["redis"] is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_pool_concurrent_connections(self, test_pool):
        """Test pool handles concurrent connections correctly."""

        async def use_connection(n: int):
            async with test_pool.get_postgres_connection() as conn:
                result = await conn.fetchval("SELECT $1::int", n)
                return result

        # Run multiple concurrent connections
        tasks = [use_connection(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert results == list(range(10))


class TestTransactionContextIntegration:
    """Integration tests for TransactionContext."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_transaction_commit(self, test_pool, setup_test_table):
        """Test transaction commits successfully."""
        async with test_pool.get_postgres_connection() as conn:
            async with TransactionContext(conn) as tx:
                await tx.execute(
                    "INSERT INTO test_table (value) VALUES ($1)",
                    "test_value"
                )

            # Verify data was committed
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM test_table WHERE value = $1",
                "test_value"
            )
            assert count == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_transaction_rollback(self, test_pool, setup_test_table):
        """Test transaction rollback on exception."""
        async with test_pool.get_postgres_connection() as conn:
            # Insert initial row
            await conn.execute(
                "INSERT INTO test_table (value) VALUES ($1)",
                "initial"
            )

            # Transaction that will fail
            with pytest.raises(ValueError):
                async with TransactionContext(conn) as tx:
                    await tx.execute(
                        "INSERT INTO test_table (value) VALUES ($1)",
                        "should_rollback"
                    )
                    raise ValueError("Intentional error")

            # Verify rollback occurred
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM test_table WHERE value = $1",
                "should_rollback"
            )
            assert count == 0

            # Initial row should still exist
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM test_table WHERE value = $1",
                "initial"
            )
            assert count == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_transaction_isolation(self, test_pool, setup_test_table):
        """Test transactions are properly isolated."""
        async with test_pool.get_postgres_connection() as conn1, \
                   test_pool.get_postgres_connection() as conn2:

            # Start transaction in conn1
            async with TransactionContext(conn1) as tx1:
                await tx1.execute(
                    "INSERT INTO test_table (value) VALUES ($1)",
                    "tx1_value"
                )

                # conn2 should not see uncommitted data
                count = await conn2.fetchval(
                    "SELECT COUNT(*) FROM test_table WHERE value = $1",
                    "tx1_value"
                )
                assert count == 0

            # After commit, conn2 should see the data
            count = await conn2.fetchval(
                "SELECT COUNT(*) FROM test_table WHERE value = $1",
                "tx1_value"
            )
            assert count == 1


class TestOptimisticLockingIntegration:
    """Integration tests for optimistic locking."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_optimistic_lock_success(self, test_pool, setup_test_table):
        """Test successful optimistic lock update."""
        mixin = OptimisticLockMixin()

        async with test_pool.get_postgres_connection() as conn:
            # Insert test row
            row_id = await conn.fetchval(
                "INSERT INTO test_table (value) VALUES ($1) RETURNING id",
                "original"
            )

            # Update with version check
            success = await mixin.update_with_version(
                conn,
                """
                UPDATE test_table
                SET value = $1, version = version + 1
                WHERE id = $2 AND version = $3
                """,
                "updated", row_id, 1
            )

            assert success is True

            # Verify update
            row = await conn.fetchrow(
                "SELECT value, version FROM test_table WHERE id = $1",
                row_id
            )
            assert row["value"] == "updated"
            assert row["version"] == 2

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_optimistic_lock_conflict(self, test_pool, setup_test_table):
        """Test optimistic lock detects concurrent modifications."""
        mixin = OptimisticLockMixin()

        async with test_pool.get_postgres_connection() as conn:
            # Insert test row
            row_id = await conn.fetchval(
                "INSERT INTO test_table (value) VALUES ($1) RETURNING id",
                "original"
            )

            # Simulate concurrent update (increment version)
            await conn.execute(
                "UPDATE test_table SET version = 2 WHERE id = $1",
                row_id
            )

            # Try to update with old version - should fail
            with pytest.raises(OptimisticLockError):
                await mixin.update_with_version(
                    conn,
                    """
                    UPDATE test_table
                    SET value = $1, version = version + 1
                    WHERE id = $2 AND version = $3
                    """,
                    "should_fail", row_id, 1  # Old version
                )


class TestDatabaseManagerIntegration:
    """Integration tests for DatabaseManager."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_manager_connection_retry(self):
        """Test manager retries failed connections."""
        # Use invalid config that will fail initially
        config = DatabaseConfig(
            postgres_url="postgresql://invalid:invalid@localhost:5432/nonexistent",
            redis_url="redis://localhost:6379/15",
            retry_attempts=1,  # Only one retry to speed up test
            retry_delay=0.01
        )

        manager = DatabaseManager(config)

        # This should fail after retries
        with pytest.raises(Exception):
            await manager.initialize()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_manager_transaction_helper(self, test_db_manager, setup_test_table):
        """Test manager's transaction helper method."""
        async with test_db_manager.transaction() as tx:
            await tx.execute(
                "INSERT INTO test_table (value) VALUES ($1)",
                "tx_test"
            )

            rows = await tx.fetch(
                "SELECT * FROM test_table WHERE value = $1",
                "tx_test"
            )
            assert len(rows) == 1
            assert rows[0]["value"] == "tx_test"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_manager_health_check(self, test_db_manager):
        """Test manager's health check aggregation."""
        health = await test_db_manager.health_check()

        assert health["postgres"] is True
        assert health["redis"] is True
        assert health["overall"] is True
        assert "timestamp" in health
        assert "pool_info" in health

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_manager_redis_operations(self, test_db_manager):
        """Test manager can perform Redis operations."""
        async with test_db_manager.redis_connection() as redis_conn:
            # Set and get
            await redis_conn.set("manager_test", "value")
            result = await redis_conn.get("manager_test")
            assert result == "value"

            # Cleanup
            await redis_conn.delete("manager_test")


class TestConcurrencyIntegration:
    """Integration tests for concurrent database operations."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_transactions(self, test_db_manager, setup_test_table):
        """Test multiple concurrent transactions work correctly."""

        async def insert_value(value: str):
            async with test_db_manager.transaction() as tx:
                await tx.execute(
                    "INSERT INTO test_table (value) VALUES ($1)",
                    value
                )
                # Small delay to increase chance of overlap
                await asyncio.sleep(0.01)
                return value

        # Run concurrent transactions
        values = [f"concurrent_{i}" for i in range(10)]
        tasks = [insert_value(v) for v in values]
        results = await asyncio.gather(*tasks)

        assert set(results) == set(values)

        # Verify all values were inserted
        async with test_db_manager.get_connection() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM test_table WHERE value LIKE 'concurrent_%'"
            )
            assert count == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_connection_pool_exhaustion(self):
        """Test pool exhaustion handling."""
        config = get_test_db_config()
        config.pool_size = 1  # Very small pool
        config.max_overflow = 0  # No overflow

        pool = ConnectionPool(config)
        await pool.initialize()

        try:
            # Hold one connection
            async with pool.get_postgres_connection() as conn1:
                # Try to get another - should fail
                with pytest.raises(PoolExhaustionError):
                    async with pool.get_postgres_connection() as conn2:
                        pass
        finally:
            await pool.close()