from __future__ import annotations


def _load_engine_config(monkeypatch: object, *, data_source: str) -> object:
    monkeypatch.setenv("BINANCE_DATA_SOURCE", data_source)
    monkeypatch.setenv("DB_PASSWORD", "password")
    monkeypatch.setenv("REDIS_HOST", "localhost")
    monkeypatch.setenv("ROUTER_URL", "http://localhost:8001")
    monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")

    from app.engine.main import load_configuration

    return load_configuration()


def test_load_configuration_sets_testnet_true_when_data_source_testnet(
    monkeypatch: object,
) -> None:
    cfg = _load_engine_config(monkeypatch, data_source="testnet")
    assert cfg.binance.testnet is True


def test_load_configuration_sets_testnet_false_when_data_source_mainnet(
    monkeypatch: object,
) -> None:
    cfg = _load_engine_config(monkeypatch, data_source="mainnet")
    assert cfg.binance.testnet is False
