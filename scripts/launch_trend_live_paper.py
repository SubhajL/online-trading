#!/usr/bin/env python3
"""Launch the trend-live paper engine isolated from the shared .env and the soak stack.

The shared .env drives the testnet soak (spot_testnet execution, router,
Telegram, host ports 8000/8001/3001/5432/6379). This launcher builds the
engine environment exclusively from an isolated env file, refuses any
configuration that could collide with the soak or reach live execution or
alert channels, runs migrations against the dedicated database, and starts
uvicorn detached (no --reload) so the paper run survives the terminal.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any
import urllib.parse
from urllib.request import urlopen

# Never inherited from the parent shell: anything that could point the paper
# engine at the soak stack, live execution, alert channels, or exchange keys.
INHERITED_ENV_DENYLIST = (
    "EXECUTION_MODE",
    "I_UNDERSTAND_LIVE_TRADING",
    "SIGNAL_EMITTER_SUBSCRIBER_ENABLED",
    "DATABASE_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "REDIS_URL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_PASSWORD",
    "ROUTER_URL",
    "ROUTER_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "BFF_URL",
    "INTERNAL_ALERTS_TOKEN",
    "ENGINE_INTERNAL_API_TOKEN",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_SECRET_KEY",
    "BINANCE_SPOT_API_KEY",
    "BINANCE_SPOT_SECRET_KEY",
    "BINANCE_FUTURES_API_KEY",
    "BINANCE_FUTURES_SECRET_KEY",
)

# Host ports owned by the soak dev-compose stack (plus homebrew PG on 5432).
SOAK_RESERVED_PORTS = frozenset({3000, 3001, 5432, 6379, 8000, 8001, 8002})

# Set in the env file only if you intend to break isolation on purpose.
FORBIDDEN_ENV_KEYS = ("TELEGRAM_BOT_TOKEN", "BFF_URL", "ROUTER_API_KEY")

# 8010 is squatted by an unrelated container on this host; 8016 is free.
DEFAULT_ENGINE_PORT = 8016

ENGINE_HEALTH_TIMEOUT_SECONDS = 90


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"env file not found: {path} (copy the template from the runbook)")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def build_engine_environment(
    parent_env: dict[str, str], file_env: dict[str, str]
) -> dict[str, str]:
    env = {key: value for key, value in parent_env.items() if key not in INHERITED_ENV_DENYLIST}
    env.update(file_env)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _validate_url_port(
    env: dict[str, str],
    key: str,
    *,
    schemes: set[str],
    failures: list[str],
) -> None:
    raw = env.get(key, "").strip()
    if not raw:
        failures.append(f"{key} must be set to the dedicated trend-paper instance")
        return
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in schemes:
        failures.append(f"{key} must use one of {sorted(schemes)}, got {parsed.scheme!r}")
        return
    try:
        port = parsed.port
    except ValueError:
        failures.append(f"{key} has an invalid port")
        return
    # A missing port silently defaults to the soak's 5432/6379 at runtime.
    if port is None:
        failures.append(f"{key} must specify an explicit port")
        return
    if port in SOAK_RESERVED_PORTS:
        failures.append(
            f"{key} points at port {port}, which the soak stack owns — "
            "use the dedicated trend-paper instance"
        )


def validate_trend_paper_environment(env: dict[str, str]) -> list[str]:
    failures: list[str] = []

    if env.get("TREND_LIVE_ENABLED", "").strip() != "1":
        failures.append("TREND_LIVE_ENABLED must be 1 — this launcher exists to run trend paper")
    if env.get("EXECUTION_MODE", "").strip().lower() != "disabled":
        failures.append(
            "EXECUTION_MODE must be disabled so the paper engine can never reach the soak router"
        )
    if env.get("ENABLE_PAPER_TRADING", "").strip().lower() not in {"1", "true", "yes", "on"}:
        failures.append(
            "ENABLE_PAPER_TRADING must be true so equity sampling stays in-DB (no router polling)"
        )
    if env.get("BINANCE_DATA_SOURCE", "").strip().lower() != "mainnet":
        failures.append(
            "BINANCE_DATA_SOURCE must be mainnet — OOS evidence must match the backtest data"
        )

    _validate_url_port(env, "DATABASE_URL", schemes={"postgresql", "postgres"}, failures=failures)
    _validate_url_port(env, "REDIS_URL", schemes={"redis", "rediss"}, failures=failures)
    # The engine builds a RouterHTTPClient unconditionally and its /health and
    # /metrics endpoints probe it; ROUTER_URL defaults to the soak router on
    # 8001, so it must be pinned to an unroutable address (e.g. 127.0.0.1:9).
    _validate_url_port(env, "ROUTER_URL", schemes={"http", "https"}, failures=failures)

    raw_port = env.get("TREND_PAPER_ENGINE_PORT", str(DEFAULT_ENGINE_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        failures.append(f"TREND_PAPER_ENGINE_PORT must be an integer, got {raw_port!r}")
    else:
        if port in SOAK_RESERVED_PORTS:
            failures.append(
                f"TREND_PAPER_ENGINE_PORT {port} collides with a soak-owned port; pick another"
            )

    for key in FORBIDDEN_ENV_KEYS:
        if env.get(key, "").strip():
            failures.append(f"{key} must stay unset for the isolated paper engine")

    return failures


def resolve_project_python(project_root: Path) -> str:
    project_python = project_root / "app" / "engine" / ".venv" / "bin" / "python"
    return str(project_python) if project_python.exists() else sys.executable


def build_engine_command(project_root: Path, *, port: int) -> list[str]:
    return [
        resolve_project_python(project_root),
        "-m",
        "uvicorn",
        "app.engine.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def build_migrate_command(project_root: Path) -> list[str]:
    return [resolve_project_python(project_root), "app/engine/scripts/migrate_db.py"]


def wrap_with_caffeinate(command: list[str]) -> list[str]:
    if sys.platform == "darwin":
        return ["caffeinate", "-i", "--", *command]
    return command


def ensure_port_available(port: int) -> None:
    # Probe the wildcard address too: docker-proxy squats bind 0.0.0.0 and a
    # loopback-only bind would "succeed" while external traffic reaches the
    # other process.
    for host in ("0.0.0.0", "127.0.0.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind((host, port))
        except OSError as exc:
            raise SystemExit(
                f"engine port {port} is already in use ({host}): {exc}; "
                "set TREND_PAPER_ENGINE_PORT to a free port"
            ) from exc


def wait_for_engine_health(*, port: int, process: Any, timeout_seconds: int) -> None:
    url = f"http://127.0.0.1:{port}/health/simple"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise SystemExit(f"engine exited during startup (code {exit_code}); see engine.log")
        try:
            with urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return
        except OSError:
            pass
        time.sleep(1)

    process.terminate()
    raise SystemExit(
        f"engine did not become healthy within {timeout_seconds}s; terminated — see engine.log"
    )


def build_run_directory(project_root: Path, output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir)
        return path if path.is_absolute() else project_root / path
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return project_root / "artifacts" / "trend-paper" / f"manual-{timestamp}"


def launch_detached_engine(
    args: argparse.Namespace, *, project_root: Path | None = None
) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = root / env_file
    file_env = parse_env_file(env_file)
    env = build_engine_environment(dict(os.environ), file_env)
    # migrate_db.py imports app.engine.*; script-by-path execution does not
    # put the repo root on sys.path.
    inherited_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root}:{inherited_pythonpath}" if inherited_pythonpath else str(root)

    failures = validate_trend_paper_environment(env)
    if failures:
        raise SystemExit(
            "Refusing to launch the trend paper engine:\n"
            + "\n".join(f"  - {failure}" for failure in failures)
        )

    run_dir = build_run_directory(root, getattr(args, "output_dir", None))
    run_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_migrate:
        migrate = subprocess.run(
            build_migrate_command(root),
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        (run_dir / "migrate.stdout.log").write_text(migrate.stdout, encoding="utf-8")
        (run_dir / "migrate.stderr.log").write_text(migrate.stderr, encoding="utf-8")
        if migrate.returncode != 0:
            raise SystemExit(
                f"Migrations failed (exit {migrate.returncode}); "
                f"see {run_dir / 'migrate.stderr.log'}"
            )

    port = int(env.get("TREND_PAPER_ENGINE_PORT", str(DEFAULT_ENGINE_PORT)))
    ensure_port_available(port)
    command = wrap_with_caffeinate(build_engine_command(root, port=port))
    engine_log = run_dir / "engine.log"
    with engine_log.open("a", encoding="utf-8") as handle:
        process = subprocess.Popen(
            command,
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    wait_for_engine_health(
        port=port, process=process, timeout_seconds=ENGINE_HEALTH_TIMEOUT_SECONDS
    )

    metadata = {
        "pid": process.pid,
        "port": port,
        "launched_at": datetime.now(UTC).isoformat(),
        "run_dir": str(run_dir),
        "engine_log": str(engine_log),
        "env_file": str(env_file),
        "command": command,
    }
    (run_dir / "launcher.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the trend-live paper engine as a detached background process."
    )
    parser.add_argument("--env-file", default=".env.trend-paper")
    parser.add_argument("--output-dir")
    parser.add_argument("--skip-migrate", action="store_true")
    return parser.parse_args()


def main() -> int:
    metadata = launch_detached_engine(parse_args())
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
