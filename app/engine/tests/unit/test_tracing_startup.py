import importlib
import os

import pytest

from app.engine.core import tracing


class TestTracingStartup:
    def test_init_tracing_from_env_calls_configure(self, monkeypatch):
        # Arrange: stub configure_tracing_from_env to observe calls
        called = {"count": 0}

        def _stub():  # type: ignore[no-untyped-def]
            called["count"] += 1

        monkeypatch.setenv("TRACING_DISABLED", "true")
        monkeypatch.setattr(tracing, "configure_tracing_from_env", _stub)

        # Act: import and call the startup helper
        from app.engine import main as main_mod

        # The helper may not be executed on import; call explicitly
        assert hasattr(main_mod, "init_tracing_from_env"), "helper missing"
        main_mod.init_tracing_from_env()

        # Assert: our stub was called once
        assert called["count"] == 1

    def test_startup_tracing_disabled_uses_noop(self, monkeypatch):
        monkeypatch.setenv("TRACING_DISABLED", "true")
        importlib.reload(tracing)

        from app.engine import main as main_mod

        main_mod.init_tracing_from_env()
        provider = tracing.get_tracer_provider()
        assert isinstance(provider, tracing.NoopTracerProvider)

    def test_startup_tracing_enabled_uses_regular(self, monkeypatch):
        monkeypatch.setenv("TRACING_DISABLED", "false")
        importlib.reload(tracing)

        from app.engine import main as main_mod

        main_mod.init_tracing_from_env()
        provider = tracing.get_tracer_provider()
        assert isinstance(provider, tracing.TracerProvider)
        assert not isinstance(provider, tracing.NoopTracerProvider)
