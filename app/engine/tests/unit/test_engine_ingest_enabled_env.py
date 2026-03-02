from __future__ import annotations

import pytest


class _StubService:
    def __init__(self) -> None:
        self.started = 0

    async def start(self) -> None:
        self.started += 1


def test_ingest_enabled_from_env_defaults_true(monkeypatch: object) -> None:
    monkeypatch.delenv("INGEST_ENABLED", raising=False)  # type: ignore[attr-defined]

    from app.engine.main import _ingest_enabled_from_env

    assert _ingest_enabled_from_env() is True


def test_ingest_enabled_from_env_false_when_zero(monkeypatch: object) -> None:
    monkeypatch.setenv("INGEST_ENABLED", "0")  # type: ignore[attr-defined]

    from app.engine.main import _ingest_enabled_from_env

    assert _ingest_enabled_from_env() is False


@pytest.mark.asyncio
async def test_start_services_skips_ingest_when_not_present(monkeypatch: object) -> None:
    monkeypatch.setenv("INGEST_ENABLED", "0")  # type: ignore[attr-defined]

    from app.engine import main as engine_main

    previous_services = dict(engine_main.services)
    try:
        engine_main.services.clear()
        engine_main.services["event_bus"] = _StubService()
        engine_main.services["features"] = _StubService()
        engine_main.services["smc"] = _StubService()
        engine_main.services["retest_engine"] = _StubService()
        engine_main.services["decision_publisher"] = _StubService()

        await engine_main.start_services()

        assert engine_main.services["event_bus"].started == 1
        assert engine_main.services["features"].started == 1
    finally:
        engine_main.services.clear()
        engine_main.services.update(previous_services)

