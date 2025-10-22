"""
Pytest fixtures to bootstrap the global EventBus and start core services.
Starts EventBus, FeatureService, and SMCService for integration-style tests
that depend on real event flow without mocks.
"""

import asyncio
import pytest
import pytest_asyncio
import os
from pathlib import Path
from app.engine.preflight.check_database import check_db_connectivity
import pytest
import pytest_asyncio

# Redis fixtures
import os
import uuid
import redis.asyncio as redis


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise KeyError(name)
    return val


@pytest_asyncio.fixture(scope="function")
async def redis_client():
    """Session-scoped Redis client using REDIS_URL; skips when not configured.

    Requires REDIS_URL (supports rediss://). No legacy host/port fallback.
    """
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set; skipping Redis-marked tests")

    client = redis.from_url(url, decode_responses=False)
    try:
        # Basic connectivity check
        pong = await client.ping()
        if pong is not True:
            pytest.skip("Redis PING failed; skipping")
        yield client
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


@pytest_asyncio.fixture(scope="function")
async def redis_key(redis_client):
    """Generate a unique, namespaced key and ensure cleanup after test."""
    key = f"pytest:{uuid.uuid4().hex}"
    try:
        yield key
    finally:
        try:
            await redis_client.delete(key)
        except Exception:
            pass


@pytest.fixture(scope="session")
def event_loop():
    """Create a dedicated event loop for async tests in this package."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def event_bus_and_services():
    """Start EventBus and core services for tests, teardown after session."""
    # Import lazily to avoid loading heavy deps when fixture isn't used
    from app.engine.bus import set_event_bus
    from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
    from app.engine.features.feature_service import FeatureService
    from app.engine.smc.smc_service import SMCService
    # Configure event bus consistent with tests: priority queue on, DLQ off
    cfg = EventBusConfig(
        use_priority_queue=True,
        dlq_on_any_failure=False,
        num_workers=2,
        max_queue_size=10000,
        dead_letter_queue_size=1000,
    )

    bus = EventBusFactory().create_with_config(cfg)
    set_event_bus(bus)

    await bus.start()

    feature_service = FeatureService(
        buffer_size=1000,
        ema_periods=[9, 21],
        rsi_period=7,
        macd_params=(6, 13, 5),
        atr_period=7,
        bb_period=10,
        bb_std_dev=2.0,
    )
    smc_service = SMCService()

    await feature_service.start()
    await smc_service.start()

    yield

    # Teardown services and bus
    await feature_service.stop()
    await smc_service.stop()
    await bus.stop()


class _DBClient:
    def __init__(self, pool) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def fetch_one(self, sql: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(sql, *args)


@pytest_asyncio.fixture(scope="function")
async def real_db():
    """Provide a real database connection by initializing the pool and running migrations.

    Reads env vars DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, TEST_DB_NAME.
    Applies migrations found under repo-root/db/migrations.
    Yields the ConnectionPool for direct DB access if needed.
    """
    from app.engine.adapters.db.connection_pool import DBConfig, ConnectionPool
    from app.engine.adapters.db.migrations import MigrationRunner

    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("TEST_DB_NAME", "test_trading_db")
    username = os.getenv("DB_USER", "trading_user")
    password = os.getenv("DB_PASSWORD", "trading_pass")

    cfg = DBConfig(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        pool_size=5,
    )

    pool = ConnectionPool(cfg)
    await pool.initialize()

    try:
        # Apply migrations from repo root
        repo_root = Path(__file__).resolve().parents[3]
        migrations_dir = repo_root / "db" / "migrations"
        if migrations_dir.exists():
            # Build a filtered, contiguous migrations directory skipping known gaps (e.g., 008)
            versions: set[int] = set()
            files: dict[int, Path] = {}
            for p in migrations_dir.glob("*.sql"):
                try:
                    ver = int(p.name.split("_")[0])
                    versions.add(ver)
                    files[ver] = p
                except Exception:
                    continue
            working_versions = {v for v in versions if v != 8}
            last = -1
            while (last + 1) in working_versions:
                last += 1

            tmp_dir = repo_root / "db" / "_migrations_contiguous_event_flow"
            if tmp_dir.exists():
                for f in tmp_dir.glob("*.sql"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            else:
                tmp_dir.mkdir(parents=True, exist_ok=True)

            for ver in range(0, last + 1):
                src = files.get(ver)
                if not src:
                    continue
                dst = tmp_dir / src.name
                dst.write_text(src.read_text())

            runner = MigrationRunner(pool, tmp_dir)
            await runner.migrate_to_version(last)

        # Ensure minimal decisions exists for FK references in tests
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
        yield _DBClient(pool)
    finally:
        await pool.close()


@pytest_asyncio.fixture()
async def clean_test_data(real_db):
    """Clean tables between tests that touch the DB."""
    for table in [
        "candles",
        "indicators",
        "zones",
        "orders",
        "positions",
        "decisions",
        "smc_events",
    ]:
        try:
            await real_db.execute(f"TRUNCATE TABLE {table} CASCADE")
        except Exception:
            # If table doesn't exist, ignore to avoid coupling
            pass


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _auto_event_flow_bus_services(request, event_bus_and_services):
    """Automatically start bus + services for event_flow module only.

    This ensures services are available without altering other test modules.
    Tests within test_event_flow.py still manage their own bus usage; this fixture
    starts a background bus/services to satisfy scenarios that expect them alive.
    """
    module_name = getattr(request, "module", None)
    if not module_name:
        yield
        return
    if getattr(module_name, "__name__", "").endswith("test_event_flow"):
        # Verify DB connectivity first to fail fast with clear message
        try:
            await check_db_connectivity()
        except Exception as e:  # noqa: BLE001
            import pytest

            pytest.exit(f"Database preflight failed for event_flow: {e}", returncode=1)
        # event_bus_and_services is session-scoped; referencing ensures it's active
        yield
    else:
        yield
