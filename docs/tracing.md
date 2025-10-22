Tracing — Test Toggle and Startup Wiring

Defaults
- Tests default to disabled tracing by setting `TRACING_DISABLED=true`.
- Runtime wiring calls `init_tracing_from_env()` during app startup to honor the env setting.

How it works
- `core.tracing.configure_tracing_from_env()` installs a `NoopTracerProvider` when `TRACING_DISABLED=true`; otherwise a fresh `TracerProvider`.
- `app/engine/main.py:init_tracing_from_env()` delegates to that function and is invoked at the start of the FastAPI lifespan.

Opt‑in exporters
- When tracing is enabled, add processors/exporters (e.g., console/OTLP) programmatically where appropriate.
- Keep tests in noop mode to avoid noisy spans and flaky networking.

