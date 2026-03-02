from __future__ import annotations


def test_load_configuration_parses_database_url_when_provided(monkeypatch: object) -> None:
    monkeypatch.setenv(  # type: ignore[attr-defined]
        "DATABASE_URL",
        "postgresql://trading_user:password@postgres:5432/trading_platform",
    )
    monkeypatch.setenv("BINANCE_DATA_SOURCE", "mainnet")  # type: ignore[attr-defined]
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")  # type: ignore[attr-defined]
    monkeypatch.setenv("ROUTER_URL", "http://router:8001")  # type: ignore[attr-defined]
    monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")  # type: ignore[attr-defined]

    from app.engine.main import load_configuration

    cfg = load_configuration()

    assert cfg.database.host == "postgres"  # type: ignore[attr-defined]
    assert cfg.database.port == 5432  # type: ignore[attr-defined]
    assert cfg.database.database == "trading_platform"  # type: ignore[attr-defined]
    assert cfg.database.username == "trading_user"  # type: ignore[attr-defined]
    assert cfg.database.password == "password"  # type: ignore[attr-defined]

