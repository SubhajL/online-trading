"""Unit tests for migration system."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from contextlib import asynccontextmanager

import pytest
from asyncpg import Connection

from app.engine.adapters.db.migrations import Migration, MigrationRunner
from app.engine.adapters.db.connection_pool import ConnectionPool


@pytest.fixture
def mock_connection() -> AsyncMock:
    """Mock database connection."""
    conn = AsyncMock(spec=Connection)
    conn.fetchval = AsyncMock()
    conn.fetch = AsyncMock()
    conn.execute = AsyncMock()

    # Mock transaction context manager
    @asynccontextmanager
    async def mock_transaction():
        yield

    # asyncpg uses `async with conn.transaction(): ...`
    conn.transaction = mock_transaction
    return conn


@pytest.fixture
def mock_pool(mock_connection: AsyncMock) -> MagicMock:
    """Mock connection pool."""
    pool = MagicMock(spec=ConnectionPool)

    @asynccontextmanager
    async def mock_acquire():
        yield mock_connection

    pool.acquire = mock_acquire
    return pool


@pytest.fixture
def migrations_dir(tmp_path) -> Path:
    """Create temporary migrations directory."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    # Create sample migration files
    (migrations / "001_initial.sql").write_text("CREATE TABLE test1 (id INT);")
    (migrations / "002_add_column.sql").write_text(
        "ALTER TABLE test1 ADD COLUMN name TEXT;"
    )
    (migrations / "000_migration_version.sql").write_text("-- Bootstrap migration")

    return migrations


class TestMigration:
    def test_from_file_valid(self, migrations_dir) -> None:
        """Test creating migration from valid file."""
        filepath = migrations_dir / "001_initial.sql"
        migration = Migration.from_file(filepath)

        assert migration.version == 1
        assert migration.name == "Initial"
        assert migration.filename == "001_initial.sql"
        assert migration.content == "CREATE TABLE test1 (id INT);"
        assert (
            migration.checksum == hashlib.sha256(migration.content.encode()).hexdigest()
        )

    def test_from_file_invalid_filename(self, migrations_dir) -> None:
        """Test creating migration from invalid filename."""
        invalid_file = migrations_dir / "invalid_name.sql"
        invalid_file.write_text("SELECT 1;")

        with pytest.raises(ValueError, match="Invalid migration filename"):
            Migration.from_file(invalid_file)

    def test_from_file_complex_name(self, migrations_dir) -> None:
        """Test migration name parsing with underscores."""
        filepath = migrations_dir / "003_add_user_table.sql"
        filepath.write_text("CREATE TABLE users (id INT);")

        migration = Migration.from_file(filepath)

        assert migration.version == 3
        assert migration.name == "Add User Table"


class TestMigrationRunner:
    @pytest.mark.asyncio
    async def test_get_current_version_no_schema(self, mock_pool, mock_connection) -> None:
        """Test getting version when migration schema doesn't exist."""
        mock_connection.fetchval.side_effect = [False, None]  # Schema doesn't exist

        runner = MigrationRunner(mock_pool, Path("/migrations"))
        version = await runner.get_current_version()

        assert version == 0
        assert mock_connection.fetchval.call_count == 1

    @pytest.mark.asyncio
    async def test_get_current_version_with_migrations(
        self, mock_pool, mock_connection
    ):
        """Test getting version with existing migrations."""
        mock_connection.fetchval.side_effect = [True, 5]  # Schema exists, version 5

        runner = MigrationRunner(mock_pool, Path("/migrations"))
        version = await runner.get_current_version()

        assert version == 5

    @pytest.mark.asyncio
    async def test_get_available_migrations(self, mock_pool, migrations_dir) -> None:
        """Test getting available migrations from filesystem."""
        runner = MigrationRunner(mock_pool, migrations_dir)
        migrations = await runner.get_available_migrations()

        assert len(migrations) == 3
        assert migrations[0].version == 0
        assert migrations[1].version == 1
        assert migrations[2].version == 2

    @pytest.mark.asyncio
    async def test_compute_plan_includes_all_versions_from_start(
        self,
        mock_pool,
        migrations_dir,
    ) -> None:
        """Plan includes all migrations >= start_version (no gap-stopping)."""
        runner = MigrationRunner(mock_pool, migrations_dir)
        migrations = await runner.get_available_migrations()

        plan = runner.compute_plan(migrations, start_version=1)
        assert [m.version for m in plan] == [1, 2]

    @pytest.mark.asyncio
    async def test_compute_plan_does_not_stop_at_gaps(
        self,
        mock_pool,
        migrations_dir,
    ) -> None:
        """Plan does not stop when there is a version gap."""
        # Create migration with gap after 2
        (migrations_dir / "004_gap_migration.sql").write_text("SELECT 1;")

        runner = MigrationRunner(mock_pool, migrations_dir)
        migrations = await runner.get_available_migrations()

        plan = runner.compute_plan(migrations, start_version=0)
        # Expect bootstrap (0), then 1, 2, 4 even though 3 is missing.
        assert [m.version for m in plan] == [0, 1, 2, 4]

    @pytest.mark.asyncio
    async def test_apply_migration_success(self, mock_pool, mock_connection) -> None:
        """Test successful migration application."""
        mock_connection.fetchval.return_value = 123  # History ID

        migration = Migration(
            version=1,
            name="Test Migration",
            filename="001_test.sql",
            content="CREATE TABLE test (id INT);",
            checksum="abc123",
        )

        runner = MigrationRunner(mock_pool, Path("/migrations"))
        await runner.apply_migration(migration, mock_connection)

        # Verify history was recorded
        assert mock_connection.fetchval.call_count == 1
        assert (
            mock_connection.execute.call_count == 3
        )  # SQL, version insert, history update

    @pytest.mark.asyncio
    async def test_apply_migration_failure(self, mock_pool, mock_connection) -> None:
        """Test migration failure handling."""
        mock_connection.fetchval.return_value = 123  # History ID
        # First execute call succeeds, second one fails
        mock_connection.execute.side_effect = [
            Exception("Migration failed"),  # Migration SQL fails immediately
            None,  # Record failure in schema_version
            None,  # Update history with failure
        ]

        migration = Migration(
            version=1,
            name="Test Migration",
            filename="001_test.sql",
            content="INVALID SQL;",
            checksum="abc123",
        )

        runner = MigrationRunner(mock_pool, Path("/migrations"))

        with pytest.raises(Exception, match="Migration failed"):
            await runner.apply_migration(migration, mock_connection)

    @pytest.mark.asyncio
    async def test_migrate_to_version_up_to_date(
        self, mock_pool, mock_connection, migrations_dir
    ):
        """Test migration when database is already up to date."""
        mock_connection.fetchval.side_effect = [
            True,  # migration_schema_exists
            True,  # get_current_version: schema exists
            2,  # get_current_version: current version
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        applied, final_version = await runner.migrate_to_version()

        assert applied == 0
        assert final_version == 2

    @pytest.mark.asyncio
    async def test_migrate_to_version_apply_all(
        self, mock_pool, mock_connection, migrations_dir
    ):
        """Test applying all pending migrations."""
        # Mock current version = 0 (no migrations)
        mock_connection.fetchval.side_effect = [
            False,  # migration_schema_exists
            False,  # get_current_version: schema exists?
            None,  # existing_status for migration 1
            111,  # history_id for migration 1
            None,  # existing_status for migration 2
            112,  # history_id for migration 2
            True,  # get_current_version: schema exists after
            2,  # get_current_version: final version
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        applied, final_version = await runner.migrate_to_version()

        assert applied == 2  # Applied migrations 1 and 2
        assert final_version == 2

    @pytest.mark.asyncio
    async def test_migrate_to_specific_version(
        self, mock_pool, mock_connection, migrations_dir
    ):
        """Test migrating to specific version."""
        mock_connection.fetchval.side_effect = [
            True,  # migration_schema_exists
            True,  # get_current_version: schema exists
            0,  # get_current_version: current version
            None,  # Check migration 1 status
            123,  # History ID for migration 1
            True,  # get_current_version: schema exists after
            1,  # get_current_version: final version
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        applied, final_version = await runner.migrate_to_version(target_version=1)

        assert applied == 1  # Only migration 1
        assert final_version == 1

    @pytest.mark.asyncio
    async def test_check_migration_status(
        self, mock_pool, mock_connection, migrations_dir
    ):
        """Test getting migration status."""
        mock_connection.fetchval.side_effect = [True, 1]  # Current version = 1

        # Mock applied migrations
        mock_connection.fetch.side_effect = [
            [
                {
                    "version": 1,
                    "name": "Initial",
                    "applied_at": "2024-01-01",
                    "execution_time_ms": 100,
                }
            ],
            [],  # No failed migrations
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        status = await runner.check_migration_status()

        assert status["current_version"] == 1
        assert status["applied_count"] == 1
        assert status["pending_count"] == 2  # Migrations 0 and 2 are pending
        assert status["failed_count"] == 0
        assert len(status["applied_migrations"]) == 1
        assert len(status["pending_migrations"]) == 2

    @pytest.mark.asyncio
    async def test_skip_already_applied_migration(
        self, mock_pool, mock_connection, migrations_dir
    ):
        """Test that already applied migrations are skipped."""
        mock_connection.fetchval.side_effect = [
            True,  # Schema exists
            0,  # Current version
            "applied",  # Migration 1 already applied
            None,  # Check migration 2 status
            124,  # History ID for migration 2
            True,  # Schema exists
            2,  # Final version
        ]

        runner = MigrationRunner(mock_pool, migrations_dir)
        applied, final_version = await runner.migrate_to_version()

        assert applied == 1  # Only migration 2 was applied
        assert final_version == 2
