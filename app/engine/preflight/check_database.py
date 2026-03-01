"""
Preflight check for database credentials and connectivity.

Usage:
    python -m app.engine.preflight.check_database

Checks that required environment variables are set and that a connection can
be established to the Postgres/TimescaleDB server and (if present) the test
database. Exits non‑zero and prints a clear, actionable error on failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import sys

import asyncpg

REQUIRED_ENV = [
    ("DB_HOST", "localhost"),
    ("DB_PORT", "5432"),
    ("DB_USER", None),
    ("DB_PASSWORD", None),
    ("TEST_DB_NAME", "test_trading_db"),
]


@dataclass
class DBEnv:
    host: str
    port: int
    user: str
    password: str
    database: str


def _read_env() -> tuple[DBEnv | None, list[str]]:
    missing: list[str] = []
    values: dict[str, str] = {}
    for key, default in REQUIRED_ENV:
        val = os.getenv(key, default)
        if val is None or (key in {"DB_USER", "DB_PASSWORD"} and not val):
            missing.append(key)
        else:
            assert val is not None
            values[key] = val
    if missing:
        return None, missing
    return (
        DBEnv(
            host=values["DB_HOST"],
            port=int(values["DB_PORT"]),
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
            database=values["TEST_DB_NAME"],
        ),
        [],
    )


async def _try_connect(dsn: dict[str, object]) -> None:
    conn = await asyncpg.connect(**dsn)
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()


async def check_db_connectivity(timeout_seconds: float = 5.0) -> None:
    """Validate DB env and basic connectivity.

    Raises:
        RuntimeError with a clear message if validation fails.
    """
    env, missing = _read_env()
    if missing:
        exports = "\n".join(f"export {k}=<value>" for k in missing)
        raise RuntimeError(
            "Missing required database environment variables:\n"
            + "\n".join(f"  - {k}" for k in missing)
            + "\n\nSet them, for example:\n"
            + exports,
        )
    assert env is not None

    # 1) Connect to server (default 'postgres' db) to verify host/port/creds
    server_dsn = {
        "host": env.host,
        "port": env.port,
        "user": env.user,
        "password": env.password,
        "database": "postgres",
        "timeout": timeout_seconds,
    }

    try:
        await _try_connect(server_dsn)
    except Exception as e:
        raise RuntimeError(
            "Unable to connect to Postgres server with provided credentials.\n"
            f"Host: {env.host}\nPort: {env.port}\nUser: {env.user}\n"
            f"Error: {e}\n\n"
            "Ensure the database is running and credentials are correct.\n"
            "If using Docker Compose, start with:\n"
            "  docker compose -f docker-compose.dev.yml up -d postgres\n",
        ) from e

    # 2) Connect to test database to verify it is reachable (it may be created by fixtures)
    test_dsn = {
        "host": env.host,
        "port": env.port,
        "user": env.user,
        "password": env.password,
        "database": env.database,
        "timeout": timeout_seconds,
    }
    try:
        await _try_connect(test_dsn)
    except Exception as e:
        raise RuntimeError(
            "Connected to server, but the test database is not accessible.\n"
            f"Database: {env.database}\nError: {e}\n\n"
            "If running integration tests, the suite will create/apply migrations.\n"
            "Alternatively, create the database manually or run migrations.\n",
        ) from e


def main() -> int:
    try:
        asyncio.run(check_db_connectivity())
        print("✅ Database preflight check passed.")
        return 0
    except Exception as e:
        print(f"❌ Database preflight failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
