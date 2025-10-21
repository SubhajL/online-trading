import os
import importlib
import pytest

from app.engine.core import tracing


class TestTracingConfig:
    def test_init_tracer_disabled_uses_noop_provider(self, monkeypatch):
        monkeypatch.setenv("TRACING_DISABLED", "true")
        importlib.reload(tracing)
        tracing.configure_tracing_from_env()
        provider = tracing.get_tracer_provider()
        assert isinstance(provider, tracing.NoopTracerProvider)

    def test_init_tracer_enabled_uses_regular_provider(self, monkeypatch):
        monkeypatch.setenv("TRACING_DISABLED", "false")
        importlib.reload(tracing)
        tracing.configure_tracing_from_env()
        provider = tracing.get_tracer_provider()
        assert isinstance(provider, tracing.TracerProvider)
        assert not isinstance(provider, tracing.NoopTracerProvider)