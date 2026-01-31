"""
Pytest fixtures to bootstrap the global EventBus and start core services.
Starts EventBus, FeatureService, and SMCEngine for integration-style tests
that depend on real event flow without mocks.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import os
from pathlib import Path
from typing import TYPE_CHECKING
import uuid

import pytest
import pytest_asyncio
import redis.asyncio as redis

from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.adapters.db.migrations import MigrationRunner
from app.engine.preflight.check_database import check_db_connectivity

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from asyncpg import Record


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncIterator[redis.Redis]:
    """Session-scoped Redis client using REDIS_URL; skips when not configured.

    Requires REDIS_URL (supports rediss://). No legacy host/port fallback.
    """
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set; skipping Redis-marked tests")

    client = redis.from_url(url, decode_responses=False)
    try:
        # Basic connectivity check
        try:
            pong = await client.ping()
        except Exception as exc:
            pytest.skip(f"Redis connection failed; skipping ({exc!s})")
        if pong is not True:
            pytest.skip("Redis PING failed; skipping")
        yield client
    finally:
        with suppress(Exception):
            await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def redis_key(redis_client: redis.Redis) -> AsyncIterator[str]:
    """Generate a unique, namespaced key and ensure cleanup after test."""
    key = f"pytest:{uuid.uuid4().hex}"
    try:
        yield key
    finally:
        with suppress(Exception):
            await redis_client.delete(key)


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create a dedicated event loop for async tests in this package."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def event_bus_and_services() -> AsyncIterator[None]:
    """Start EventBus and core services for tests, teardown after session."""
    # Import lazily to avoid loading heavy deps when fixture isn't used
    from app.engine.bus import set_event_bus
    from app.engine.core.event_bus_factory import EventBusConfig, EventBusFactory
    from app.engine.features.feature_service import FeatureService
    from app.engine.smc.engine import SMCEngine

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
    smc_engine = SMCEngine()

    await feature_service.start()
    await smc_engine.start()

    yield

    # Teardown services and bus
    await feature_service.stop()
    await smc_engine.stop()
    await bus.stop()


class _DBClient:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    async def execute(self, sql: str, *args: object) -> str:
        async with self._pool.acquire() as conn:  # type: ignore[attr-defined]
            return await conn.execute(sql, *args)

    async def fetch_one(self, sql: str, *args: object) -> Record | None:
        async with self._pool.acquire() as conn:  # type: ignore[attr-defined]
            return await conn.fetchrow(sql, *args)


@pytest_asyncio.fixture(scope="function")
async def real_db() -> AsyncIterator[_DBClient]:
    """Provide a real database connection by initializing the pool and running migrations.

    Reads env vars DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, TEST_DB_NAME.
    Applies migrations found under repo-root/db/migrations.
    Yields the ConnectionPool for direct DB access if needed.
    """
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
        runner = MigrationRunner(pool, migrations_dir)
        await runner.migrate_to_version()
        yield _DBClient(pool)
    finally:
        await pool.close()


@pytest_asyncio.fixture()
async def clean_test_data(real_db: _DBClient) -> None:
    """Clean tables between tests that touch the DB."""
    for table in [
        "candles",
        "indicators",
        "zones",
        "orders",
        "positions",
        "trading_decisions",
        "smc_events",
    ]:
        with suppress(Exception):
            await real_db.execute(f"TRUNCATE TABLE {table} CASCADE")


@pytest_asyncio.fixture(scope="function", autouse=True)
async def _auto_event_flow_bus_services(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
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
        except Exception as e:
            pytest.exit(f"Database preflight failed for event_flow: {e}", returncode=1)
        request.getfixturevalue("event_bus_and_services")
        # Ensure the underlying fixture is awaited/entered at least once
        # by requesting it; then yield to test and teardown happens via fixture itself
        yield
    else:
        yield
