from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class TestDatabaseConfig:
    host: str
    port: int
    username: str
    password: str
    database: str


def load_test_database_config() -> TestDatabaseConfig:
    """Load integration-test DB config from `TEST_DATABASE_URL`."""
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://trading_user:your_secure_password_here@localhost:5432/trading_platform_test",
    )
    parsed = urlparse(database_url)

    return TestDatabaseConfig(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        username=parsed.username or "trading",
        password=parsed.password or "trading",
        database=parsed.path.lstrip("/") or "trading_test",
    )
