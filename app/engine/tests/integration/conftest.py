"""Integration-test DB setup.

This suite is intended to run against a local Postgres instance specified via
`TEST_DATABASE_URL` (see `.env.example`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


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
    except Exception as exc:
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
    """Apply migrations to the test database."""
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
        runner = MigrationRunner(pool, migrations_dir)
        await runner.migrate_to_version()
    finally:
        await pool.close()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test requiring database",
    )
    config.addinivalue_line(
        "markers",
        "e2e: mark test as end-to-end requiring full stack (BFF, Telegram, Binance)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    for item in items:
        existing = {m.name for m in item.iter_markers()}
        if "e2e" not in existing:
            item.add_marker(pytest.mark.integration)
