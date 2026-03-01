from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

from app.engine.adapters.db.connection_pool import ConnectionPool, DBConfig
from app.engine.adapters.db.migrations import MigrationRunner


def _load_database_url(database_url_arg: str | None) -> str:
    if database_url_arg:
        return database_url_arg

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    test_database_url = os.getenv("TEST_DATABASE_URL")
    if test_database_url:
        return test_database_url

    raise SystemExit(
        "Missing database URL. Provide --database-url or set DATABASE_URL/TEST_DATABASE_URL.",
    )


def _parse_database_url(database_url: str) -> DBConfig:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise SystemExit(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")

    host = parsed.hostname
    port = parsed.port
    username = parsed.username
    password = parsed.password
    database = parsed.path.lstrip("/")

    if not host or not port or not username or password is None or not database:
        raise SystemExit(
            "Invalid DATABASE_URL. Expected postgresql://user:pass@host:port/dbname",
        )

    return DBConfig(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
    )


def _default_migrations_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "db" / "migrations"


async def _run_migrations(*, database_url: str, migrations_dir: Path) -> None:
    config = _parse_database_url(database_url)
    pool = ConnectionPool(config)
    await pool.initialize()
    try:
        runner = MigrationRunner(pool, migrations_dir)
        await runner.migrate_to_version()
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply SQL migrations to the database.")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--migrations-dir", type=Path, default=_default_migrations_dir())
    args = parser.parse_args()

    database_url = _load_database_url(args.database_url)
    asyncio.run(
        _run_migrations(database_url=database_url, migrations_dir=args.migrations_dir),
    )


if __name__ == "__main__":
    main()
