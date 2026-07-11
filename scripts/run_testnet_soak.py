#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import ssl
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in tests

    def load_dotenv(*_args: object, **_kwargs: object) -> None:
        return None


# The soak override MUST be in the default set: without it the dev stack's
# file watchers (uvicorn --reload / nest --watch / air) restart critical
# services on any source edit, silently dooming a multi-day run.
DEFAULT_COMPOSE_FILES = ("docker-compose.dev.yml", "docker-compose.soak.yml")


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout_path: str
    stderr_path: str
    duration_seconds: float


@dataclass(slots=True)
class PeriodicOrderSmokeConfig:
    symbols: tuple[str, ...]
    interval_seconds: int
    cancel_after_seconds: int
    entry_offset_bps: int
    target_notional_usdt: Decimal


def _parse_positive_int(value: str, *, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _parse_positive_decimal(value: str, *, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _format_decimal(value: Decimal, *, places: int) -> str:
    quantum = Decimal("1").scaleb(-places)
    return f"{value.quantize(quantum, rounding=ROUND_DOWN):f}"


def build_periodic_order_smoke_config(environ: dict[str, str]) -> PeriodicOrderSmokeConfig:
    raw_symbols = (
        environ.get("SOAK_SMOKE_SYMBOLS") or environ.get("SOAK_SMOKE_SYMBOL") or "ETHUSDT,BTCUSDT"
    )
    symbols = tuple(symbol.strip().upper() for symbol in raw_symbols.split(",") if symbol.strip())
    if not symbols:
        raise ValueError("SOAK_SMOKE_SYMBOLS must define at least one symbol")

    interval_seconds = _parse_positive_int(
        environ.get("SOAK_SMOKE_INTERVAL_SECONDS", "3600"),
        name="SOAK_SMOKE_INTERVAL_SECONDS",
    )
    cancel_after_seconds = _parse_positive_int(
        environ.get("SOAK_SMOKE_CANCEL_AFTER_SECONDS", "75"),
        name="SOAK_SMOKE_CANCEL_AFTER_SECONDS",
    )
    entry_offset_bps = _parse_positive_int(
        environ.get("SOAK_SMOKE_ENTRY_OFFSET_BPS", "150"),
        name="SOAK_SMOKE_ENTRY_OFFSET_BPS",
    )
    target_notional_usdt = _parse_positive_decimal(
        environ.get("SOAK_SMOKE_TARGET_NOTIONAL_USDT", "25"),
        name="SOAK_SMOKE_TARGET_NOTIONAL_USDT",
    )
    return PeriodicOrderSmokeConfig(
        symbols=symbols,
        interval_seconds=interval_seconds,
        cancel_after_seconds=cancel_after_seconds,
        entry_offset_bps=entry_offset_bps,
        target_notional_usdt=target_notional_usdt,
    )


def build_dynamic_order_smoke_body(
    symbol: str,
    reference_price: Decimal,
    config: PeriodicOrderSmokeConfig,
) -> dict[str, Any]:
    offset = Decimal(config.entry_offset_bps) / Decimal("10000")
    entry_price = reference_price * (Decimal("1") - offset)
    take_profit_price = reference_price * (Decimal("1") + offset)
    stop_loss_price = reference_price * (Decimal("1") - (offset * Decimal("2")))
    quantity = config.target_notional_usdt / entry_price
    return {
        "symbol": symbol,
        "side": "BUY",
        "quantity": _format_decimal(quantity, places=8),
        "take_profit_prices": [_format_decimal(take_profit_price, places=2)],
        "stop_loss_price": _format_decimal(stop_loss_price, places=2),
        "is_futures": False,
        "entry_price": _format_decimal(entry_price, places=2),
        "order_type": "LIMIT",
    }


def validate_soak_environment(environ: dict[str, str]) -> list[CheckResult]:
    results: list[CheckResult] = []

    execution_mode = environ.get("EXECUTION_MODE", "").strip().lower()
    router_execution_env = environ.get("ROUTER_EXECUTION_ENV", "testnet").strip().lower()
    trading_mode = environ.get("TRADING_MODE", "spot").strip().lower()
    data_source = environ.get("BINANCE_DATA_SOURCE", "mainnet").strip().lower()

    if execution_mode != "spot_testnet":
        results.append(
            CheckResult(
                name="execution_mode",
                status="fail",
                message="EXECUTION_MODE must remain spot_testnet for testnet soak",
                details={"observed": execution_mode or None},
            )
        )
    else:
        results.append(
            CheckResult(
                name="execution_mode",
                status="pass",
                message="Execution mode locked to spot_testnet",
            )
        )

    if router_execution_env != "testnet":
        results.append(
            CheckResult(
                name="router_execution_env",
                status="fail",
                message="ROUTER_EXECUTION_ENV=testnet is required for testnet soak",
                details={"observed": router_execution_env or None},
            )
        )
    else:
        results.append(
            CheckResult(
                name="router_execution_env",
                status="pass",
                message="Router execution environment locked to testnet",
            )
        )

    safeguard_failures: list[str] = []
    if data_source != "mainnet":
        safeguard_failures.append("BINANCE_DATA_SOURCE should stay mainnet for real market candles")
    if trading_mode != "spot":
        safeguard_failures.append("TRADING_MODE should be spot for this soak")
    if environ.get("PIPELINE_HEALTH_ALERTS_ENABLED", "1") != "1":
        safeguard_failures.append("PIPELINE_HEALTH_ALERTS_ENABLED must be 1")
    if environ.get("LIVE_REST_FALLBACK_ENABLED", "1") != "1":
        safeguard_failures.append("LIVE_REST_FALLBACK_ENABLED must be 1")
    if environ.get("SPOT_RECONCILIATION_ENABLED", "true").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        safeguard_failures.append("SPOT_RECONCILIATION_ENABLED must be true")
    if environ.get("I_UNDERSTAND_LIVE_TRADING") == "1":
        safeguard_failures.append("I_UNDERSTAND_LIVE_TRADING must stay unset for testnet soak")

    if safeguard_failures:
        results.append(
            CheckResult(
                name="safeguards",
                status="fail",
                message="Testnet soak safety flags are not in the expected state",
                details={"issues": safeguard_failures},
            )
        )
    else:
        results.append(
            CheckResult(
                name="safeguards",
                status="pass",
                message="Safety flags match the planned testnet soak profile",
            )
        )

    missing_tokens = [
        name
        for name in (
            "ROUTER_API_KEY",
            "SECURITY_REQUIRED_API_KEY",
            "ENGINE_INTERNAL_API_TOKEN",
            "INTERNAL_ALERTS_TOKEN",
        )
        if not environ.get(name, "").strip()
    ]
    if missing_tokens:
        results.append(
            CheckResult(
                name="internal_auth",
                status="fail",
                message="Required internal auth tokens must be non-empty before soak",
                details={"missing": missing_tokens},
            )
        )
    else:
        results.append(
            CheckResult(
                name="internal_auth",
                status="pass",
                message="Required internal auth tokens are present",
            )
        )

    return results


def build_recommendations(results: list[CheckResult]) -> list[str]:
    recommendations: list[str] = []
    for result in results:
        handled = False
        if result.status == "fail" and result.name == "execution_mode":
            recommendations.append("Set EXECUTION_MODE=spot_testnet before starting the soak.")
            handled = True
        elif result.status == "fail" and result.name == "router_execution_env":
            recommendations.append(
                "Set ROUTER_EXECUTION_ENV=testnet so the router cannot place mainnet orders."
            )
            handled = True
        elif result.status == "fail" and result.name == "safeguards":
            recommendations.append(
                "Restore the planned soak safety flags: mainnet candles, spot mode, pipeline health alerts, live REST fallback, and spot reconciliation."
            )
            handled = True
        elif result.status == "fail" and result.name == "internal_auth":
            recommendations.append(
                "Populate ROUTER_API_KEY, SECURITY_REQUIRED_API_KEY, ENGINE_INTERNAL_API_TOKEN, and INTERNAL_ALERTS_TOKEN before soak start."
            )
            handled = True
        elif result.status == "fail" and result.name == "preflight_tests":
            recommendations.append(
                "Fix the failing preflight test suite before trusting any soak result."
            )
            handled = True
        elif result.status == "fail" and result.name.startswith("health:"):
            recommendations.append(
                "Inspect stack logs and health endpoints before retrying; a service failed to become healthy."
            )
            handled = True
        elif result.status == "warn" and result.name.startswith("health:"):
            recommendations.append(
                f"Investigate the unhealthy non-critical service ({result.name}); "
                "the soak continued because it does not gate the trading pipeline."
            )
            handled = True
        elif result.status == "fail" and result.name == "log_assertions":
            recommendations.append(
                "Review engine/router startup logs; required testnet execution markers were missing or error signatures were present."
            )
            handled = True
        elif result.status == "skip" and result.name.startswith("order_smoke"):
            recommendations.append(
                "Configure explicit order smoke inputs and rerun with --enable-order-smoke to validate place/cancel behavior automatically."
            )
            handled = True
        elif result.status == "fail" and result.name.startswith("order_smoke"):
            recommendations.append(
                "Inspect periodic order smoke failures; verify live price lookup, router placement, and cancel behavior for the configured symbols."
            )
            handled = True

        if result.status in ("fail", "warn") and not handled:
            recommendations.append(result.message)

    if not recommendations:
        recommendations.append(
            "No immediate improvements from this run. If this was a short smoke, extend the duration to a 24-72h soak."
        )
    seen: set[str] = set()
    unique: list[str] = []
    for rec in recommendations:
        if rec not in seen:
            seen.add(rec)
            unique.append(rec)
    return unique


def build_bff_test_environment(environ: dict[str, str]) -> dict[str, str]:
    sanitized = dict(environ)
    for key in (
        "HOST",
        "PORT",
        "BFF_PORT",
        "ENGINE_HOST",
        "ENGINE_PORT",
        "ENGINE_TYPE",
        "ROUTER_URL",
        "ROUTER_TIMEOUT",
        "ROUTER_RETRY_ATTEMPTS",
        "ROUTER_RETRY_DELAY",
        "WS_CORS_ORIGIN",
        "WS_NAMESPACE",
    ):
        sanitized.pop(key, None)
    return sanitized


def build_health_urls(environ: dict[str, str]) -> dict[str, str]:
    engine_port = environ.get("ENGINE_PORT", "8000").strip() or "8000"
    router_port = environ.get("ROUTER_PORT", "8001").strip() or "8001"
    bff_port = environ.get("BFF_PORT", "8002").strip() or "8002"
    ui_port = environ.get("UI_PORT", "3000").strip() or "3000"
    return {
        "engine": f"http://localhost:{engine_port}/health/simple",
        "router": f"http://localhost:{router_port}/healthz",
        "router_ready": f"http://localhost:{router_port}/readyz",
        "bff": f"http://localhost:{bff_port}/api/health",
        "ui": f"http://localhost:{ui_port}/api/health",
    }


# Startup log markers proving the deferred-legs + reconciler stack (C4–C6)
# is actually live during the soak. Without these the soak would pass while
# exercising none of the code it exists to validate.
DEFERRED_LEGS_LOG_MARKERS = (
    ("Durable bracket reservations enabled", "router did not enable durable bracket reservations"),
    (
        "BRACKET_LEGS_ON_FILL enabled: spot exits placed as OCO on entry fill",
        "router did not enable spot OCO deferred exits (BRACKET_LEGS_ON_FILL off?)",
    ),
    ("Entry fill watcher started", "router did not start the entry-fill watcher"),
    ("Startup reconciliation complete", "router did not complete a startup reconciliation pass"),
)

# Log fragments that must NOT appear: each signals an unrepaired failure the
# reconciler/watcher is supposed to prevent.
FORBIDDEN_LOG_MARKERS = (
    ("SECURITY_REQUIRED_API_KEY must be configured", "router log shows missing required API key"),
    ("401 Unauthorized", "startup logs show unauthorized internal callback or router request"),
    (
        "Startup reconciliation exhausted retries",
        "startup reconciliation failed every attempt — DB or router unhealthy",
    ),
    ("position UNPROTECTED", "an entry filled with no armer — position left unprotected"),
)


def evaluate_log_signatures(combined: str, *, require_deferred_legs: bool = True) -> list[str]:
    """Return the list of log-signature failures (empty means pass).

    Pure so it can be unit-tested without a running stack. The soak requires
    the deferred-legs stack; callers may relax that for a bare-stack probe.
    """
    failures: list[str] = []
    if "Execution subscriber enabled: spot_testnet" not in combined:
        failures.append("engine log missing spot_testnet execution marker")
    if "Order Router starting" not in combined or "testnet" not in combined.lower():
        failures.append("router log missing testnet startup marker")
    if require_deferred_legs:
        for marker, message in DEFERRED_LEGS_LOG_MARKERS:
            if marker not in combined:
                failures.append(message)
    for marker, message in FORBIDDEN_LOG_MARKERS:
        if marker in combined:
            failures.append(message)
    return failures


def resolve_project_python(project_root: Path) -> str:
    project_python = project_root / "app" / "engine" / ".venv" / "bin" / "python"
    return str(project_python) if project_python.exists() else sys.executable


class TestnetSoakRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        load_dotenv()
        self.args = args
        self.project_root = Path(__file__).resolve().parents[1]
        self.project_python = resolve_project_python(self.project_root)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        default_output_dir = self.project_root / "artifacts" / "testnet-soak" / timestamp
        self.output_dir = Path(args.output_dir) if args.output_dir else default_output_dir
        if not self.output_dir.is_absolute():
            self.output_dir = self.project_root / self.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[CheckResult] = []
        self.compose_cmd = self._resolve_compose_command()
        self.report_path = self.output_dir / "report.json"
        self.partial_report_path = self.output_dir / "report.partial.json"
        self.heartbeat_path = self.output_dir / "heartbeat.json"
        self.started_at = datetime.now(UTC)
        self.health_urls = build_health_urls(dict(os.environ))
        self.router_base_url = (
            f"http://localhost:{os.getenv('ROUTER_PORT', '8001').strip() or '8001'}"
        )
        self.periodic_order_smoke_config: PeriodicOrderSmokeConfig | None = None
        self.next_order_smoke_due: float | None = None
        self.order_smoke_cycle_count = 0
        self.order_smoke_symbol_index = 0
        self.heartbeat_interval_seconds = max(
            1, int(getattr(args, "heartbeat_interval_seconds", 60))
        )
        self.stop_requested = False
        self.termination_signal: str | None = None
        self.final_report_written = False
        self.last_heartbeat_at = time.monotonic()
        self._register_signal_handlers()

    def _resolve_compose_command(self) -> list[str]:
        docker_compose = shutil.which("docker-compose")
        if docker_compose:
            return [docker_compose]
        docker = shutil.which("docker")
        if docker:
            return [docker, "compose"]
        raise RuntimeError("Neither docker-compose nor docker compose is available")

    def _compose(self, *args: str) -> list[str]:
        raw = self.args.compose_file or DEFAULT_COMPOSE_FILES
        compose_files = [raw] if isinstance(raw, str) else list(raw)
        file_args = [arg for path in compose_files for arg in ("-f", path)]
        return [*self.compose_cmd, *file_args, *args]

    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _register_signal_handlers(self) -> None:
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(signum, self._handle_termination_signal)
            except ValueError:
                return

    def _handle_termination_signal(self, signum: int, _frame: Any) -> None:
        self.stop_requested = True
        if self.termination_signal is None:
            self.termination_signal = signal.Signals(signum).name
        self._write_runtime_artifacts(run_state="interrupted")

    def _current_run_state(self) -> str:
        return "interrupted" if self.stop_requested else "running"

    def _build_report_payload(self, *, report_type: str, run_state: str) -> dict[str, Any]:
        overall_pass = run_state == "completed" and all(
            result.status == "pass"
            for result in self.results
            if result.status not in ("skip", "warn")
        )
        payload = {
            "started_at": self.started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "duration_seconds": self.args.duration_seconds,
            "overall_status": "pass" if overall_pass else "fail",
            "warnings": sum(1 for result in self.results if result.status == "warn"),
            "report_type": report_type,
            "run_state": run_state,
            "termination_signal": self.termination_signal,
            "results": [asdict(result) for result in self.results],
            "recommendations": build_recommendations(self.results),
        }
        return payload

    def _write_runtime_artifacts(self, *, run_state: str) -> None:
        payload = self._build_report_payload(report_type="partial", run_state=run_state)
        self._write_json(self.partial_report_path, payload)
        heartbeat_payload = {
            "started_at": self.started_at.isoformat(),
            "updated_at": payload["finished_at"],
            "run_state": run_state,
            "termination_signal": self.termination_signal,
            "result_count": len(self.results),
            "latest_result": asdict(self.results[-1]) if self.results else None,
        }
        self._write_json(self.heartbeat_path, heartbeat_payload)

    def _maybe_write_heartbeat(self) -> None:
        current_time = time.monotonic()
        if current_time - self.last_heartbeat_at < self.heartbeat_interval_seconds:
            return
        self.last_heartbeat_at = current_time
        self._write_runtime_artifacts(run_state=self._current_run_state())

    def _sleep_with_shutdown(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while not self.stop_requested and time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            time.sleep(min(1.0, remaining))

    def _run_command(
        self,
        name: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        check: bool = False,
    ) -> CommandResult:
        slug = name.replace("/", "_").replace(" ", "_")
        stdout_path = self.output_dir / f"{slug}.stdout.log"
        stderr_path = self.output_dir / f"{slug}.stderr.log"
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=str(cwd or self.project_root),
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )
        duration_seconds = time.monotonic() - started
        self._write_text(stdout_path, completed.stdout)
        self._write_text(stderr_path, completed.stderr)
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                command,
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return CommandResult(
            returncode=completed.returncode,
            stdout_path=str(stdout_path.relative_to(self.project_root)),
            stderr_path=str(stderr_path.relative_to(self.project_root)),
            duration_seconds=duration_seconds,
        )

    def _record(self, result: CheckResult) -> None:
        self.results.append(result)
        self._write_runtime_artifacts(run_state=self._current_run_state())

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = 5,
        allow_insecure_tls: bool = False,
    ) -> tuple[int, str]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=payload, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if payload is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8")
        except HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except URLError as exc:
            if (
                allow_insecure_tls
                and url.startswith("https://")
                and "CERTIFICATE_VERIFY_FAILED" in str(exc).upper()
            ):
                insecure_context = ssl._create_unverified_context()
                with urlopen(request, timeout=timeout, context=insecure_context) as response:
                    return response.status, response.read().decode("utf-8")
            raise RuntimeError(str(exc)) from exc
        except http.client.HTTPException as exc:
            raise RuntimeError(str(exc)) from exc

    def _wait_for_http(
        self, name: str, url: str, *, timeout_seconds: int = 120, critical: bool = True
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                status, body = self._request_json(url, timeout=5)
                if 200 <= status < 300:
                    self._record(
                        CheckResult(
                            name=f"health:{name}",
                            status="pass",
                            message=f"{name} became healthy",
                            details={"url": url, "status": status, "body": body[:500]},
                        )
                    )
                    return
            except Exception:
                pass
            time.sleep(2)

        self._record(
            CheckResult(
                name=f"health:{name}",
                status="fail" if critical else "warn",
                message=f"{name} did not become healthy within timeout",
                details={"url": url, "timeout_seconds": timeout_seconds},
            )
        )

    def _parse_json_body(self, raw_body: str) -> Any:
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return raw_body

    def _get_periodic_order_smoke_config(self) -> PeriodicOrderSmokeConfig:
        if self.periodic_order_smoke_config is None:
            self.periodic_order_smoke_config = build_periodic_order_smoke_config(dict(os.environ))
        return self.periodic_order_smoke_config

    def _next_order_smoke_symbol(self, config: PeriodicOrderSmokeConfig) -> str:
        symbol = config.symbols[self.order_smoke_symbol_index % len(config.symbols)]
        self.order_smoke_symbol_index += 1
        return symbol

    def _fetch_reference_price(self, symbol: str) -> Decimal:
        base_url = os.getenv("BINANCE_SPOT_BASE_URL", "https://testnet.binance.vision").rstrip("/")
        status, raw_body = self._request_json(
            f"{base_url}/api/v3/ticker/price?symbol={symbol}",
            timeout=10,
            allow_insecure_tls=True,
        )
        parsed = self._parse_json_body(raw_body)
        if status >= 300:
            raise RuntimeError(f"price lookup failed with status {status}: {parsed}")
        price = parsed.get("price") if isinstance(parsed, dict) else None
        if not price:
            raise RuntimeError("price lookup response missing price")
        return Decimal(str(price))

    def _resolve_exchange_order_id(self, symbol: str, client_order_id: str) -> int:
        api_key = (os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_SPOT_API_KEY") or "").strip()
        api_secret = (
            os.getenv("BINANCE_SECRET_KEY")
            or os.getenv("BINANCE_SPOT_SECRET_KEY")
            or os.getenv("BINANCE_API_SECRET")
            or ""
        ).strip()
        if not api_key or not api_secret:
            raise RuntimeError(
                "Binance spot API credentials are required to resolve exchange order IDs"
            )

        params = {
            "symbol": symbol,
            "origClientOrderId": client_order_id,
            "timestamp": str(int(time.time() * 1000)),
        }
        query = urlencode(params)
        signature = hmac.new(
            api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        base_url = os.getenv("BINANCE_SPOT_BASE_URL", "https://testnet.binance.vision").rstrip("/")
        status, raw_body = self._request_json(
            f"{base_url}/api/v3/order?{query}&signature={signature}",
            headers={"X-MBX-APIKEY": api_key},
            timeout=20,
            allow_insecure_tls=True,
        )
        parsed = self._parse_json_body(raw_body)
        if status >= 300:
            raise RuntimeError(f"order lookup failed with status {status}: {parsed}")
        order_id = parsed.get("orderId") if isinstance(parsed, dict) else None
        if order_id is None:
            raise RuntimeError("order lookup response missing orderId")
        return int(order_id)

    def validate_environment(self) -> bool:
        env_results = validate_soak_environment(dict(os.environ))
        for result in env_results:
            self._record(result)
        return all(result.status == "pass" for result in env_results)

    def run_preflight_tests(self) -> bool:
        commands = [
            (
                "preflight_engine_tests",
                [
                    self.project_python,
                    "-m",
                    "pytest",
                    "-q",
                    "app/engine/tests/unit/test_internal_api_auth.py",
                    "app/engine/tests/unit/test_order_update_webhook.py",
                    "app/engine/tests/unit/test_router_execution_subscriber.py",
                    "app/engine/tests/unit/test_main_execution_wiring.py",
                ],
                self.project_root,
            ),
            (
                "preflight_router_tests",
                ["go", "test", "./cmd/router", "./internal/orders"],
                self.project_root / "app" / "router",
            ),
            (
                "preflight_bff_tests",
                [
                    "pnpm",
                    "--filter=bff",
                    "test",
                    "--",
                    "--runInBand",
                    "src/router-client/router-client.service.spec.ts",
                    "src/config/configuration.spec.ts",
                    "src/trading/trading.service.spec.ts",
                    "src/orders/repositories/order.repository.spec.ts",
                ],
                self.project_root,
                build_bff_test_environment(dict(os.environ)),
            ),
        ]
        passed = True
        for command_tuple in commands:
            if len(command_tuple) == 3:
                name, command, cwd = command_tuple
                env = None
            else:
                name, command, cwd, env = command_tuple
            result = self._run_command(name, command, cwd=cwd, env=env)
            status = "pass" if result.returncode == 0 else "fail"
            if status == "fail":
                passed = False
            self._record(
                CheckResult(
                    name="preflight_tests",
                    status=status,
                    message=f"{name} {'passed' if status == 'pass' else 'failed'}",
                    details={
                        "command": shlex.join(command),
                        "cwd": str(
                            cwd.relative_to(self.project_root)
                            if cwd != self.project_root
                            else Path(".")
                        ),
                        "returncode": result.returncode,
                        "duration_seconds": round(result.duration_seconds, 2),
                    },
                    artifacts=[result.stdout_path, result.stderr_path],
                )
            )
            if status == "fail":
                break
        return passed

    def start_stack(self) -> bool:
        command = self._compose(
            "up",
            "-d",
            "--build",
            "postgres",
            "redis",
            "migrate",
            "engine",
            "router",
            "bff",
            "ui",
        )
        result = self._run_command("compose_up", command, cwd=self.project_root)
        status = "pass" if result.returncode == 0 else "fail"
        self._record(
            CheckResult(
                name="compose_up",
                status=status,
                message="Docker Compose stack started"
                if status == "pass"
                else "Docker Compose stack failed to start",
                details={"command": shlex.join(command), "returncode": result.returncode},
                artifacts=[result.stdout_path, result.stderr_path],
            )
        )
        return status == "pass"

    def check_stack_health(self) -> bool:
        for name in ("engine", "router", "bff"):
            self._wait_for_http(name, self.health_urls[name])
        # The soak validates the engine→router trading pipeline; the UI is a
        # bystander that monitor_window never probes, so an unhealthy UI is
        # recorded as a warning instead of aborting a 7-day run.
        self._wait_for_http("ui", self.health_urls["ui"], critical=False)
        # /readyz is 503 while the startup reconciler runs and flips to 200
        # once it completes, so a passing probe proves C6 reconciliation ran
        # to completion before the stack started taking work. Allow more time
        # than the liveness probes: the reconciler retries up to 3x with a
        # 2-minute timeout each before failing open (~6.5m worst case), and a
        # slow first sweep must not spuriously fail an otherwise healthy soak.
        self._wait_for_http("router_ready", self.health_urls["router_ready"], timeout_seconds=420)
        return not any(
            result.status == "fail" for result in self.results if result.name.startswith("health:")
        )

    def assert_log_signatures(self) -> bool:
        command = self._compose("logs", "--no-color", "engine", "router")
        result = self._run_command("compose_logs_engine_router", command, cwd=self.project_root)
        combined = ""
        stdout_abs = self.project_root / result.stdout_path
        if stdout_abs.exists():
            combined = stdout_abs.read_text(encoding="utf-8")

        failures = evaluate_log_signatures(combined)

        status = "pass" if not failures else "fail"
        self._record(
            CheckResult(
                name="log_assertions",
                status=status,
                message="Startup log assertions passed"
                if status == "pass"
                else "Startup log assertions failed",
                details={"failures": failures},
                artifacts=[result.stdout_path, result.stderr_path],
            )
        )
        return status == "pass"

    def maybe_run_order_smoke(self) -> None:
        if not self.args.enable_order_smoke:
            self._record(
                CheckResult(
                    name="order_smoke",
                    status="skip",
                    message="Order smoke disabled; configure explicit smoke payload to automate place/cancel checks",
                )
            )
            return
        try:
            config = self._get_periodic_order_smoke_config()
        except ValueError as exc:
            self._record(
                CheckResult(
                    name="order_smoke",
                    status="fail",
                    message="Order smoke configuration is invalid",
                    details={"error": str(exc)},
                )
            )
            return
        self.run_order_smoke_cycle("startup")
        self.next_order_smoke_due = time.monotonic() + config.interval_seconds

    def run_order_smoke_cycle(self, trigger: str) -> None:
        config = self._get_periodic_order_smoke_config()
        symbol = self._next_order_smoke_symbol(config)
        self.order_smoke_cycle_count += 1
        result_name = f"order_smoke:{trigger}:{self.order_smoke_cycle_count}:{symbol}"
        headers = {"Authorization": f"Bearer {os.getenv('ROUTER_API_KEY', '')}"}
        try:
            reference_price = self._fetch_reference_price(symbol)
            body = build_dynamic_order_smoke_body(symbol, reference_price, config)
            status_code, raw_body = self._request_json(
                f"{self.router_base_url}/place_bracket",
                method="POST",
                headers=headers,
                body=body,
                timeout=20,
            )
            parsed = self._parse_json_body(raw_body)
        except Exception as exc:
            self._record(
                CheckResult(
                    name=result_name,
                    status="fail",
                    message="Order smoke placement failed",
                    details={"error": str(exc), "symbol": symbol, "trigger": trigger},
                )
            )
            return

        if status_code >= 300:
            self._record(
                CheckResult(
                    name=result_name,
                    status="fail",
                    message="Router rejected order smoke placement",
                    details={
                        "status": status_code,
                        "body": parsed,
                        "symbol": symbol,
                        "trigger": trigger,
                    },
                )
            )
            return

        client_order_id = (
            parsed.get("client_order_ids", {}).get("main") if isinstance(parsed, dict) else None
        )
        if not client_order_id:
            self._record(
                CheckResult(
                    name=result_name,
                    status="fail",
                    message="Order smoke placement succeeded but no main client order ID was returned",
                    details={"body": parsed, "symbol": symbol, "trigger": trigger},
                )
            )
            return

        try:
            exchange_order_id = self._resolve_exchange_order_id(symbol, client_order_id)
        except Exception as exc:
            self._record(
                CheckResult(
                    name=result_name,
                    status="fail",
                    message="Order smoke could not resolve exchange order ID",
                    details={
                        "error": str(exc),
                        "client_order_id": client_order_id,
                        "symbol": symbol,
                        "trigger": trigger,
                    },
                )
            )
            return

        self._sleep_with_shutdown(config.cancel_after_seconds)
        cancel_status, cancel_body = self._request_json(
            f"{self.router_base_url}/cancel",
            method="POST",
            headers=headers,
            body={
                "symbol": symbol,
                "order_id": exchange_order_id,
                "client_order_id": client_order_id,
            },
            timeout=20,
        )
        parsed_cancel_body = self._parse_json_body(cancel_body)
        if cancel_status >= 300:
            self._record(
                CheckResult(
                    name=result_name,
                    status="fail",
                    message="Order smoke cancel failed",
                    details={
                        "status": cancel_status,
                        "body": parsed_cancel_body,
                        "client_order_id": client_order_id,
                        "symbol": symbol,
                        "trigger": trigger,
                    },
                )
            )
            return

        self._record(
            CheckResult(
                name=result_name,
                status="pass",
                message="Order smoke placement and cancel both succeeded",
                details={
                    "client_order_id": client_order_id,
                    "symbol": symbol,
                    "trigger": trigger,
                    "reference_price": _format_decimal(reference_price, places=2),
                },
            )
        )

    def monitor_window(self) -> None:
        deadline = time.monotonic() + self.args.duration_seconds
        failures: list[str] = []
        samples = 0
        while time.monotonic() < deadline:
            if self.stop_requested:
                break
            current_time = time.monotonic()
            if (
                self.args.enable_order_smoke
                and self.periodic_order_smoke_config is not None
                and self.next_order_smoke_due is not None
                and current_time >= self.next_order_smoke_due
            ):
                self.run_order_smoke_cycle("periodic")
                self.next_order_smoke_due = (
                    time.monotonic() + self.periodic_order_smoke_config.interval_seconds
                )
            samples += 1
            for name in ("engine", "router", "bff"):
                url = self.health_urls[name]
                try:
                    status, _body = self._request_json(url, timeout=5)
                    if status >= 300:
                        failures.append(f"{name} returned {status}")
                except Exception as exc:
                    failures.append(f"{name} health probe failed: {exc}")
            self._maybe_write_heartbeat()
            self._sleep_with_shutdown(self.args.poll_interval_seconds)

        interrupted = self.stop_requested
        status = "pass" if not failures and not interrupted else "fail"
        self._record(
            CheckResult(
                name="monitor_window",
                status=status,
                message=(
                    "Bounded soak monitoring completed"
                    if status == "pass"
                    else "Bounded soak monitoring was interrupted before completion"
                    if interrupted
                    else "Health probe failures occurred during bounded soak monitoring"
                ),
                details={
                    "samples": samples,
                    "failures": failures[:20],
                    "termination_signal": self.termination_signal,
                },
            )
        )

    def collect_compose_logs(self) -> None:
        try:
            result = self._run_command(
                "compose_logs_full",
                self._compose("logs", "--no-color"),
                cwd=self.project_root,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            self._record(
                CheckResult(
                    name="artifact_logs",
                    status="fail",
                    message="Docker Compose log collection timed out after 120s",
                )
            )
            return
        self._record(
            CheckResult(
                name="artifact_logs",
                status="pass",
                message="Collected Docker Compose logs",
                artifacts=[result.stdout_path, result.stderr_path],
            )
        )

    def maybe_shutdown(self) -> None:
        if self.args.keep_running:
            self._record(
                CheckResult(
                    name="shutdown",
                    status="skip",
                    message="Stack left running by request",
                )
            )
            return

        result = self._run_command(
            "compose_down", self._compose("down", "-v"), cwd=self.project_root
        )
        self._record(
            CheckResult(
                name="shutdown",
                status="pass" if result.returncode == 0 else "fail",
                message="Docker Compose stack shut down"
                if result.returncode == 0
                else "Docker Compose stack shutdown failed",
                artifacts=[result.stdout_path, result.stderr_path],
            )
        )

    def write_report(self) -> dict[str, Any]:
        run_state = "interrupted" if self.stop_requested else "completed"
        report = self._build_report_payload(report_type="final", run_state=run_state)
        self._write_json(self.report_path, report)
        self.final_report_written = True
        return report

    def run(self) -> dict[str, Any]:
        try:
            if not self.validate_environment():
                return self.write_report()

            if not self.args.skip_preflight_tests and not self.run_preflight_tests():
                self.collect_compose_logs()
                return self.write_report()

            if not self.start_stack():
                self.collect_compose_logs()
                return self.write_report()

            health_ok = self.check_stack_health()
            logs_ok = self.assert_log_signatures()
            if health_ok and logs_ok:
                self.maybe_run_order_smoke()
                self.monitor_window()
            self.collect_compose_logs()
            return self.write_report()
        except Exception as exc:
            self._record(
                CheckResult(
                    name="runner_exception",
                    status="fail",
                    message="The soak runner encountered an unexpected exception",
                    details={"error": str(exc), "type": type(exc).__name__},
                )
            )
            self.collect_compose_logs()
            return self.write_report()
        finally:
            self.maybe_shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded automated testnet soak.")
    parser.add_argument(
        "--compose-file",
        action="append",
        default=None,
        help="Docker Compose file; repeat for override files (default: docker-compose.dev.yml)",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=120,
        help="How long to monitor the running stack after health checks pass",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=15,
        help="Polling interval during the bounded soak window",
    )
    parser.add_argument(
        "--output-dir",
        help="Artifact directory for logs and the JSON report",
    )
    parser.add_argument(
        "--heartbeat-interval-seconds",
        type=int,
        default=60,
        help="How often to refresh heartbeat and partial report artifacts during the soak window",
    )
    parser.add_argument(
        "--skip-preflight-tests",
        action="store_true",
        help="Skip code-level preflight test commands",
    )
    parser.add_argument(
        "--enable-order-smoke",
        action="store_true",
        help="Enable automated place/cancel smoke using explicit SOAK_SMOKE_* env vars",
    )
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave the Docker Compose stack running after the bounded soak completes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.compose_file:
        args.compose_file = list(DEFAULT_COMPOSE_FILES)
    runner = TestnetSoakRunner(args)
    report = runner.run()
    print(json.dumps(report, indent=2))
    return 0 if report["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
