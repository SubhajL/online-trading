"""Database migration management system."""

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import asyncpg
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

        with open(filepath, "r") as f:
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
    """Manages database migrations."""

    def __init__(self, pool: ConnectionPool, migrations_dir: Path):
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
                """
            )

            if not schema_exists:
                return 0

            version = await conn.fetchval(
                """
                SELECT COALESCE(MAX(version), 0)
                FROM _migration.schema_version
                WHERE status = 'applied'
                """
            )

            return version or 0

    async def get_available_migrations(self) -> List[Migration]:
        """Get all available migrations from filesystem."""
        migrations = []

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

    async def validate_migration_order(self, migrations: List[Migration]) -> None:
        """Ensure migrations are sequential with no gaps."""
        expected_version = 0

        for migration in sorted(migrations, key=lambda m: m.version):
            if migration.version != expected_version:
                raise ValueError(
                    f"Migration version gap detected: expected {expected_version}, "
                    f"found {migration.version} ({migration.filename})"
                )
            expected_version += 1

    async def apply_migration(self, migration: Migration, conn: Connection) -> None:
        """Apply a single migration within a transaction."""
        history_id = None
        start_time = time.time()

        try:
            # Record migration start
            history_id = await conn.fetchval(
                "SELECT _migration.record_migration_start($1, $2)",
                migration.version,
                "apply",
            )

            # Execute migration SQL
            await conn.execute(migration.content)

            # Record successful migration
            execution_time_ms = int((time.time() - start_time) * 1000)

            await conn.execute(
                """
                INSERT INTO _migration.schema_version
                (version, name, checksum, execution_time_ms, status)
                VALUES ($1, $2, $3, $4, 'applied')
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
                f"({execution_time_ms}ms)"
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
        self, target_version: Optional[int] = None
    ) -> Tuple[int, int]:
        """
        Apply migrations up to target version.

        Args:
            target_version: Target version to migrate to. If None, apply all.

        Returns:
            Tuple of (migrations_applied, final_version)
        """
        current_version = await self.get_current_version()
        available_migrations = await self.get_available_migrations()

        # Validate migration sequence
        await self.validate_migration_order(available_migrations)

        # Filter migrations to apply
        migrations_to_apply = [
            m
            for m in available_migrations
            if m.version > current_version
            and (target_version is None or m.version <= target_version)
        ]

        if not migrations_to_apply:
            logger.info(f"Database is up to date at version {current_version}")
            return 0, current_version

        migrations_applied = 0

        # Apply migrations in a transaction
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Ensure migration schema exists
                if current_version == 0:
                    bootstrap_migration = Migration(
                        version=0,
                        name="Bootstrap Migration Schema",
                        filename="000_migration_version.sql",
                        content=open(
                            self.migrations_dir / "000_migration_version.sql"
                        ).read(),
                        checksum="bootstrap",
                    )

                    await conn.execute(bootstrap_migration.content)
                    logger.info("Created migration tracking schema")

                # Apply each migration
                for migration in sorted(migrations_to_apply, key=lambda m: m.version):
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
                            f"Skipping already applied migration {migration.version}"
                        )
                        continue

                    await self.apply_migration(migration, conn)
                    migrations_applied += 1

        final_version = await self.get_current_version()
        logger.info(
            f"Applied {migrations_applied} migrations. "
            f"Database now at version {final_version}"
        )

        return migrations_applied, final_version

    async def check_migration_status(self) -> dict:
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
                """
            )

            # Get failed migrations
            failed_migrations = await conn.fetch(
                """
                SELECT version, name, applied_at, error_message
                FROM _migration.schema_version
                WHERE status = 'failed'
                ORDER BY version
                """
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
