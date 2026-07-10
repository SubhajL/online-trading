from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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

    async def subscribe(
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

    async def insert_equity_sample(
        self,
        *,
        equity: Decimal,
        timestamp: datetime,
        source_timestamp: datetime | None = None,
    ) -> bool:
        _ = equity, timestamp, source_timestamp
        return True


class _StubRedisAdapter(_StubDBAdapter):
    pass


class _StubRouterClient(_StubDBAdapter):
    async def place_bracket_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "payload": payload}

    async def get_internal_equity(self, *, venue: str | None = None) -> tuple[Decimal, datetime]:
        _ = venue
        return Decimal("10000"), datetime(2026, 2, 6, 12, 0, tzinfo=UTC)


class _StubTelegramAdapter(_StubAsyncService):
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, *, bot_token: str, chat_id: str, db_adapter: object | None = None) -> None:
        super().__init__()
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.db_adapter = db_adapter
        type(self).last_kwargs = {
            "bot_token": bot_token,
            "chat_id": chat_id,
            "db_adapter": db_adapter,
        }


class _CapturingAlertSubscriber:
    last_kwargs: dict[str, Any] | None = None

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_kwargs = dict(kwargs)

    async def register(self, event_bus: object) -> None:
        _ = event_bus

    async def stop(self) -> None:
        return None


@pytest.mark.asyncio
class TestMainExecutionWiring:
    async def test_initialize_services_sanitizes_trading_symbols(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()

        captured: dict[str, Any] = {}

        def ingest_ctor(**kwargs: Any) -> _StubAsyncService:
            captured["symbols"] = kwargs.get("symbols")
            return _StubAsyncService()

        bus = _StubEventBus()
        monkeypatch.setenv("EXECUTION_MODE", "disabled")
        monkeypatch.setenv("TRADING_SYMBOLS", " BTCUSDT , ethusdt ,, ")
        monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        monkeypatch.setattr(main_mod, "IngestService", lambda **kw: ingest_ctor(**kw))
        monkeypatch.setattr(main_mod, "FeatureService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=type(
                "RiskParams",
                (),
                {
                    "risk_per_trade": Decimal("0.01"),
                    "max_position_size": Decimal(1),
                },
            )(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]

        assert captured["symbols"] == ["BTCUSDT", "ETHUSDT"]

    async def test_initialize_services_fails_fast_when_trading_symbols_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()

        def ingest_ctor(**_kwargs: Any) -> _StubAsyncService:
            return _StubAsyncService()

        bus = _StubEventBus()
        monkeypatch.setenv("EXECUTION_MODE", "disabled")
        monkeypatch.setenv("TRADING_SYMBOLS", " , ,  ,")
        monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        monkeypatch.setattr(main_mod, "IngestService", lambda **kw: ingest_ctor(**kw))
        monkeypatch.setattr(main_mod, "FeatureService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=type(
                "RiskParams",
                (),
                {
                    "risk_per_trade": Decimal("0.01"),
                    "max_position_size": Decimal(1),
                },
            )(),
        )

        with pytest.raises(RuntimeError, match="TRADING_SYMBOLS"):
            await main_mod.initialize_services(cfg)  # type: ignore[arg-type]

    async def test_initialize_services_registers_execution_subscriber_when_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()

        bus = _StubEventBus()
        monkeypatch.setenv("EXECUTION_MODE", "futures_testnet")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")
        monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        monkeypatch.setattr(main_mod, "IngestService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "FeatureService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=type(
                "RiskParams",
                (),
                {
                    "risk_per_trade": Decimal("0.01"),
                    "max_position_size": Decimal(1),
                },
            )(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]

        assert "execution_subscriber" in main_mod.services
        assert "retest_engine" in main_mod.services
        assert "decision_publisher" in main_mod.services
        assert "execution_cooldown" in main_mod.services
        assert "alert_cooldown" in main_mod.services
        assert main_mod.services["execution_cooldown"] is not main_mod.services["alert_cooldown"]

    async def test_start_services_starts_execution_subscriber(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()
        bus = _StubEventBus()

        monkeypatch.setenv("EXECUTION_MODE", "futures_testnet")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")
        monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        ingest = _StubAsyncService()
        features = _StubAsyncService()
        smc = _StubAsyncService()
        retest = _StubAsyncService()
        publisher = _StubAsyncService()
        monkeypatch.setattr(main_mod, "IngestService", lambda **_: ingest)
        monkeypatch.setattr(main_mod, "FeatureService", lambda **_: features)
        monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: smc)
        monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: retest)
        monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: publisher)
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=type(
                "RiskParams",
                (),
                {
                    "risk_per_trade": Decimal("0.01"),
                    "max_position_size": Decimal(1),
                },
            )(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]
        await main_mod.start_services()

        assert bus.started is True
        assert ingest.started is True
        assert features.started is True
        assert smc.started is True
        assert retest.started is True
        assert publisher.started is True
        assert any(sub_id == "router-execution" for sub_id, _ in bus.subscribed)

    async def test_initialize_services_enables_execution_decision_alerts_when_flag_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod
        from app.engine.adapters.alert import alert_subscriber as alert_subscriber_mod
        from app.engine.adapters.alert import telegram as telegram_mod

        main_mod.services.clear()
        _CapturingAlertSubscriber.last_kwargs = None
        _StubTelegramAdapter.last_kwargs = None

        bus = _StubEventBus()
        monkeypatch.setenv("EXECUTION_MODE", "futures_testnet")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")
        monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat-1")
        monkeypatch.setenv("TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED", "1")

        monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
        monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
        monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())

        monkeypatch.setattr(main_mod, "IngestService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "FeatureService", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: _StubAsyncService())
        monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())

        monkeypatch.setattr(alert_subscriber_mod, "AlertSubscriber", _CapturingAlertSubscriber)
        monkeypatch.setattr(telegram_mod, "TelegramAlertAdapter", _StubTelegramAdapter)

        monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)
        import app.engine.bus as bus_mod

        monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)

        cfg = _StubConfig(
            database=_StubDatabaseCfg(),
            redis=_StubRedisCfg(),
            binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
            risk_parameters=type(
                "RiskParams",
                (),
                {
                    "risk_per_trade": Decimal("0.01"),
                    "max_position_size": Decimal(1),
                },
            )(),
        )

        await main_mod.initialize_services(cfg)  # type: ignore[arg-type]

        assert _CapturingAlertSubscriber.last_kwargs is not None
        assert _CapturingAlertSubscriber.last_kwargs["execution_enabled"] is True
        assert _CapturingAlertSubscriber.last_kwargs["execution_decision_alerts_enabled"] is True
        assert _StubTelegramAdapter.last_kwargs is not None
        assert _StubTelegramAdapter.last_kwargs["db_adapter"] is not None


def _patch_main_stubs(
    monkeypatch: pytest.MonkeyPatch,
    main_mod: Any,
    ingest_ctor: Any,
) -> _StubEventBus:
    bus = _StubEventBus()
    monkeypatch.setenv("EXECUTION_MODE", "disabled")
    monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")
    monkeypatch.setenv("LIVE_REST_FALLBACK_ENABLED", "0")

    monkeypatch.setattr(main_mod, "TimescaleDBAdapter", lambda **_: _StubDBAdapter())
    monkeypatch.setattr(main_mod, "RedisAdapter", lambda **_: _StubRedisAdapter())
    monkeypatch.setattr(main_mod, "RouterHTTPClient", lambda **_: _StubRouterClient())
    monkeypatch.setattr(main_mod, "IngestService", lambda **kw: ingest_ctor(**kw))
    monkeypatch.setattr(main_mod, "FeatureService", lambda **_: _StubAsyncService())
    monkeypatch.setattr(main_mod, "SMCEngine", lambda **_: _StubAsyncService())
    monkeypatch.setattr(main_mod, "RetestEngine", lambda **_: _StubAsyncService())
    monkeypatch.setattr(main_mod, "DecisionPublisher", lambda **_: _StubAsyncService())
    monkeypatch.setattr(main_mod, "RiskManager", lambda *_: object())
    monkeypatch.setattr(main_mod, "set_event_bus", lambda *_: None)

    import app.engine.bus as bus_mod

    monkeypatch.setattr(bus_mod, "create_event_bus", lambda: bus)
    return bus


def _stub_cfg() -> _StubConfig:
    return _StubConfig(
        database=_StubDatabaseCfg(),
        redis=_StubRedisCfg(),
        binance=type("BinanceCfg", (), {"api_key": "", "api_secret": "", "testnet": True})(),
        risk_parameters=type(
            "RiskParams",
            (),
            {
                "risk_per_trade": Decimal("0.01"),
                "max_position_size": Decimal(1),
            },
        )(),
    )


_SHARED_INGEST_TIMEFRAME_VALUES = ["5m", "15m", "1h", "4h"]


@pytest.mark.asyncio
class TestTrendLiveMainWiring:
    """Phase 3a isolation: flag off is inert; flag on leaves shared ingest alone."""

    async def test_trend_live_default_off_registers_no_services(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()
        monkeypatch.delenv("TREND_LIVE_ENABLED", raising=False)

        captured: dict[str, Any] = {}

        def ingest_ctor(**kwargs: Any) -> _StubAsyncService:
            captured["timeframes"] = kwargs.get("timeframes")
            return _StubAsyncService()

        _patch_main_stubs(monkeypatch, main_mod, ingest_ctor)

        await main_mod.initialize_services(_stub_cfg())  # type: ignore[arg-type]

        assert (
            [key for key in main_mod.services if key.startswith("trend_")],
            [tf.value for tf in captured["timeframes"]],
        ) == ([], _SHARED_INGEST_TIMEFRAME_VALUES)

    async def test_trend_live_flag_on_keeps_shared_ingest_timeframes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        main_mod.services.clear()
        monkeypatch.setenv("TREND_LIVE_ENABLED", "1")

        captured: dict[str, Any] = {}

        def ingest_ctor(**kwargs: Any) -> _StubAsyncService:
            captured["timeframes"] = kwargs.get("timeframes")
            return _StubAsyncService()

        _patch_main_stubs(monkeypatch, main_mod, ingest_ctor)

        poller = _StubAsyncService()

        async def stub_trend_wiring(**kwargs: Any) -> dict[str, Any]:
            captured["trend_kwargs"] = kwargs
            return {
                "trend_paper_broker": object(),
                "trend_decision_service": object(),
                "trend_daily_poller": poller,
            }

        monkeypatch.setattr(main_mod, "initialize_trend_live_services", stub_trend_wiring)

        await main_mod.initialize_services(_stub_cfg())  # type: ignore[arg-type]
        await main_mod.start_services()

        assert (
            sorted(key for key in main_mod.services if key.startswith("trend_")),
            [tf.value for tf in captured["timeframes"]],
            poller.started,
        ) == (
            ["trend_daily_poller", "trend_decision_service", "trend_paper_broker"],
            _SHARED_INGEST_TIMEFRAME_VALUES,
            True,
        )


class TestTelegramExecutionDecisionAlertsDefault:
    """Decision alerts in execution mode are opt-out (default enabled)."""

    def test_helper_defaults_to_enabled_when_env_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        monkeypatch.delenv("TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED", raising=False)

        assert main_mod._telegram_execution_decision_alerts_enabled_from_env() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_helper_opt_out_values_disable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        value: str,
    ) -> None:
        from app.engine import main as main_mod

        monkeypatch.setenv("TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED", value)

        assert main_mod._telegram_execution_decision_alerts_enabled_from_env() is False


class TestRiskPerTradeDefault:
    """Documented risk is 0.5% fixed-fractional per trade (CLAUDE.md)."""

    def test_load_configuration_defaults_risk_per_trade_to_half_percent(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        monkeypatch.delenv("RISK_PER_TRADE", raising=False)
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")

        cfg = main_mod.load_configuration()

        assert cfg.risk_parameters.risk_per_trade == Decimal("0.005")

    def test_load_configuration_env_overrides_risk_per_trade(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.engine import main as main_mod

        monkeypatch.setenv("RISK_PER_TRADE", "0.02")
        monkeypatch.setenv("TRADING_SYMBOLS", "BTCUSDT")

        cfg = main_mod.load_configuration()

        assert cfg.risk_parameters.risk_per_trade == Decimal("0.02")
