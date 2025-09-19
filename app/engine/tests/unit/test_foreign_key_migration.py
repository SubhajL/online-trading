"""Test foreign key migration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from decimal import Decimal

from asyncpg import Connection

from app.engine.adapters.db.migrations import Migration, MigrationRunner
from app.engine.adapters.db.connection_pool import ConnectionPool


@pytest.fixture
def mock_connection():
    """Mock database connection."""
    conn = AsyncMock(spec=Connection)
    conn.fetchval = AsyncMock()
    conn.fetch = AsyncMock()
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_transaction():
        yield

    conn.transaction = mock_transaction
    return conn


@pytest.fixture
def mock_pool(mock_connection):
    """Mock connection pool."""
    pool = MagicMock(spec=ConnectionPool)

    @asynccontextmanager
    async def mock_acquire():
        yield mock_connection

    pool.acquire = mock_acquire
    return pool


@pytest.fixture
def migrations_dir(tmp_path):
    """Create temporary migrations directory with foreign key migration."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    # Create bootstrap migration
    (migrations / "000_migration_version.sql").write_text("-- Bootstrap migration")

    # Create some base migrations
    (migrations / "001_initial.sql").write_text("CREATE TABLE test1 (id INT);")
    (migrations / "002_add_column.sql").write_text("ALTER TABLE test1 ADD COLUMN name TEXT;")

    # Create foreign key migration
    fk_content = """
-- Add foreign key constraints
ALTER TABLE orders
ADD CONSTRAINT fk_orders_decision
FOREIGN KEY (decision_id)
REFERENCES decisions(decision_id)
ON DELETE SET NULL;

ALTER TABLE positions
ADD CONSTRAINT fk_positions_decision
FOREIGN KEY (decision_id)
REFERENCES decisions(decision_id)
ON DELETE SET NULL;
"""
    (migrations / "008_add_foreign_keys.sql").write_text(fk_content)

    return migrations


class TestForeignKeyMigration:
    @pytest.mark.asyncio
    async def test_foreign_key_migration_parsing(self, migrations_dir):
        """Test foreign key migration file is parsed correctly."""
        filepath = migrations_dir / "008_add_foreign_keys.sql"
        migration = Migration.from_file(filepath)

        assert migration.version == 8
        assert migration.name == "Add Foreign Keys"
        assert "ADD CONSTRAINT fk_orders_decision" in migration.content
        assert "ADD CONSTRAINT fk_positions_decision" in migration.content

    @pytest.mark.asyncio
    async def test_foreign_key_migration_applies(self, mock_pool, mock_connection, migrations_dir):
        """Test foreign key migration can be applied."""
        # Mock current version as 7 (before foreign keys)
        mock_connection.fetchval.side_effect = [
            True,   # Schema exists
            7,      # Current version
            None,   # Check if migration 8 is already applied
            125,    # History ID for migration 8
            True,   # Schema exists after
            8,      # Final version
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        applied, final_version = await runner.migrate_to_version()

        assert applied == 1  # Only migration 8
        assert final_version == 8

        # Verify foreign key SQL was executed
        executed_sql = None
        for call in mock_connection.execute.call_args_list:
            if call[0][0] and "ADD CONSTRAINT fk_orders_decision" in call[0][0]:
                executed_sql = call[0][0]
                break

        assert executed_sql is not None
        assert "FOREIGN KEY (decision_id)" in executed_sql
        assert "REFERENCES decisions(decision_id)" in executed_sql

    @pytest.mark.asyncio
    async def test_foreign_key_migration_rollback_on_error(self, mock_pool, mock_connection, migrations_dir):
        """Test foreign key migration rolls back on constraint violation."""
        mock_connection.fetchval.side_effect = [
            True,   # Schema exists
            7,      # Current version
            None,   # Check if migration 8 is already applied
            125,    # History ID
        ]

        # Simulate foreign key constraint violation
        mock_connection.execute.side_effect = [
            Exception("violates foreign key constraint"),
            None,  # Record failure in schema_version
            None,  # Update history with failure
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)

        with pytest.raises(Exception, match="violates foreign key constraint"):
            await runner.migrate_to_version()

        # Verify failure was recorded
        assert mock_connection.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_check_foreign_key_constraints(self, mock_pool, mock_connection, migrations_dir):
        """Test checking status after foreign key migration."""
        mock_connection.fetchval.side_effect = [True, 8]  # Schema exists, version 8

        # Mock applied migrations including foreign keys
        mock_connection.fetch.side_effect = [
            [
                {"version": 1, "name": "Initial", "applied_at": datetime.utcnow(), "execution_time_ms": 100},
                {"version": 2, "name": "Add Column", "applied_at": datetime.utcnow(), "execution_time_ms": 50},
                {"version": 8, "name": "Add Foreign Keys", "applied_at": datetime.utcnow(), "execution_time_ms": 200},
            ],
            [],  # No failed migrations
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        status = await runner.check_migration_status()

        assert status["current_version"] == 8
        assert status["applied_count"] == 3
        assert status["failed_count"] == 0

        # Find foreign key migration in applied list
        fk_migration = next(
            (m for m in status["applied_migrations"] if m["version"] == 8),
            None
        )
        assert fk_migration is not None
        assert fk_migration["name"] == "Add Foreign Keys"