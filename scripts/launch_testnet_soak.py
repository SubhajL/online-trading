#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


def build_run_directory(project_root: Path, output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir)
        return path if path.is_absolute() else project_root / path
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return project_root / "artifacts" / "testnet-soak" / f"manual-{timestamp}"


def wrap_with_caffeinate(command: list[str]) -> list[str]:
    if sys.platform == "darwin":
        return ["caffeinate", "-i", "--"] + command
    return command


def resolve_project_python(project_root: Path) -> str:
    project_python = project_root / "app" / "engine" / ".venv" / "bin" / "python"
    return str(project_python) if project_python.exists() else sys.executable


def build_runner_command(
    args: argparse.Namespace,
    run_dir: Path,
    *,
    project_root: Path,
) -> list[str]:
    command = [
        resolve_project_python(project_root),
        "scripts/run_testnet_soak.py",
        "--compose-file",
        args.compose_file,
        "--duration-seconds",
        str(args.duration_seconds),
        "--poll-interval-seconds",
        str(args.poll_interval_seconds),
        "--heartbeat-interval-seconds",
        str(args.heartbeat_interval_seconds),
        "--output-dir",
        str(run_dir),
    ]
    if args.enable_order_smoke:
        command.append("--enable-order-smoke")
    if args.skip_preflight_tests:
        command.append("--skip-preflight-tests")
    if args.keep_running:
        command.append("--keep-running")
    return command


def launch_detached_soak(
    args: argparse.Namespace, *, project_root: Path | None = None
) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    run_dir = build_run_directory(root, getattr(args, "output_dir", None))
    run_dir.mkdir(parents=True, exist_ok=True)
    session_log = run_dir / "session.log"
    launcher_path = run_dir / "launcher.json"
    command = build_runner_command(args, run_dir, project_root=root)
    command = wrap_with_caffeinate(command)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    with session_log.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    metadata = {
        "pid": process.pid,
        "launched_at": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "session_log": str(session_log),
        "command": command,
    }
    launcher_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the testnet soak runner as a detached background process."
    )
    parser.add_argument("--compose-file", default="docker-compose.dev.yml")
    parser.add_argument("--duration-seconds", type=int, default=86400)
    parser.add_argument("--poll-interval-seconds", type=int, default=15)
    parser.add_argument("--heartbeat-interval-seconds", type=int, default=60)
    parser.add_argument("--output-dir")
    parser.add_argument("--enable-order-smoke", action="store_true")
    parser.add_argument("--skip-preflight-tests", action="store_true")
    parser.add_argument("--keep-running", action="store_true")
    return parser.parse_args()


def main() -> int:
    metadata = launch_detached_soak(parse_args())
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
