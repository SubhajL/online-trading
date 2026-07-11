from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

import pytest


def _load_launch_trend_live_paper_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "launch_trend_live_paper.py"
    spec = importlib.util.spec_from_file_location("launch_trend_live_paper", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _isolated_env() -> dict[str, str]:
    return {
        "TREND_LIVE_ENABLED": "1",
        "EXECUTION_MODE": "disabled",
        "ENABLE_PAPER_TRADING": "true",
        "BINANCE_DATA_SOURCE": "mainnet",
        "DATABASE_URL": "postgresql://trading_user:secret@localhost:5433/trend_paper",
        "REDIS_URL": "redis://localhost:6380/0",
        "ROUTER_URL": "http://127.0.0.1:9",
        "TREND_PAPER_ENGINE_PORT": "8016",
    }


def test_parse_env_file_reads_pairs_and_skips_comments():
    module = _load_launch_trend_live_paper_module()
    env_file = Path(tempfile.mkdtemp()) / ".env.trend-paper"
    env_file.write_text(
        "# isolated paper engine\n"
        "\n"
        "TREND_LIVE_ENABLED=1\n"
        "DATABASE_URL='postgresql://u:p@localhost:5433/trend_paper'\n"
        'REDIS_URL="redis://localhost:6380/0"\n',
        encoding="utf-8",
    )

    parsed = module.parse_env_file(env_file)

    assert parsed == {
        "TREND_LIVE_ENABLED": "1",
        "DATABASE_URL": "postgresql://u:p@localhost:5433/trend_paper",
        "REDIS_URL": "redis://localhost:6380/0",
    }


def test_parse_env_file_strips_export_prefix_and_rejects_missing_file():
    module = _load_launch_trend_live_paper_module()
    env_dir = Path(tempfile.mkdtemp())
    env_file = env_dir / ".env.trend-paper"
    env_file.write_text("export TREND_LIVE_ENABLED=1\n", encoding="utf-8")

    assert module.parse_env_file(env_file) == {"TREND_LIVE_ENABLED": "1"}

    with pytest.raises(SystemExit, match="env file"):
        module.parse_env_file(env_dir / "does-not-exist")


def test_build_engine_environment_strips_soak_coupled_vars_and_overlays_file():
    module = _load_launch_trend_live_paper_module()

    parent = {
        "PATH": "/usr/bin",
        "EXECUTION_MODE": "spot_testnet",
        "DATABASE_URL": "postgresql://trading_user:pw@localhost:5432/trading_platform",
        "REDIS_URL": "redis://localhost:6379/0",
        "TELEGRAM_BOT_TOKEN": "tg-secret",
        "TELEGRAM_CHAT_ID": "12345",
        "ROUTER_URL": "http://localhost:8001",
        "ROUTER_API_KEY": "router-secret",
        "BFF_URL": "http://localhost:3001",
        "INTERNAL_ALERTS_TOKEN": "alerts-secret",
        "ENGINE_INTERNAL_API_TOKEN": "engine-secret",
        "BINANCE_API_KEY": "binance-key",
        "BINANCE_SPOT_API_KEY": "spot-key",
        "I_UNDERSTAND_LIVE_TRADING": "1",
        "SIGNAL_EMITTER_SUBSCRIBER_ENABLED": "1",
    }
    file_env = _isolated_env()

    env = module.build_engine_environment(parent, file_env)

    assert env["PATH"] == "/usr/bin"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["EXECUTION_MODE"] == "disabled"
    assert env["DATABASE_URL"] == "postgresql://trading_user:secret@localhost:5433/trend_paper"
    assert env["REDIS_URL"] == "redis://localhost:6380/0"
    # the parent's soak router URL must lose to the file's unroutable pin
    assert env["ROUTER_URL"] == "http://127.0.0.1:9"
    for leaked in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ROUTER_API_KEY",
        "BFF_URL",
        "INTERNAL_ALERTS_TOKEN",
        "ENGINE_INTERNAL_API_TOKEN",
        "BINANCE_API_KEY",
        "BINANCE_SPOT_API_KEY",
        "I_UNDERSTAND_LIVE_TRADING",
        "SIGNAL_EMITTER_SUBSCRIBER_ENABLED",
    ):
        assert leaked not in env


def test_validate_trend_paper_environment_accepts_isolated_profile():
    module = _load_launch_trend_live_paper_module()

    assert module.validate_trend_paper_environment(_isolated_env()) == []


@pytest.mark.parametrize(
    ("overrides", "expected_fragment"),
    [
        ({"TREND_LIVE_ENABLED": "0"}, "TREND_LIVE_ENABLED"),
        ({"EXECUTION_MODE": "spot_testnet"}, "EXECUTION_MODE"),
        ({"ENABLE_PAPER_TRADING": "false"}, "ENABLE_PAPER_TRADING"),
        ({"BINANCE_DATA_SOURCE": "testnet"}, "BINANCE_DATA_SOURCE"),
        (
            {"DATABASE_URL": "postgresql://trading_user:pw@localhost:5432/trading_platform"},
            "DATABASE_URL",
        ),
        ({"DATABASE_URL": "mysql://u:p@localhost:5433/trend_paper"}, "DATABASE_URL"),
        # Portless URLs default to 5432/6379 at runtime — the soak DB and redis
        ({"DATABASE_URL": "postgresql://u:p@localhost/trend_paper"}, "DATABASE_URL"),
        ({"REDIS_URL": "redis://localhost/0"}, "REDIS_URL"),
        ({"DATABASE_URL": "postgresql://u:p@localhost:banana/trend_paper"}, "DATABASE_URL"),
        ({"REDIS_URL": "redis://localhost:6379/0"}, "REDIS_URL"),
        ({"ROUTER_URL": ""}, "ROUTER_URL"),
        ({"ROUTER_URL": "http://localhost:8001"}, "ROUTER_URL"),
        ({"TREND_PAPER_ENGINE_PORT": "8000"}, "TREND_PAPER_ENGINE_PORT"),
        ({"TREND_PAPER_ENGINE_PORT": "not-a-port"}, "TREND_PAPER_ENGINE_PORT"),
        ({"TELEGRAM_BOT_TOKEN": "tg-secret"}, "TELEGRAM_BOT_TOKEN"),
        ({"BFF_URL": "http://localhost:3001"}, "BFF_URL"),
        ({"ROUTER_API_KEY": "router-secret"}, "ROUTER_API_KEY"),
    ],
)
def test_validate_trend_paper_environment_rejects_soak_collisions(overrides, expected_fragment):
    module = _load_launch_trend_live_paper_module()
    env = _isolated_env()
    env.update(overrides)

    failures = module.validate_trend_paper_environment(env)

    assert any(expected_fragment in failure for failure in failures)


def test_build_engine_command_uses_project_python_without_reload():
    module = _load_launch_trend_live_paper_module()
    project_root = Path(tempfile.mkdtemp())
    project_python = project_root / "app" / "engine" / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True, exist_ok=True)
    project_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    command = module.build_engine_command(project_root, port=8010)

    assert command == [
        str(project_python),
        "-m",
        "uvicorn",
        "app.engine.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
    ]
    assert "--reload" not in command


def test_build_migrate_command_targets_engine_migration_script():
    module = _load_launch_trend_live_paper_module()
    project_root = Path(tempfile.mkdtemp())

    command = module.build_migrate_command(project_root)

    assert command == [sys.executable, "app/engine/scripts/migrate_db.py"]


def test_wait_for_engine_health_returns_when_health_endpoint_answers(monkeypatch):
    module = _load_launch_trend_live_paper_module()

    class AliveProcess:
        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("healthy engine must not be terminated")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    urls: list[str] = []

    def fake_urlopen(url, timeout=0):
        urls.append(url)
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    module.wait_for_engine_health(port=8016, process=AliveProcess(), timeout_seconds=5)

    assert urls == ["http://127.0.0.1:8016/health/simple"]


def test_wait_for_engine_health_fails_when_process_dies(monkeypatch):
    module = _load_launch_trend_live_paper_module()

    class DeadProcess:
        def poll(self):
            return 3

        def terminate(self):
            raise AssertionError("dead process needs no terminate")

    with pytest.raises(SystemExit, match="exited"):
        module.wait_for_engine_health(port=8016, process=DeadProcess(), timeout_seconds=5)


def test_wait_for_engine_health_terminates_and_fails_on_timeout(monkeypatch):
    module = _load_launch_trend_live_paper_module()

    terminated: list[bool] = []

    class HangingProcess:
        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)

    def fake_urlopen(url, timeout=0):
        raise OSError("connection refused")

    clock = {"now": 0.0}
    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock["now"])

    def fake_sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr(module.time, "sleep", fake_sleep)

    with pytest.raises(SystemExit, match="did not become healthy"):
        module.wait_for_engine_health(port=8016, process=HangingProcess(), timeout_seconds=5)

    assert terminated == [True]


def test_launch_detached_engine_migrates_then_starts_with_sanitized_env(monkeypatch):
    module = _load_launch_trend_live_paper_module()
    monkeypatch.setattr(sys, "platform", "darwin")

    temp_root = Path(tempfile.mkdtemp())
    env_file = temp_root / ".env.trend-paper"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in _isolated_env().items()),
        encoding="utf-8",
    )
    run_dir = temp_root / "artifacts" / "trend-paper" / "manual-test"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-secret")
    monkeypatch.setenv("EXECUTION_MODE", "spot_testnet")

    args = argparse.Namespace(
        env_file=str(env_file),
        output_dir=str(run_dir),
        skip_migrate=False,
    )

    class FakeCompleted:
        returncode = 0
        stdout = "migrations ok"
        stderr = ""

    run_calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        run_calls.append({"command": command, **kwargs})
        return FakeCompleted()

    class FakeProcess:
        pid = 54321

    popen_calls: list[dict[str, object]] = []

    def fake_popen(command, **kwargs):
        popen_calls.append({"command": command, **kwargs})
        return FakeProcess()

    port_probes: list[int] = []
    health_waits: list[tuple[int, object, int]] = []

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module, "ensure_port_available", lambda port: port_probes.append(port))
    monkeypatch.setattr(
        module,
        "wait_for_engine_health",
        lambda *, port, process, timeout_seconds: health_waits.append(
            (port, process, timeout_seconds)
        ),
    )

    metadata = module.launch_detached_engine(args, project_root=temp_root)

    assert len(run_calls) == 1
    assert run_calls[0]["command"][-1] == "app/engine/scripts/migrate_db.py"
    assert run_calls[0]["env"]["DATABASE_URL"].endswith(":5433/trend_paper")

    assert port_probes == [8016]
    assert len(popen_calls) == 1
    assert popen_calls[0]["command"][:3] == ["caffeinate", "-i", "--"]
    assert popen_calls[0]["start_new_session"] is True
    assert popen_calls[0]["cwd"] == str(temp_root)
    engine_env = popen_calls[0]["env"]
    assert engine_env["EXECUTION_MODE"] == "disabled"
    assert "TELEGRAM_BOT_TOKEN" not in engine_env

    assert len(health_waits) == 1
    assert health_waits[0][0] == 8016

    assert metadata["pid"] == 54321
    assert metadata["port"] == 8016
    launcher = json.loads((run_dir / "launcher.json").read_text(encoding="utf-8"))
    assert launcher["pid"] == 54321
    assert launcher["command"] == popen_calls[0]["command"]
    assert (run_dir / "engine.log").exists()


def test_launch_detached_engine_refuses_invalid_environment(monkeypatch):
    module = _load_launch_trend_live_paper_module()

    temp_root = Path(tempfile.mkdtemp())
    env_file = temp_root / ".env.trend-paper"
    bad_env = _isolated_env()
    bad_env["EXECUTION_MODE"] = "spot_testnet"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in bad_env.items()),
        encoding="utf-8",
    )

    args = argparse.Namespace(
        env_file=str(env_file),
        output_dir=str(temp_root / "run"),
        skip_migrate=True,
    )

    with pytest.raises(SystemExit):
        module.launch_detached_engine(args, project_root=temp_root)
