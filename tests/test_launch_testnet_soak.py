from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types


def _load_launch_testnet_soak_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "launch_testnet_soak.py"
    spec = importlib.util.spec_from_file_location("launch_testnet_soak", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_runner_command_enables_requested_flags():
    module = _load_launch_testnet_soak_module()
    project_root = Path(tempfile.mkdtemp())
    project_python = project_root / "app" / "engine" / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True, exist_ok=True)
    project_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=86400,
        poll_interval_seconds=15,
        enable_order_smoke=True,
        skip_preflight_tests=False,
        keep_running=True,
        heartbeat_interval_seconds=120,
    )

    command = module.build_runner_command(
        args,
        Path("/tmp/run-dir"),
        project_root=project_root,
    )

    assert command == [
        str(project_python),
        "scripts/run_testnet_soak.py",
        "--compose-file",
        "docker-compose.dev.yml",
        "--duration-seconds",
        "86400",
        "--poll-interval-seconds",
        "15",
        "--heartbeat-interval-seconds",
        "120",
        "--output-dir",
        "/tmp/run-dir",
        "--enable-order-smoke",
        "--keep-running",
    ]


def test_build_runner_command_repeats_compose_file_for_each_entry():
    module = _load_launch_testnet_soak_module()

    args = argparse.Namespace(
        compose_file=["docker-compose.dev.yml", "docker-compose.soak.yml"],
        duration_seconds=86400,
        poll_interval_seconds=15,
        enable_order_smoke=False,
        skip_preflight_tests=False,
        keep_running=False,
        heartbeat_interval_seconds=120,
    )

    command = module.build_runner_command(
        args,
        Path("/tmp/run-dir"),
        project_root=Path("/repo-without-venv"),
    )

    dev_index = command.index("docker-compose.dev.yml")
    assert command[dev_index - 1] == "--compose-file"
    soak_index = command.index("docker-compose.soak.yml")
    assert command[soak_index - 1] == "--compose-file"
    # -f order determines override precedence: dev first, soak override second
    assert dev_index < soak_index


def test_build_runner_command_defaults_to_dev_plus_soak_override():
    module = _load_launch_testnet_soak_module()

    args = argparse.Namespace(
        compose_file=None,
        duration_seconds=86400,
        poll_interval_seconds=15,
        enable_order_smoke=False,
        skip_preflight_tests=False,
        keep_running=False,
        heartbeat_interval_seconds=120,
    )

    command = module.build_runner_command(
        args,
        Path("/tmp/run-dir"),
        project_root=Path("/repo-without-venv"),
    )

    dev_index = command.index("docker-compose.dev.yml")
    soak_index = command.index("docker-compose.soak.yml")
    assert dev_index < soak_index


def test_launch_detached_soak_writes_launcher_metadata(monkeypatch):
    module = _load_launch_testnet_soak_module()

    temp_root = Path(tempfile.mkdtemp())
    run_dir = temp_root / "artifacts" / "testnet-soak" / "manual-test"
    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=86400,
        poll_interval_seconds=15,
        enable_order_smoke=True,
        skip_preflight_tests=False,
        keep_running=True,
        heartbeat_interval_seconds=120,
        output_dir=str(run_dir),
    )

    class FakeProcess:
        pid = 43210

    popen_calls: list[dict[str, object]] = []

    def fake_popen(command, **kwargs):
        popen_calls.append({"command": command, **kwargs})
        return FakeProcess()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    metadata = module.launch_detached_soak(args, project_root=temp_root)

    launcher_path = run_dir / "launcher.json"
    session_log = run_dir / "session.log"

    assert launcher_path.exists()
    assert session_log.exists()
    assert metadata["pid"] == 43210
    assert metadata["run_dir"] == str(run_dir)
    assert metadata["session_log"] == str(session_log)

    written = json.loads(launcher_path.read_text(encoding="utf-8"))
    assert written["pid"] == 43210
    assert written["command"] == popen_calls[0]["command"]
    assert popen_calls[0]["cwd"] == str(temp_root)
    assert popen_calls[0]["start_new_session"] is True


def test_build_runner_command_falls_back_to_sys_executable_without_project_venv(monkeypatch):
    module = _load_launch_testnet_soak_module()
    monkeypatch.setattr(sys, "executable", "/ambient/python3")

    args = argparse.Namespace(
        compose_file="docker-compose.dev.yml",
        duration_seconds=86400,
        poll_interval_seconds=15,
        enable_order_smoke=False,
        skip_preflight_tests=False,
        keep_running=False,
        heartbeat_interval_seconds=120,
    )

    command = module.build_runner_command(
        args,
        Path("/tmp/run-dir"),
        project_root=Path("/repo-without-venv"),
    )

    assert command[0] == "/ambient/python3"


def test_wrap_with_caffeinate_on_darwin(monkeypatch):
    module = _load_launch_testnet_soak_module()
    monkeypatch.setattr(sys, "platform", "darwin")

    cmd = ["/usr/bin/python3", "scripts/run_testnet_soak.py"]
    wrapped = module.wrap_with_caffeinate(cmd)

    assert wrapped[:3] == ["caffeinate", "-i", "--"]
    assert wrapped[3:] == cmd


def test_wrap_with_caffeinate_skips_on_linux(monkeypatch):
    module = _load_launch_testnet_soak_module()
    monkeypatch.setattr(sys, "platform", "linux")

    cmd = ["/usr/bin/python3", "scripts/run_testnet_soak.py"]
    wrapped = module.wrap_with_caffeinate(cmd)

    assert wrapped == cmd
