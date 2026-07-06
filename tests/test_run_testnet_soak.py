from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
from urllib.error import URLError


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
        "bff": "http://localhost:3101/api/health",
        "ui": "http://localhost:3100/api/health",
    }


def test_build_periodic_order_smoke_config_uses_defaults():
    module = _load_run_testnet_soak_module()

    config = module.build_periodic_order_smoke_config({})

    assert config.symbols == ("ETHUSDT", "BTCUSDT")
    assert config.interval_seconds == 3600
    assert config.cancel_after_seconds == 10
    assert config.entry_offset_bps == 500
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

    def fake_request_json(
        url, *, method="GET", headers=None, body=None, timeout=5, allow_insecure_tls=False
    ):
        calls.append((url, method, body))
        if url.endswith("/place_bracket"):
            return (
                200,
                '{"client_order_ids":{"main":"coid-123","take_profits":["coid-tp1"],"stop_loss":"coid-sl"}}',
            )
        if url.endswith("/cancel"):
            return 200, '{"status":"success"}'
        raise AssertionError(url)

    monkeypatch.setattr(runner, "_fetch_reference_price", lambda symbol: Decimal("2000"))
    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    monkeypatch.setattr(
        runner,
        "_fetch_exchange_order",
        lambda symbol, client_order_id: {
            "coid-123": {"orderId": 987654321, "status": "NEW"},
            "coid-tp1": {"orderId": 987654322, "status": "NEW"},
            "coid-sl": {"orderId": 987654323, "status": "NEW"},
        }[client_order_id],
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: state.__setitem__("now", state["now"] + seconds)
    )

    runner.run_order_smoke_cycle("startup")

    cancel_calls = [call for call in calls if call[0].endswith("/cancel")]
    assert cancel_calls == [
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 987654321, "client_order_id": "coid-123"},
        ),
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 987654322, "client_order_id": "coid-tp1"},
        ),
        (
            "http://localhost:8001/cancel",
            "POST",
            {"symbol": "ETHUSDT", "order_id": 987654323, "client_order_id": "coid-sl"},
        ),
    ]


def test_run_order_smoke_cycle_fails_clearly_when_main_order_fills_before_cancel(monkeypatch):
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

    def fake_request_json(
        url, *, method="GET", headers=None, body=None, timeout=5, allow_insecure_tls=False
    ):
        calls.append((url, method, body))
        if url.endswith("/place_bracket"):
            return 200, '{"client_order_ids":{"main":"coid-123"}}'
        if url.endswith("/cancel"):
            raise AssertionError("cancel should not be attempted after a terminal fill")
        raise AssertionError(url)

    monkeypatch.setattr(runner, "_fetch_reference_price", lambda symbol: Decimal("2000"))
    monkeypatch.setattr(runner, "_request_json", fake_request_json)
    monkeypatch.setattr(
        runner,
        "_fetch_exchange_order",
        lambda symbol, client_order_id: {
            "orderId": 987654321,
            "status": "FILLED",
            "executedQty": "0.01200000",
        },
    )
    monkeypatch.setattr(module.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: state.__setitem__("now", state["now"] + seconds)
    )

    runner.run_order_smoke_cycle("startup")

    order_result = next(result for result in runner.results if result.name.startswith("order_smoke"))
    assert order_result.status == "fail"
    assert order_result.message == "Order smoke main order filled before cancel window elapsed"
    assert order_result.details["exchange_order_status"] == "FILLED"
    assert order_result.details["executed_qty"] == "0.01200000"


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


def test_write_report_finalizes_runtime_artifacts(monkeypatch):
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

    report = runner.write_report()
    partial_report = module.json.loads(
        (runner.output_dir / "report.partial.json").read_text(encoding="utf-8")
    )
    heartbeat = module.json.loads(
        (runner.output_dir / "heartbeat.json").read_text(encoding="utf-8")
    )

    assert report["report_type"] == "final"
    assert report["run_state"] == "completed"
    assert report["completed_at"] is not None
    assert partial_report["run_state"] == "completed"
    assert partial_report["completed_at"] is not None
    assert heartbeat["run_state"] == "completed"
    assert heartbeat["completed_at"] is not None


def test_record_after_final_report_preserves_terminal_runtime_state(monkeypatch):
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
    runner.write_report()

    runner._record(module.CheckResult(name="shutdown", status="skip", message="left running"))

    partial_report = module.json.loads(
        (runner.output_dir / "report.partial.json").read_text(encoding="utf-8")
    )
    heartbeat = module.json.loads(
        (runner.output_dir / "heartbeat.json").read_text(encoding="utf-8")
    )

    assert partial_report["run_state"] == "completed"
    assert heartbeat["run_state"] == "completed"


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


def test_assert_log_signatures_scopes_logs_to_run_start(monkeypatch):
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
    commands: list[list[str]] = []

    def fake_run_command(name, command, **kwargs):
        commands.append(command)
        stdout_path = runner.output_dir / f"{name}.stdout.log"
        stdout_path.write_text(
            "Execution subscriber enabled: spot_testnet\nOrder Router starting in testnet mode\n",
            encoding="utf-8",
        )
        stderr_path = runner.output_dir / f"{name}.stderr.log"
        stderr_path.write_text("", encoding="utf-8")
        return module.CommandResult(
            returncode=0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            duration_seconds=0.01,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    assert runner.assert_log_signatures() is True
    assert "--since" in commands[0]
    assert runner.started_at.isoformat() in commands[0]


def test_assert_log_signatures_skips_missing_markers_when_services_not_restarted(monkeypatch):
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
    compose_up_stdout = runner.output_dir / "compose_up.stdout.log"
    compose_up_stdout.write_text("", encoding="utf-8")
    compose_up_stderr = runner.output_dir / "compose_up.stderr.log"
    compose_up_stderr.write_text(
        "\n".join(
            [
                " Container trading-engine-dev  Running",
                " Container trading-router-dev  Running",
            ]
        ),
        encoding="utf-8",
    )
    runner._record(
        module.CheckResult(
            name="compose_up",
            status="pass",
            message="stack started",
            artifacts=[str(compose_up_stdout), str(compose_up_stderr)],
        )
    )

    def fake_run_command(name, command, **kwargs):
        stdout_path = runner.output_dir / f"{name}.stdout.log"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path = runner.output_dir / f"{name}.stderr.log"
        stderr_path.write_text("", encoding="utf-8")
        return module.CommandResult(
            returncode=0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            duration_seconds=0.01,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    assert runner.assert_log_signatures() is True
    assert runner.results[-1].name == "log_assertions"
    assert runner.results[-1].status == "skip"


def test_collect_compose_logs_scopes_to_run_start(monkeypatch):
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
    commands: list[list[str]] = []

    def fake_run_command(name, command, **kwargs):
        commands.append(command)
        stdout_path = runner.output_dir / f"{name}.stdout.log"
        stdout_path.write_text("", encoding="utf-8")
        stderr_path = runner.output_dir / f"{name}.stderr.log"
        stderr_path.write_text("", encoding="utf-8")
        return module.CommandResult(
            returncode=0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            duration_seconds=0.01,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    runner.collect_compose_logs()

    assert "--since" in commands[0]
    assert runner.started_at.isoformat() in commands[0]


def test_collect_compose_logs_records_critical_runtime_incidents(monkeypatch):
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

    def fake_run_command(name, command, **kwargs):
        stdout_path = runner.output_dir / f"{name}.stdout.log"
        stdout_path.write_text(
            "\n".join(
                [
                    'app.engine.adapters.alert.bff_api_client - ERROR - BffApiClient POST /api/signals/alert failed: 401 {"message":"Unauthorized","statusCode":401}',
                    "app.engine.adapters.db.timescale_adapter - ERROR - Error upserting order: client_order_id=abc123",
                    "router - ERR Failed to persist bracket intent",
                ]
            ),
            encoding="utf-8",
        )
        stderr_path = runner.output_dir / f"{name}.stderr.log"
        stderr_path.write_text("", encoding="utf-8")
        return module.CommandResult(
            returncode=0,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            duration_seconds=0.01,
        )

    monkeypatch.setattr(runner, "_run_command", fake_run_command)

    runner.collect_compose_logs()

    runtime_result = runner.results[-1]
    assert runtime_result.name == "runtime_incidents"
    assert runtime_result.status == "fail"
    assert runtime_result.details["incident_count"] == 3
    assert {incident["key"] for incident in runtime_result.details["incidents"]} == {
        "alert_auth_401",
        "engine_order_persistence",
        "router_bracket_intent_persistence",
    }


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


def test_monitor_window_records_health_probe_failure_before_summary(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=2,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
        heartbeat_interval_seconds=5,
        critical_health_failure_threshold=2,
    )
    runner = module.TestnetSoakRunner(args)

    state = {"now": 0.0}

    def fake_monotonic():
        return state["now"]

    def fake_sleep(seconds: float):
        state["now"] += seconds

    def fake_request_json(url, **kwargs):
        if url == runner.health_urls["bff"]:
            raise URLError("connection refused")
        return 200, "{}"

    monkeypatch.setattr(module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    runner.monitor_window()

    assert runner.results[0].name == "health:bff"
    assert runner.results[0].status == "fail"
    assert runner.results[0].details["consecutive_failures"] == 1
    assert runner.results[-1].name == "monitor_window"
    assert runner.results[-1].status == "fail"


def test_run_fails_and_writes_final_report_when_wall_clock_budget_exceeded(monkeypatch):
    module = _load_run_testnet_soak_module()
    monkeypatch.setattr(
        module.TestnetSoakRunner, "_resolve_compose_command", lambda self: ["docker-compose"]
    )

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=1,
        poll_interval_seconds=1,
        output_dir=tempfile.mkdtemp(),
        skip_preflight_tests=True,
        enable_order_smoke=False,
        keep_running=True,
        heartbeat_interval_seconds=5,
    )
    runner = module.TestnetSoakRunner(args)
    runner.started_at = module.datetime.now(module.UTC) - timedelta(seconds=10)

    state = {"now": 0.0}

    def fake_monotonic():
        return state["now"]

    def fake_sleep(seconds: float):
        state["now"] += seconds

    monkeypatch.setattr(module.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(runner, "_request_json", lambda *args, **kwargs: (200, "{}"))
    monkeypatch.setattr(runner, "validate_environment", lambda: True)
    monkeypatch.setattr(runner, "start_stack", lambda: True)
    monkeypatch.setattr(runner, "check_stack_health", lambda: True)
    monkeypatch.setattr(runner, "assert_log_signatures", lambda: True)
    monkeypatch.setattr(runner, "maybe_run_order_smoke", lambda: None)
    monkeypatch.setattr(runner, "collect_compose_logs", lambda: None)
    monkeypatch.setattr(runner, "maybe_shutdown", lambda: None)

    report = runner.run()

    assert report["overall_status"] == "fail"
    assert report["run_state"] == "completed"
    assert any(
        result["name"] == "monitor_window" and "wall-clock" in result["message"].lower()
        for result in report["results"]
    )
    assert runner.report_path.exists()


def test_build_recommendations_deduplicates_identical_entries():
    module = _load_run_testnet_soak_module()
    CheckResult = module.CheckResult

    results = [
        CheckResult(name="order_smoke:periodic:1:ETHUSDT", status="fail", message="Order smoke failed"),
        CheckResult(name="order_smoke:periodic:2:BTCUSDT", status="fail", message="Order smoke failed"),
        CheckResult(name="order_smoke:periodic:3:ETHUSDT", status="fail", message="Order smoke failed"),
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
