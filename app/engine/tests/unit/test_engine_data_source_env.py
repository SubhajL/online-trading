from __future__ import annotations


def _load_engine_config(monkeypatch: object, *, data_source: str) -> object:
    monkeypatch.setenv("BINANCE_DATA_SOURCE", data_source)  # type: ignore[attr-defined]
    monkeypatch.setenv("DB_PASSWORD", "password")  # type: ignore[attr-defined]
    monkeypatch.setenv("REDIS_HOST", "localhost")  # type: ignore[attr-defined]
    monkeypatch.setenv("ROUTER_URL", "http://localhost:8001")  # type: ignore[attr-defined]
    monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")  # type: ignore[attr-defined]

    from app.engine.main import load_configuration

    return load_configuration()


def test_load_configuration_sets_testnet_true_when_data_source_testnet(
    monkeypatch: object,
) -> None:
    cfg = _load_engine_config(monkeypatch, data_source="testnet")
    assert cfg.binance.testnet is True  # type: ignore[attr-defined]


def test_load_configuration_sets_testnet_false_when_data_source_mainnet(
    monkeypatch: object,
) -> None:
    cfg = _load_engine_config(monkeypatch, data_source="mainnet")
    assert cfg.binance.testnet is False  # type: ignore[attr-defined]
