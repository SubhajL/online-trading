from __future__ import annotations

import argparse
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
from urllib.error import URLError

import pytest


def _load_run_testnet_soak_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_testnet_soak.py"
    spec = importlib.util.spec_from_file_location("run_testnet_soak", script_path)
    assert spec is not None
    assert spec.loader is not None

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    sys.modules.setdefault("dotenv", dotenv)

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_env_requires_testnet_and_internal_tokens():
    module = _load_run_testnet_soak_module()

    results = module.validate_soak_environment(
        {
            "BINANCE_DATA_SOURCE": "mainnet",
            "EXECUTION_MODE": "spot_testnet",
            "ROUTER_EXECUTION_ENV": "testnet",
            "TRADING_MODE": "spot",
            "PIPELINE_HEALTH_ALERTS_ENABLED": "1",
            "LIVE_REST_FALLBACK_ENABLED": "1",
            "SPOT_RECONCILIATION_ENABLED": "true",
            "ROUTER_API_KEY": "router-token",
            "SECURITY_REQUIRED_API_KEY": "router-token",
            "ENGINE_INTERNAL_API_TOKEN": "engine-token",
            "INTERNAL_ALERTS_TOKEN": "alerts-token",
        }
    )

    assert [result.status for result in results] == ["pass", "pass", "pass", "pass"]


def test_validate_env_fails_for_mainnet_execution_and_missing_tokens():
    module = _load_run_testnet_soak_module()

    results = module.validate_soak_environment(
        {
            "BINANCE_DATA_SOURCE": "mainnet",
            "EXECUTION_MODE": "spot_mainnet",
            "ROUTER_EXECUTION_ENV": "mainnet",
            "TRADING_MODE": "spot",
            "PIPELINE_HEALTH_ALERTS_ENABLED": "0",
            "LIVE_REST_FALLBACK_ENABLED": "0",
            "SPOT_RECONCILIATION_ENABLED": "false",
            "ROUTER_API_KEY": "",
            "SECURITY_REQUIRED_API_KEY": "",
            "ENGINE_INTERNAL_API_TOKEN": "",
            "INTERNAL_ALERTS_TOKEN": "",
        }
    )

    failures = [result for result in results if result.status == "fail"]
    assert failures
    assert any("spot_testnet" in result.message for result in failures)
    assert any("ROUTER_EXECUTION_ENV=testnet" in result.message for result in failures)
    assert any("non-empty" in result.message for result in failures)


def test_build_recommendations_uses_failures_and_skips():
    module = _load_run_testnet_soak_module()

    results = [
        module.CheckResult(
            name="env",
            status="fail",
            message="EXECUTION_MODE must remain spot_testnet",
        ),
        module.CheckResult(
            name="order_smoke",
            status="skip",
            message="Order smoke disabled; configure explicit smoke payload",
        ),
        module.CheckResult(
            name="health",
            status="pass",
            message="All health checks passed",
        ),
    ]

    recommendations = module.build_recommendations(results)

    assert recommendations
    assert any("spot_testnet" in recommendation for recommendation in recommendations)
    assert any("order smoke" in recommendation.lower() for recommendation in recommendations)


def test_build_bff_test_environment_removes_ambient_config_keys():
    module = _load_run_testnet_soak_module()

    env = module.build_bff_test_environment(
        {
            "HOST": "0.0.0.0",
            "PORT": "4000",
            "BFF_PORT": "4001",
            "ENGINE_HOST": "1.2.3.4",
            "ENGINE_PORT": "9999",
            "ROUTER_URL": "http://bad-router",
            "SAFE_VAR": "keep-me",
        }
    )

    assert env["SAFE_VAR"] == "keep-me"
    for key in ("HOST", "PORT", "BFF_PORT", "ENGINE_HOST", "ENGINE_PORT", "ROUTER_URL"):
        assert key not in env


def test_build_health_urls_uses_configured_host_ports():
    module = _load_run_testnet_soak_module()

    urls = module.build_health_urls(
        {
            "ENGINE_PORT": "8100",
            "ROUTER_PORT": "8101",
            "BFF_PORT": "3101",
            "UI_PORT": "3100",
        }
    )

    assert urls == {
        "engine": "http://localhost:8100/health/simple",
        "router": "http://localhost:8101/healthz",
        "router_ready": "http://localhost:8101/readyz",
        "bff": "http://localhost:3101/api/health",
        "ui": "http://localhost:3100/api/health",
    }


def _soak_startup_logs() -> str:
    """A minimal combined engine+router log that satisfies every marker."""
    return "\n".join(
        [
            "engine | Execution subscriber enabled: spot_testnet",
            "router | Order Router starting testnet",
            "router | Durable bracket reservations enabled",
            "router | BRACKET_LEGS_ON_FILL enabled: spot exits placed as OCO on entry fill",
            "router | Entry fill watcher started",
            "router | Startup reconciliation complete",
        ]
    )


def test_evaluate_log_signatures_passes_for_full_deferred_legs_stack():
    module = _load_run_testnet_soak_module()

    assert module.evaluate_log_signatures(_soak_startup_logs()) == []


def test_evaluate_log_signatures_flags_missing_deferred_legs_markers():
    module = _load_run_testnet_soak_module()

    # Flag off: no spot-OCO / watcher / reconciler markers
    logs = "\n".join(
        [
            "engine | Execution subscriber enabled: spot_testnet",
            "router | Order Router starting testnet",
        ]
    )
    failures = module.evaluate_log_signatures(logs)

    assert failures == [
        "router did not enable durable bracket reservations",
        "router did not enable spot OCO deferred exits (BRACKET_LEGS_ON_FILL off?)",
        "router did not start the entry-fill watcher",
        "router did not complete a startup reconciliation pass",
    ]


def test_evaluate_log_signatures_flags_forbidden_markers():
    module = _load_run_testnet_soak_module()

    logs = _soak_startup_logs() + "\n".join(
        [
            "",
            "router | Startup reconciliation exhausted retries; serving anyway",
            "router | entry fill watcher: entry filled but no armer; position UNPROTECTED",
        ]
    )
    failures = module.evaluate_log_signatures(logs)

    assert "startup reconciliation failed every attempt — DB or router unhealthy" in failures
    assert "an entry filled with no armer — position left unprotected" in failures


def test_evaluate_log_signatures_can_relax_deferred_legs_requirement():
    module = _load_run_testnet_soak_module()

    logs = "\n".join(
        [
            "engine | Execution subscriber enabled: spot_testnet",
            "router | Order Router starting testnet",
        ]
    )

    assert module.evaluate_log_signatures(logs, require_deferred_legs=False) == []


def test_build_periodic_order_smoke_config_uses_defaults():
    module = _load_run_testnet_soak_module()

    config = module.build_periodic_order_smoke_config({})

    assert config.symbols == ("ETHUSDT", "BTCUSDT")
    assert config.interval_seconds == 3600
    assert config.cancel_after_seconds == 75
    assert config.entry_offset_bps == 150
    assert config.target_notional_usdt == Decimal("25")


def test_build_periodic_order_smoke_config_parses_symbols_and_numbers():
    module = _load_run_testnet_soak_module()

    config = module.build_periodic_order_smoke_config(
        {
            "SOAK_SMOKE_SYMBOLS": " ETHUSDT , BTCUSDT , BNBUSDT ",
            "SOAK_SMOKE_INTERVAL_SECONDS": "1800",
            "SOAK_SMOKE_CANCEL_AFTER_SECONDS": "45",
            "SOAK_SMOKE_ENTRY_OFFSET_BPS": "200",
            "SOAK_SMOKE_TARGET_NOTIONAL_USDT": "35",
        }
    )

    assert config.symbols == ("ETHUSDT", "BTCUSDT", "BNBUSDT")
    assert config.interval_seconds == 1800
    assert config.cancel_after_seconds == 45
    assert config.entry_offset_bps == 200
    assert config.target_notional_usdt == Decimal("35")


def test_build_dynamic_order_smoke_body_for_buy_limit():
    module = _load_run_testnet_soak_module()

    config = module.build_periodic_order_smoke_config(
        {
            "SOAK_SMOKE_SYMBOLS": "ETHUSDT",
            "SOAK_SMOKE_ENTRY_OFFSET_BPS": "150",
            "SOAK_SMOKE_TARGET_NOTIONAL_USDT": "25",
        }
    )

    body = module.build_dynamic_order_smoke_body("ETHUSDT", Decimal("2000"), config)

    assert body == {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "quantity": "0.01269035",
        "take_profit_prices": ["2030.00"],
        "stop_loss_price": "1940.00",
        "is_futures": False,
        "entry_price": "1970.00",
        "order_type": "LIMIT",
    }


def test_monitor_window_runs_periodic_order_smoke_when_due(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )
    monkeypatch.setenv("SOAK_SMOKE_SYMBOLS", "ETHUSDT,BTCUSDT")
    monkeypatch.setenv("SOAK_SMOKE_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("SOAK_SMOKE_CANCEL_AFTER_SECONDS", "1")
    monkeypatch.setenv("SOAK_SMOKE_ENTRY_OFFSET_BPS", "150")
    monkeypatch.setenv("SOAK_SMOKE_TARGET_NOTIONAL_USDT", "25")

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=5,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=True,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)
    runner.periodic_order_smoke_config = module.build_periodic_order_smoke_config(
        dict(module.os.environ)
    )
    runner.next_order_smoke_due = 0.0

    state = {"now": 0.0}

    def fake_monotonic():
        return state["now"]

    def fake_sleep(seconds: float):
        state["now"] += seconds

    calls: list[str] = []

    monkeypatch.setattr(module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "_request_json", lambda *args, **kwargs: (200, "{}"))
    monkeypatch.setattr(runner, "run_order_smoke_cycle", lambda trigger: calls.append(trigger))

    runner.monitor_window()

    assert calls == ["periodic", "periodic", "periodic"]


def test_monitor_window_skips_periodic_order_smoke_before_interval(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=3,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=True,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)
    runner.periodic_order_smoke_config = module.build_periodic_order_smoke_config({})
    runner.next_order_smoke_due = 10.0

    state = {"now": 0.0}

    def fake_monotonic():
        return state["now"]

    def fake_sleep(seconds: float):
        state["now"] += seconds

    calls: list[str] = []

    monkeypatch.setattr(module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "_request_json", lambda *args, **kwargs: (200, "{}"))
    monkeypatch.setattr(runner, "run_order_smoke_cycle", lambda trigger: calls.append(trigger))

    runner.monitor_window()

    assert calls == []


def _make_runner(module, monkeypatch, **overrides):
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )
    defaults = {
        "compose_file": "docker-compose.dev.yml",
        "duration_seconds": 5,
        "poll_interval_seconds": 1,
        "output_dir": tempfile.mkdtemp(),
        "skip_preflight_tests": True,
        "enable_order_smoke": False,
        "keep_running": True,
        "heartbeat_interval_seconds": 60,
    }
    defaults.update(overrides)
    return module.TestnetSoakRunner(argparse.Namespace(**defaults))


def _fake_clock(module, monkeypatch):
    state = {"now": 0.0}
    monkeypatch.setattr(module.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: state.__setitem__("now", state["now"] + seconds)
    )
    return state


@pytest.mark.parametrize(
    ("critical", "expected_status"),
    [(True, "fail"), (False, "warn")],
)
def test_wait_for_http_timeout_status_depends_on_criticality(
    monkeypatch, critical, expected_status
):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch)
    _fake_clock(module, monkeypatch)

    def failing_request(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(runner, "_request_json", failing_request)

    runner._wait_for_http(
        "ui", "http://localhost:3000/api/health", timeout_seconds=4, critical=critical
    )

    result = runner.results[-1]
    assert (result.name, result.status) == ("health:ui", expected_status)
    assert "did not become healthy" in result.message


def test_check_stack_health_passes_when_only_ui_unhealthy(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch)
    _fake_clock(module, monkeypatch)

    ui_url = runner.health_urls["ui"]

    def fake_request_json(url, **kwargs):
        if url == ui_url:
            raise RuntimeError("connection refused")
        return 200, "{}"

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    assert runner.check_stack_health() is True
    statuses = {
        result.name: result.status for result in runner.results if result.name.startswith("health:")
    }
    assert statuses == {
        "health:engine": "pass",
        "health:router": "pass",
        "health:bff": "pass",
        "health:ui": "warn",
        "health:router_ready": "pass",
    }


def test_check_stack_health_fails_when_critical_service_unhealthy(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch)
    _fake_clock(module, monkeypatch)

    bff_url = runner.health_urls["bff"]

    def fake_request_json(url, **kwargs):
        if url == bff_url:
            raise RuntimeError("connection refused")
        return 200, "{}"

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    assert runner.check_stack_health() is False


def test_compose_supports_multiple_files(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(
        module, monkeypatch, compose_file=["docker-compose.dev.yml", "docker-compose.soak.yml"]
    )

    assert runner._compose("up", "-d") == [
        "docker-compose",
        "-f",
        "docker-compose.dev.yml",
        "-f",
        "docker-compose.soak.yml",
        "up",
        "-d",
    ]


def test_compose_accepts_single_string_for_back_compat(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch, compose_file="docker-compose.dev.yml")

    assert runner._compose("logs") == [
        "docker-compose",
        "-f",
        "docker-compose.dev.yml",
        "logs",
    ]


def test_report_overall_status_treats_warn_as_nonblocking(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch)

    runner._record(
        module.CheckResult(name="health:engine", status="pass", message="engine became healthy")
    )
    runner._record(
        module.CheckResult(
            name="health:ui", status="warn", message="ui did not become healthy within timeout"
        )
    )

    payload = runner._build_report_payload(report_type="final", run_state="completed")

    assert payload["overall_status"] == "pass"
    assert payload["warnings"] == 1


def test_report_overall_status_fails_when_any_fail_present(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch)

    runner._record(
        module.CheckResult(
            name="health:engine",
            status="fail",
            message="engine did not become healthy within timeout",
        )
    )
    runner._record(
        module.CheckResult(
            name="health:ui", status="warn", message="ui did not become healthy within timeout"
        )
    )

    payload = runner._build_report_payload(report_type="final", run_state="completed")

    assert payload["overall_status"] == "fail"


def test_build_recommendations_falls_back_to_message_for_unhandled_warn():
    module = _load_run_testnet_soak_module()

    recommendations = module.build_recommendations(
        [
            module.CheckResult(
                name="order_smoke_setup",
                status="warn",
                message="smoke configuration partially degraded",
            )
        ]
    )

    assert "smoke configuration partially degraded" in recommendations


def test_build_recommendations_flags_noncritical_health_warn():
    module = _load_run_testnet_soak_module()

    recommendations = module.build_recommendations(
        [
            module.CheckResult(
                name="health:ui",
                status="warn",
                message="ui did not become healthy within timeout",
            )
        ]
    )

    assert any("soak continued" in recommendation for recommendation in recommendations)


def test_build_recommendations_mentions_periodic_smoke_failures():
    module = _load_run_testnet_soak_module()

    recommendations = module.build_recommendations(
        [
            module.CheckResult(
                name="order_smoke:cycle-2:BTCUSDT",
                status="fail",
                message="Periodic order smoke cancel failed",
            )
        ]
    )

    assert any("order smoke" in recommendation.lower() for recommendation in recommendations)


def test_runner_resolves_relative_output_dir_under_project_root(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=5,
        poll_interval_seconds=1,
        output_dir="artifacts/testnet-soak/relative-check",
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)

    result = runner._run_command(
        "echo_ok",
        [sys.executable, "-c", "print('ok')"],
        cwd=runner.project_root,
    )

    assert result.returncode == 0
    assert result.stdout_path == "artifacts/testnet-soak/relative-check/echo_ok.stdout.log"


def test_run_preflight_tests_uses_project_python_for_engine_pytest(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=5,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=False,
        enable_order_smoke=False,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)

    commands: list[list[str]] = []

    def fake_run_command(name, command, **kwargs):
        commands.append(command)
        return module.CommandResult(
            returncode=0,
            stdout_path=f"{name}.stdout.log",
            stderr_path=f"{name}.stderr.log",
            duration_seconds=0.01,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    assert runner.run_preflight_tests() is True
    assert commands[0][0] == str(
        runner.project_root / "app" / "engine" / ".venv" / "bin" / "python"
    )


def test_request_json_retries_with_unverified_tls_on_cert_error(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=5,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"price":"123.45"}'

    calls: list[dict[str, object]] = []

    def fake_urlopen(request, timeout=0, context=None):
        calls.append(
            {"timeout": timeout, "has_context": context is not None, "url": request.full_url}
        )
        if len(calls) == 1:
            raise URLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    status, body = runner._request_json(
        "https://testnet.binance.vision/api/v3/ticker/price?symbol=ETHUSDT",
        timeout=10,
        allow_insecure_tls=True,
    )

    assert status == 200
    assert body == '{"price":"123.45"}'
    assert calls == [
        {
            "timeout": 10,
            "has_context": False,
            "url": "https://testnet.binance.vision/api/v3/ticker/price?symbol=ETHUSDT",
        },
        {
            "timeout": 10,
            "has_context": True,
            "url": "https://testnet.binance.vision/api/v3/ticker/price?symbol=ETHUSDT",
        },
    ]


def test_run_order_smoke_cycle_cancels_with_resolved_exchange_order_id(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=5,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=True,
        keep_running=True,
    )
    runner = module.TestnetSoakRunner(args)
    runner.periodic_order_smoke_config = module.build_periodic_order_smoke_config(
        {"SOAK_SMOKE_SYMBOLS": "ETHUSDT", "SOAK_SMOKE_CANCEL_AFTER_SECONDS": "1"}
    )

    calls: list[tuple[str, str, object | None]] = []
    state = {"now": 0.0}

    exchange_ids = {"coid-123": 111, "coid-123-tp1": 222, "coid-123-sl": 333}

    def fake_fetch_order(symbol, client_order_id):
        return {"orderId": exchange_ids[client_order_id], "executedQty": "0"}

    def fake_request_json(
        url, *, method="GET", headers=None, body=None, timeout=5, allow_insecure_tls=False
    ):
        calls.append((url, method, body))
        if url.endswith("/place_bracket"):
            return 200, (
                '{"client_order_ids":{"main":"coid-123",'
                '"take_profits":["coid-123-tp1"],"stop_loss":"coid-123-sl"}}'
            )
        if url.endswith("/cancel"):
            return 200, '{"status":"success"}'
        raise AssertionError(url)

    monkeypatch.setattr(runner, "_fetch_reference_price", lambda symbol: Decimal("2000"))
    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    monkeypatch.setattr(runner, "_fetch_order", fake_fetch_order)
    monkeypatch.setattr(module.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: state.__setitem__("now", state["now"] + seconds)
    )

    runner.run_order_smoke_cycle("startup")

    # Every leg must be cancelled — synchronously-placed exits otherwise leak
    # on the shared testnet account until the 5-per-symbol algo cap rejects
    # all placements (run-4 failure). Entry first to close the fill window.
    cancel_calls = [call for call in calls if call[0].endswith("/cancel")]
    assert cancel_calls == [
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 111, "client_order_id": "coid-123"},
        ),
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 222, "client_order_id": "coid-123-tp1"},
        ),
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 333, "client_order_id": "coid-123-sl"},
        ),
    ]
    assert runner.results[-1].status == "pass"


def test_run_order_smoke_cycle_fails_when_exit_leg_cancel_fails(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch, enable_order_smoke=True)
    runner.periodic_order_smoke_config = module.build_periodic_order_smoke_config(
        {"SOAK_SMOKE_SYMBOLS": "ETHUSDT", "SOAK_SMOKE_CANCEL_AFTER_SECONDS": "1"}
    )
    _fake_clock(module, monkeypatch)

    cancelled: list[str] = []

    def fake_request_json(
        url, *, method="GET", headers=None, body=None, timeout=5, allow_insecure_tls=False
    ):
        if url.endswith("/place_bracket"):
            return 200, (
                '{"client_order_ids":{"main":"coid-1",'
                '"take_profits":["coid-1-tp1"],"stop_loss":"coid-1-sl"}}'
            )
        if url.endswith("/cancel"):
            client_order_id = (body or {}).get("client_order_id")
            cancelled.append(client_order_id)
            # The FIRST leg fails: best-effort must still cancel the rest,
            # otherwise the exits keep leaking (the bug being fixed).
            if client_order_id == "coid-1":
                return 400, '{"error":"boom"}'
            return 200, '{"status":"success"}'
        raise AssertionError(url)

    monkeypatch.setattr(runner, "_fetch_reference_price", lambda symbol: Decimal("2000"))
    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    monkeypatch.setattr(
        runner, "_fetch_order", lambda symbol, client_order_id: {"orderId": 42, "executedQty": "0"}
    )

    runner.run_order_smoke_cycle("startup")

    assert cancelled == ["coid-1", "coid-1-tp1", "coid-1-sl"]
    result = runner.results[-1]
    assert result.status == "fail"
    assert result.details["failures"] == [
        {"client_order_id": "coid-1", "status": 400, "body": {"error": "boom"}}
    ]


def test_run_order_smoke_cycle_fails_when_entry_filled_during_window(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _make_runner(module, monkeypatch, enable_order_smoke=True)
    runner.periodic_order_smoke_config = module.build_periodic_order_smoke_config(
        {"SOAK_SMOKE_SYMBOLS": "ETHUSDT", "SOAK_SMOKE_CANCEL_AFTER_SECONDS": "1"}
    )
    _fake_clock(module, monkeypatch)

    def fake_request_json(
        url, *, method="GET", headers=None, body=None, timeout=5, allow_insecure_tls=False
    ):
        if url.endswith("/place_bracket"):
            return 200, (
                '{"client_order_ids":{"main":"coid-9",'
                '"take_profits":["coid-9-tp1"],"stop_loss":"coid-9-sl"}}'
            )
        if url.endswith("/cancel"):
            return 200, '{"status":"success"}'
        raise AssertionError(url)

    def fake_fetch_order(symbol, client_order_id):
        # Final fill check sees a partial fill on the entry
        executed = "0.00500000" if client_order_id == "coid-9" else "0"
        return {"orderId": 7, "executedQty": executed}

    monkeypatch.setattr(runner, "_fetch_reference_price", lambda symbol: Decimal("2000"))
    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    monkeypatch.setattr(runner, "_fetch_order", fake_fetch_order)

    runner.run_order_smoke_cycle("startup")

    result = runner.results[-1]
    assert result.status == "fail"
    assert "filled during the cancel window" in result.message
    assert result.details["executed_qty"] == "0.00500000"


def test_record_writes_partial_report_and_heartbeat(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=30,
        poll_interval_seconds=5,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
        heartbeat_interval_seconds=60,
    )
    runner = module.TestnetSoakRunner(args)

    runner._record(
        module.CheckResult(name="health:engine", status="pass", message="engine became healthy")
    )

    partial_report = module.json.loads(
        (runner.output_dir / "report.partial.json").read_text(encoding="utf-8")
    )
    heartbeat = module.json.loads(
        (runner.output_dir / "heartbeat.json").read_text(encoding="utf-8")
    )

    assert partial_report["report_type"] == "partial"
    assert partial_report["run_state"] == "running"
    assert partial_report["results"][0]["name"] == "health:engine"
    assert heartbeat["run_state"] == "running"
    assert heartbeat["result_count"] == 1


def test_handle_termination_signal_marks_runner_and_writes_partial_report(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=30,
        poll_interval_seconds=5,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
        heartbeat_interval_seconds=60,
    )
    runner = module.TestnetSoakRunner(args)
    runner._record(module.CheckResult(name="compose_up", status="pass", message="stack started"))

    runner._handle_termination_signal(module.signal.SIGTERM, None)

    partial_report = module.json.loads(
        (runner.output_dir / "report.partial.json").read_text(encoding="utf-8")
    )

    assert runner.stop_requested is True
    assert runner.termination_signal == "SIGTERM"
    assert partial_report["run_state"] == "interrupted"
    assert partial_report["termination_signal"] == "SIGTERM"


def test_monitor_window_records_interrupted_status_when_stop_requested(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=30,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
        heartbeat_interval_seconds=5,
    )
    runner = module.TestnetSoakRunner(args)

    state = {"now": 0.0}

    def fake_monotonic():
        return state["now"]

    def fake_sleep(seconds: float):
        state["now"] += seconds
        runner.stop_requested = True
        runner.termination_signal = "SIGTERM"

    monkeypatch.setattr(module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "_request_json", lambda *args, **kwargs: (200, "{}"))

    runner.monitor_window()

    monitor_result = runner.results[-1]
    assert monitor_result.name == "monitor_window"
    assert monitor_result.status == "fail"
    assert "interrupted" in monitor_result.message.lower()
    assert monitor_result.details["termination_signal"] == "SIGTERM"


def test_build_recommendations_deduplicates_identical_entries():
    module = _load_run_testnet_soak_module()
    CheckResult = module.CheckResult

    results = [
        CheckResult(
            name="order_smoke:periodic:1:ETHUSDT", status="fail", message="Order smoke failed"
        ),
        CheckResult(
            name="order_smoke:periodic:2:BTCUSDT", status="fail", message="Order smoke failed"
        ),
        CheckResult(
            name="order_smoke:periodic:3:ETHUSDT", status="fail", message="Order smoke failed"
        ),
    ]

    recommendations = module.build_recommendations(results)

    assert len(recommendations) == 1
    assert "order smoke" in recommendations[0].lower()


def test_build_recommendations_preserves_distinct_entries():
    module = _load_run_testnet_soak_module()
    CheckResult = module.CheckResult

    results = [
        CheckResult(name="execution_mode", status="fail", message="wrong mode"),
        CheckResult(name="internal_auth", status="fail", message="missing tokens"),
    ]

    recommendations = module.build_recommendations(results)

    assert len(recommendations) == 2


def _fetch_order_runner(module, monkeypatch):
    runner = _make_runner(module, monkeypatch)
    monkeypatch.setenv("BINANCE_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    counter = {"now": 1_700_000_000.0}

    def fake_time():
        counter["now"] += 1.0
        return counter["now"]

    monkeypatch.setattr(module.time, "time", fake_time)
    return runner


def test_fetch_order_retries_recv_window_error_with_fresh_timestamp(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _fetch_order_runner(module, monkeypatch)

    urls: list[str] = []

    def fake_request_json(url, **kwargs):
        urls.append(url)
        if len(urls) == 1:
            return (
                400,
                '{"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}',
            )
        return 200, '{"orderId":77,"executedQty":"0"}'

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    order = runner._fetch_order("ETHUSDT", "coid-1")

    assert order["orderId"] == 77
    assert len(urls) == 2
    assert all("recvWindow=10000" in url for url in urls)
    timestamps = [url.split("timestamp=")[1].split("&")[0] for url in urls]
    assert timestamps[0] != timestamps[1]


def test_fetch_order_retries_transient_network_errors(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _fetch_order_runner(module, monkeypatch)

    calls = {"n": 0}

    def fake_request_json(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("timed out")
        return 200, '{"orderId":88,"executedQty":"0"}'

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    assert runner._fetch_order("ETHUSDT", "coid-1")["orderId"] == 88
    assert calls["n"] == 2


def test_fetch_order_fails_fast_on_non_retryable_api_error(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _fetch_order_runner(module, monkeypatch)

    calls = {"n": 0}

    def fake_request_json(url, **kwargs):
        calls["n"] += 1
        return 400, '{"code":-2013,"msg":"Order does not exist."}'

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    with pytest.raises(RuntimeError, match="-2013"):
        runner._fetch_order("ETHUSDT", "coid-1")
    assert calls["n"] == 1


def test_fetch_order_fails_fast_when_rate_limited(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _fetch_order_runner(module, monkeypatch)

    calls = {"n": 0}

    def fake_request_json(url, **kwargs):
        calls["n"] += 1
        return (
            429,
            '{"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}',
        )

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    with pytest.raises(RuntimeError, match="429"):
        runner._fetch_order("ETHUSDT", "coid-1")
    assert calls["n"] == 1


def test_fetch_order_raises_after_exhausting_retries(monkeypatch):
    module = _load_run_testnet_soak_module()
    runner = _fetch_order_runner(module, monkeypatch)

    calls = {"n": 0}

    def fake_request_json(url, **kwargs):
        calls["n"] += 1
        return (
            400,
            '{"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}',
        )

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    with pytest.raises(RuntimeError, match="-1021"):
        runner._fetch_order("ETHUSDT", "coid-1")
    assert calls["n"] == 3
