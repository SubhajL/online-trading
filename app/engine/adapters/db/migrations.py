"""Database migration management system."""

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
import time
from typing import Any

from asyncpg import Connection

from .connection_pool import ConnectionPool

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Represents a database migration."""

    version: int
    name: str
    filename: str
    content: str
    checksum: str

    @classmethod
    def from_file(cls, filepath: Path) -> "Migration":
        """Create Migration from SQL file."""
        # Parse version and name from filename (e.g., "001_candles.sql")
        match = re.match(r"^(\d+)_(.+)\.sql$", filepath.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {filepath.name}")

        version = int(match.group(1))
        name = match.group(2).replace("_", " ").title()

        with open(filepath) as f:
            content = f.read()

        checksum = hashlib.sha256(content.encode()).hexdigest()

        return cls(
            version=version,
            name=name,
            filename=filepath.name,
            content=content,
            checksum=checksum,
        )


class MigrationRunner:
    """Manages database migrations.

    Canonical behavior:
    - Apply all available migrations in ascending version order.
    - Version gaps do not stop migration application.
    - The bootstrap migration (000_migration_version.sql) is applied once to create
      the _migration schema before applying any other migrations.
    """

    def __init__(self, pool: ConnectionPool, migrations_dir: Path) -> None:
        self.pool = pool
        self.migrations_dir = migrations_dir

    async def get_current_version(self) -> int:
        """Get the current migration version from database."""
        async with self.pool.acquire() as conn:
            # Check if migration schema exists
            schema_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.schemata
                    WHERE schema_name = '_migration'
                )
                """,
            )

            if not schema_exists:
                return 0

            version = await conn.fetchval(
                """
                SELECT COALESCE(MAX(version), 0)
                FROM _migration.schema_version
                WHERE status = 'applied'
                """,
            )

            return version or 0

    async def migration_schema_exists(self) -> bool:
        """Return True if the _migration schema exists."""
        async with self.pool.acquire() as conn:
            return bool(
                await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.schemata
                        WHERE schema_name = '_migration'
                    )
                    """,
                ),
            )

    async def get_available_migrations(self) -> list[Migration]:
        """Get all available migrations from filesystem."""
        migrations: list[Migration] = []

        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return migrations

        for filepath in sorted(self.migrations_dir.glob("*.sql")):
            try:
                migration = Migration.from_file(filepath)
                migrations.append(migration)
            except ValueError as e:
                logger.warning(f"Skipping invalid migration file: {e}")

        return migrations

    def compute_plan(
        self,
        migrations: list[Migration],
        start_version: int,
        target_version: int | None = None,
    ) -> list[Migration]:
        """Compute the migration plan to apply starting at start_version.

        Canonical behavior: apply all available migrations with version >= start_version,
        ordered by version. Gaps in version numbers do not stop migration application.

        If target_version is provided, only include migrations up to that version.
        """
        if not migrations:
            return []

        candidates = [
            m
            for m in migrations
            if m.version >= start_version
            and (target_version is None or m.version <= target_version)
        ]
        candidates.sort(key=lambda m: m.version)
        return candidates

    async def apply_migration(self, migration: Migration, conn: Connection) -> None:
        """Apply a single migration.

        Notes:
        - The migration SQL + schema_version update are executed in a per-migration
          transaction to avoid leaving the connection in an aborted transaction state
          if a migration fails.
        - Audit/history rows are recorded outside the migration transaction so failures
          are persisted even when the migration is rolled back.
        """
        history_id = None
        start_time = time.time()

        try:
            # Record migration start
            history_id = await conn.fetchval(
                "SELECT _migration.record_migration_start($1, $2)",
                migration.version,
                "apply",
            )

            execution_time_ms: int
            async with conn.transaction():
                # Execute migration SQL
                await conn.execute(migration.content)

                # Record successful migration
                execution_time_ms = int((time.time() - start_time) * 1000)
                await conn.execute(
                    """
                    INSERT INTO _migration.schema_version
                    (version, name, checksum, execution_time_ms, status)
                    VALUES ($1, $2, $3, $4, 'applied')
                    ON CONFLICT (version) DO UPDATE SET
                        name = EXCLUDED.name,
                        checksum = EXCLUDED.checksum,
                        execution_time_ms = EXCLUDED.execution_time_ms,
                        status = 'applied',
                        error_message = NULL
                    """,
                    migration.version,
                    migration.name,
                    migration.checksum,
                    execution_time_ms,
                )

            # Update history
            if history_id:
                await conn.execute(
                    "SELECT _migration.record_migration_complete($1, $2)",
                    history_id,
                    "success",
                )

            logger.info(
                f"Applied migration {migration.version}: {migration.name} "
                f"({execution_time_ms}ms)",
            )

        except Exception as e:
            # Record failure
            if history_id:
                await conn.execute(
                    "SELECT _migration.record_migration_complete($1, $2, $3)",
                    history_id,
                    "failed",
                    str(e),
                )

            # Record failed migration
            await conn.execute(
                """
                INSERT INTO _migration.schema_version
                (version, name, checksum, execution_time_ms, status, error_message)
                VALUES ($1, $2, $3, $4, 'failed', $5)
                ON CONFLICT (version) DO UPDATE SET
                    status = 'failed',
                    error_message = EXCLUDED.error_message
                """,
                migration.version,
                migration.name,
                migration.checksum,
                int((time.time() - start_time) * 1000),
                str(e),
            )

            raise

    async def migrate_to_version(
        self,
        target_version: int | None = None,
    ) -> tuple[int, int]:
        """
        Apply migrations up to target version.

        Args:
            target_version: Target version to migrate to. If None, apply all.

        Returns:
            Tuple[Any, ...] of (migrations_applied, final_version)
        """
        schema_exists = await self.migration_schema_exists()
        current_version = await self.get_current_version()
        available_migrations = await self.get_available_migrations()

        bootstrap = next((m for m in available_migrations if m.version == 0), None)
        if bootstrap is None:
            raise RuntimeError("Missing required migration 000_migration_version.sql")

        start_version = current_version + 1
        if not schema_exists:
            # Schema doesn't exist yet; bootstrap will be applied first.
            start_version = 1

        migrations_to_apply = self.compute_plan(
            available_migrations,
            start_version=start_version,
            target_version=target_version,
        )

        if not migrations_to_apply and schema_exists:
            logger.info("Database is up to date at version %s", current_version)
            return 0, current_version

        migrations_applied = 0
        async with self.pool.acquire() as conn:
            if not schema_exists:
                async with conn.transaction():
                    # Apply bootstrap first to create _migration schema/tables/functions.
                    await conn.execute(bootstrap.content)
                    await conn.execute(
                        """
                        INSERT INTO _migration.schema_version
                        (version, name, checksum, execution_time_ms, status)
                        VALUES ($1, $2, $3, $4, 'applied')
                        ON CONFLICT (version) DO NOTHING
                        """,
                        bootstrap.version,
                        bootstrap.name,
                        bootstrap.checksum,
                        0,
                    )
                logger.info("Created migration tracking schema")

            for migration in migrations_to_apply:
                # Check if migration was already partially applied
                existing_status = await conn.fetchval(
                    """
                        SELECT status FROM _migration.schema_version
                        WHERE version = $1
                        """,
                    migration.version,
                )

                if existing_status == "applied":
                    logger.info(
                        f"Skipping already applied migration {migration.version}",
                    )
                    continue

                await self.apply_migration(migration, conn)
                migrations_applied += 1

        final_version = await self.get_current_version()
        logger.info(
            f"Applied {migrations_applied} migrations. "
            f"Database now at version {final_version}",
        )

        return migrations_applied, final_version

    async def check_migration_status(self) -> dict[Any, Any]:
        """Get detailed migration status."""
        async with self.pool.acquire() as conn:
            current_version = await self.get_current_version()

            # Get applied migrations
            applied_migrations = await conn.fetch(
                """
                SELECT version, name, applied_at, execution_time_ms
                FROM _migration.schema_version
                WHERE status = 'applied'
                ORDER BY version
                """,
            )

            # Get failed migrations
            failed_migrations = await conn.fetch(
                """
                SELECT version, name, applied_at, error_message
                FROM _migration.schema_version
                WHERE status = 'failed'
                ORDER BY version
                """,
            )

            # Get pending migrations
            available_migrations = await self.get_available_migrations()
            applied_versions = {row["version"] for row in applied_migrations}
            pending_migrations = [
                m for m in available_migrations if m.version not in applied_versions
            ]

            return {
                "current_version": current_version,
                "applied_count": len(applied_migrations),
                "pending_count": len(pending_migrations),
                "failed_count": len(failed_migrations),
                "applied_migrations": [dict(row) for row in applied_migrations],
                "pending_migrations": [
                    {"version": m.version, "name": m.name, "filename": m.filename}
                    for m in pending_migrations
                ],
                "failed_migrations": [dict(row) for row in failed_migrations],
            }
