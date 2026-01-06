from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class _StubDatabaseCfg:
    host: str = "localhost"
    port: int = 5432
    database: str = "test"
    username: str = "user"
    password: str = "placeholder"  # noqa: S105


@dataclass
class _StubRedisCfg:
    host: str = "localhost"
    port: int = 6379
    password: str | None = None


@dataclass
class _StubConfig:  # Minimal stand-in for EngineConfig
    database: _StubDatabaseCfg
    redis: _StubRedisCfg
    binance: object
    risk_parameters: object


class _StubAsyncService:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _StubEventBus(_StubAsyncService):
    def __init__(self) -> None:
        super().__init__()
        self.subscribed: list[tuple[str, list[object] | None]] = []
        self.unsubscribed: list[str] = []

    async def subscribe(  # type: ignore[no-untyped-def]
        self,
        subscriber_id: str,
        handler: object,
        event_types: list[object] | None = None,
        priority: int = 0,
    ) -> str:
        _ = handler, priority
        self.subscribed.append((subscriber_id, event_types))
        return "sub-1"

    async def unsubscribe(self, subscription_id: str) -> bool:
        self.unsubscribed.append(subscription_id)
        return True


class _StubDBAdapter:
    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _StubRedisAdapter(_StubDBAdapter):
    pass


class _StubRouterClient(_StubDBAdapter):
    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "payload": payload}


@pytest.mark.asyncio
class TestMainExecutionWiring:
    async def test_initialize_services_registers_execution_subscriber_when_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()

        bus = _StubEventBus()
        monkeypatch.setenv("EXECUTION_MODE", "futures_testnet")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        monkeypatch.setattr(main_mod, "IngestService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "FeatureService", lambda: _StubAsyncService())
        monkeypatch.setattr(main_mod, "SMCService", lambda: _StubAsyncService())
        monkeypatch.setattr(main_mod, "DecisionEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=object(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]

        assert "execution_subscriber" in main_mod.services

    async def test_start_services_starts_execution_subscriber(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()
        bus = _StubEventBus()

        monkeypatch.setenv("EXECUTION_MODE", "futures_testnet")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        ingest = _StubAsyncService()
        features = _StubAsyncService()
        smc = _StubAsyncService()
        decision = _StubAsyncService()
        monkeypatch.setattr(main_mod, "IngestService", lambda **_: ingest)
        monkeypatch.setattr(main_mod, "FeatureService", lambda: features)
        monkeypatch.setattr(main_mod, "SMCService", lambda: smc)
        monkeypatch.setattr(main_mod, "DecisionEngine", lambda **_: decision)
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=object(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]
        await main_mod.start_services()

        assert bus.started is True
        assert ingest.started is True
        assert features.started is True
        assert smc.started is True
        assert decision.started is True
        assert any(sub_id == "router-execution" for sub_id, _ in bus.subscribed)
