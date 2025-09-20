"""Pytest configuration for integration tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import asyncpg

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def ensure_test_database():
    """Ensure test database exists."""
    admin_dsn = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_ADMIN_USER", "postgres"),
        "password": os.getenv("DB_ADMIN_PASSWORD", "postgres"),
        "database": "postgres",
    }

    test_db_name = os.getenv("TEST_DB_NAME", "test_trading_db")
    test_user = os.getenv("DB_USER", "trading_user")
    test_password = os.getenv("DB_PASSWORD", "trading_pass")

    # Connect as admin to create test database
    conn = await asyncpg.connect(**admin_dsn)
    try:
        # Check if test database exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", test_db_name
        )

        if not exists:
            # Create test database
            await conn.execute(f'CREATE DATABASE "{test_db_name}"')

            # Connect to test database to set up user
            test_conn = await asyncpg.connect(**{**admin_dsn, "database": test_db_name})
            try:
                # Create user if not exists
                user_exists = await test_conn.fetchval(
                    "SELECT 1 FROM pg_user WHERE usename = $1", test_user
                )
                if not user_exists:
                    await test_conn.execute(
                        f"CREATE USER {test_user} WITH PASSWORD '{test_password}'"
                    )

                # Grant privileges
                await test_conn.execute(
                    f"GRANT ALL PRIVILEGES ON DATABASE {test_db_name} TO {test_user}"
                )
                await test_conn.execute(f"GRANT CREATE ON SCHEMA public TO {test_user}")

            finally:
                await test_conn.close()

    finally:
        await conn.close()

    yield test_db_name


@pytest.fixture(scope="session", autouse=True)
async def setup_test_environment(ensure_test_database):
    """Set up test environment before running tests."""
    # Ensure migrations are applied
    from app.engine.adapters.db.connection_pool import DBConfig, ConnectionPool
    from app.engine.adapters.db.migrations import MigrationRunner

    config = DBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=ensure_test_database,
        username=os.getenv("DB_USER", "trading_user"),
        password=os.getenv("DB_PASSWORD", "trading_pass"),
    )

    pool = ConnectionPool(config)
    await pool.initialize()

    try:
        # Run migrations
        migrations_dir = (
            Path(__file__).parent.parent.parent.parent.parent / "db" / "migrations"
        )
        if migrations_dir.exists():
            runner = MigrationRunner(pool, migrations_dir)
            await runner.migrate_to_version()
    finally:
        await pool.close()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test requiring database"
    )
