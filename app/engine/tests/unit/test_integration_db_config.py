from __future__ import annotations

from typing import Protocol

from app.engine.tests.integration.db_config import load_test_database_config

TEST_PORT = 5433
DEFAULT_PORT = 5432
DEFAULT_USERNAME = "trading_user"
DEFAULT_PASSWORD = "your_secure_password_here"  # noqa: S105
DEFAULT_DATABASE = "trading_platform_test"


class MonkeyPatchLike(Protocol):
    def setenv(self, name: str, value: str) -> None: ...

    def delenv(self, name: str, *, raising: bool) -> None: ...


def test_load_test_database_config_parses_test_database_url(
    monkeypatch: MonkeyPatchLike,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", f"postgresql://u:p@h:{TEST_PORT}/db")

    cfg = load_test_database_config()

    assert cfg.host == "h"
    assert cfg.port == TEST_PORT
    assert cfg.username == "u"
    assert cfg.password == "p"  # noqa: S105
    assert cfg.database == "db"


def test_load_test_database_config_defaults_when_env_missing(
    monkeypatch: MonkeyPatchLike,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    cfg = load_test_database_config()

    assert cfg.host == "localhost"
    assert cfg.port == DEFAULT_PORT
    assert cfg.username == DEFAULT_USERNAME
    assert cfg.password == DEFAULT_PASSWORD
    assert cfg.database == DEFAULT_DATABASE
