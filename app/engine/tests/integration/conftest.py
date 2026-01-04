"""Integration-test DB setup.

This suite is intended to run against a local Postgres instance specified via
`TEST_DATABASE_URL` (see `.env.example`).

Migrations are applied up to the last contiguous version, then `020_reports.sql`
is applied explicitly to ensure paper trading tables exist.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

import asyncpg
import pytest
import pytest_asyncio

from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.adapters.db.migrations import MigrationRunner
from app.engine.tests.integration.db_config import (
    TestDatabaseConfig,
    load_test_database_config,
)

SKIP_MIGRATION_VERSIONS = {8}
REPORTS_MIGRATION_VERSION = 20

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


def _migration_version_from_name(name: str) -> int | None:
    try:
        return int(name.split("_", maxsplit=1)[0])
    except (IndexError, ValueError):
        return None


def _load_migration_files(migrations_dir: Path) -> dict[int, Path]:
    files: dict[int, Path] = {}
    for path in migrations_dir.glob("*.sql"):
        version = _migration_version_from_name(path.name)
        if version is None:
            continue
        files[version] = path
    return files


def _last_contiguous_version(versions: set[int]) -> int:
    last = -1
    while (last + 1) in versions:
        last += 1
    return last


def _prepare_contiguous_migrations_dir(
    *,
    files: dict[int, Path],
    last_version: int,
    tmp_dir: Path,
) -> Path:
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for version in range(last_version + 1):
        if version in SKIP_MIGRATION_VERSIONS:
            continue
        src = files.get(version)
        if src is None:
            continue
        (tmp_dir / src.name).write_text(src.read_text())

    return tmp_dir


async def _apply_sql_file(pool: ConnectionPool, path: Path) -> None:
    sql = path.read_text()
    async with pool.acquire() as conn:
        await conn.execute(sql)


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_database_config() -> TestDatabaseConfig:
    return load_test_database_config()


@pytest_asyncio.fixture(scope="session")
async def ensure_test_database(
    test_database_config: TestDatabaseConfig,
) -> AsyncIterator[str]:
    """Ensure the test database exists and is reachable."""
    admin_conn = await asyncpg.connect(
        host=test_database_config.host,
        port=test_database_config.port,
        user=test_database_config.username,
        password=test_database_config.password,
        database="postgres",
    )
    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            test_database_config.database,
        )
        if not exists:
            database_name = test_database_config.database
            await admin_conn.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await admin_conn.close()

    yield test_database_config.database


@pytest_asyncio.fixture(scope="session", autouse=True)
async def preflight_db_check(test_database_config: TestDatabaseConfig) -> None:
    """Fail fast if Postgres is unreachable."""
    try:
        conn = await asyncpg.connect(
            host=test_database_config.host,
            port=test_database_config.port,
            user=test_database_config.username,
            password=test_database_config.password,
            database="postgres",
        )
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        pytest.exit(
            (
                "Database preflight failed: cannot reach server with provided "
                "credentials.\n"
                f"Host: {test_database_config.host} Port: {test_database_config.port} "
                f"User: {test_database_config.username}\nError: {exc}"
            ),
            returncode=1,
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_environment(
    ensure_test_database: str,
    test_database_config: TestDatabaseConfig,
) -> None:
    """Apply migrations and ensure paper trading tables exist."""
    config = DBConfig(
        host=test_database_config.host,
        port=test_database_config.port,
        database=ensure_test_database,
        username=test_database_config.username,
        password=test_database_config.password,
    )

    pool = ConnectionPool(config)
    await pool.initialize()
    try:
        migrations_dir = (
            Path(__file__).parent.parent.parent.parent.parent / "db" / "migrations"
        )
        if migrations_dir.exists():
            files = _load_migration_files(migrations_dir)
            available = set(files.keys()) - SKIP_MIGRATION_VERSIONS
            last = _last_contiguous_version(available)

            tmp_dir = Path(__file__).parent / "_migrations_contiguous"
            contiguous_dir = _prepare_contiguous_migrations_dir(
                files=files,
                last_version=last,
                tmp_dir=tmp_dir,
            )

            runner = MigrationRunner(pool, contiguous_dir)
            await runner.migrate_to_version(last)

            reports_migration = files.get(REPORTS_MIGRATION_VERSION)
            if reports_migration is not None:
                await _apply_sql_file(pool, reports_migration)
    finally:
        await pool.close()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test requiring database",
    )
