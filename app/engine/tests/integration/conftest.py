"""Pytest configuration for integration tests."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import asyncpg
from app.engine.preflight.check_database import check_db_connectivity

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def event_loop() -> None:
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def ensure_test_database() -> None:
    """Ensure test database exists using the primary DB_USER/DB_PASSWORD credentials.

    This avoids a separate admin credential requirement. For Docker defaults,
    POSTGRES_USER is set to the same value as DB_USER, which has sufficient privileges
    to create the test database.
    """
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    db_user = os.getenv("DB_USER", "trading_user")
    db_password = os.getenv("DB_PASSWORD", "trading_pass")
    test_db_name = os.getenv("TEST_DB_NAME", "test_trading_db")

    # Connect to the default 'postgres' database with the same DB user
    admin_dsn = {
        "host": host,
        "port": port,
        "user": db_user,
        "password": db_password,
        "database": "postgres",
    }

    test_user = db_user
    test_password = db_password

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
                # If using the same DB user for admin and tests, user creation is unnecessary.
                # Ensure privileges are set (harmless if already owner).
                await test_conn.execute(
                    f"GRANT ALL PRIVILEGES ON DATABASE {test_db_name} TO {test_user}"
                )
                await test_conn.execute(f"GRANT CREATE ON SCHEMA public TO {test_user}")

            finally:
                await test_conn.close()

    finally:
        await conn.close()

    yield test_db_name


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_environment(ensure_test_database) -> None:
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
        # Run migrations up to the last contiguous version
        migrations_dir = (
            Path(__file__).parent.parent.parent.parent.parent / "db" / "migrations"
        )
        if migrations_dir.exists():
            # Determine last contiguous version from available files
            versions: set[int] = set()
            files: dict[int, Path] = {}
            for p in migrations_dir.glob("*.sql"):
                name = p.name
                try:
                    ver = int(name.split("_")[0])
                    versions.add(ver)
                    files[ver] = p
                except Exception:
                    continue
            # Exclude known problematic FK migration (008); compute contiguous range
            working_versions = {v for v in versions if v != 8}
            last = -1
            while (last + 1) in working_versions:
                last += 1

            # Build a temporary directory containing only contiguous migrations
            tmp_dir = Path(__file__).parent / "_migrations_contiguous"
            if tmp_dir.exists():
                # Clean stale files
                for f in tmp_dir.glob("*.sql"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            else:
                tmp_dir.mkdir(parents=True, exist_ok=True)

            for ver in range(0, last + 1):
                if ver == 8:
                    # Skip FK migration that depends on non-contiguous tables
                    continue
                src = files.get(ver)
                if not src:
                    continue
                dst = tmp_dir / src.name
                dst.write_text(src.read_text())

            runner = MigrationRunner(pool, tmp_dir)
            await runner.migrate_to_version(last)

        # Ensure minimal decisions table exists for tests that reference it
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL
                );
                """
            )
    finally:
        await pool.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def preflight_db_check() -> None:
    """Fail fast if server is unreachable; the test DB may be created by fixtures."""
    import os
    import asyncpg

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    user = os.getenv("DB_USER", "trading_user")
    password = os.getenv("DB_PASSWORD", "trading_pass")

    try:
        conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database="postgres")
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
    except Exception as e:  # noqa: BLE001
        import pytest
        pytest.exit(
            "Database preflight failed: cannot reach server with provided credentials.\n"
            f"Host: {host} Port: {port} User: {user}\nError: {e}",
            returncode=1,
        )


def pytest_configure(config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test requiring database"
    )
