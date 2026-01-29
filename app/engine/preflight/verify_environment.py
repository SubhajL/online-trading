"""Verify environment configuration and prerequisites."""

import os
from pathlib import Path
import socket
from typing import Any

from dotenv import load_dotenv

from .check_results import CheckResult, CheckStatus

# Load .env file if it exists
env_path = Path(__file__).parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Required environment variables with validation rules
REQUIRED_ENV_VARS = {
    "BINANCE_API_KEY": {"min_length": 10},
    "BINANCE_SECRET_KEY": {"min_length": 10},
    "POSTGRES_HOST": {"min_length": 1},
    "POSTGRES_PORT": {"type": "int", "min": 1, "max": 65535},
    "REDIS_HOST": {"min_length": 1},
    "REDIS_PORT": {"type": "int", "min": 1, "max": 65535},
}

# Optional environment variables
OPTIONAL_ENV_VARS = {
    "TELEGRAM_BOT_TOKEN": {"min_length": 20},
    "TELEGRAM_CHAT_ID": {"min_length": 1},
    "ROUTER_URL": {"min_length": 10},
}

# Risk parameters with mandatory bounds
RISK_ENV_VARS = {
    "RISK_PER_TRADE_PCT": {"type": "float", "min": 0.001, "max": 0.05},
    "MAX_DAILY_LOSS_PCT": {"type": "float", "min": 0.01, "max": 0.10},
    "MAX_POSITION_SIZE": {"type": "float", "min": 0.0001, "max": 100000},
}

# Service ports to check
SERVICE_PORTS = {
    "postgres": {
        "host_env": "POSTGRES_HOST",
        "port_env": "POSTGRES_PORT",
        "default_port": 5432,
    },
    "redis": {"host_env": "REDIS_HOST", "port_env": "REDIS_PORT", "default_port": 6379},
}

# Required directories with permissions
REQUIRED_DIRS = {
    "logs": os.W_OK | os.R_OK,
    "data": os.W_OK | os.R_OK,
    ".env": os.R_OK,  # File, not directory
}


def check_required_env_vars() -> CheckResult:
    """Verify all required environment variables are set with valid values."""
    missing = []
    invalid = {}
    warnings = []

    # Check required variables
    for var_name, rules in REQUIRED_ENV_VARS.items():
        value = os.environ.get(var_name, "")

        if not value:
            missing.append(var_name)
            continue

        # Validate value
        if "type" in rules and rules["type"] == "int":  # type: ignore[index, operator]
            try:
                int_val = int(value)
                if "min" in rules and int_val < rules["min"]:  # type: ignore[index, operator]
                    invalid[var_name] = f"Value {int_val} is below minimum {rules['min']}"  # type: ignore[index]
                if "max" in rules and int_val > rules["max"]:  # type: ignore[index, operator]
                    invalid[var_name] = f"Value {int_val} is above maximum {rules['max']}"  # type: ignore[index]
            except ValueError:
                invalid[var_name] = f"Expected integer, got '{value}'"

        if "min_length" in rules and len(value) < rules["min_length"]:  # type: ignore[index, operator]
            invalid[var_name] = f"Too short (min {rules['min_length']} chars)"  # type: ignore[index]

    # Check optional variables
    for var_name, rules in OPTIONAL_ENV_VARS.items():
        value = os.environ.get(var_name, "")
        if not value:
            warnings.append(f"Optional {var_name} not set")

    details: dict[str, Any] = {
        "total_checked": len(REQUIRED_ENV_VARS),
        "missing": missing,
        "invalid": invalid,
    }

    if warnings:
        details["optional"] = warnings

    if missing or invalid:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"Missing required environment variables: {len(missing)}, Invalid: {len(invalid)}",
            details=details,
        )

    if warnings:
        return CheckResult(
            status=CheckStatus.WARNING,
            message="All required environment variables are set (with optional warnings)",
            details=details,
        )

    return CheckResult(
        status=CheckStatus.PASSED,
        message="All required environment variables are set",
        details=details,
    )


def check_risk_parameters() -> CheckResult:
    """Verify risk parameters are set and within safe bounds.

    If any risk env var is missing or out of bounds, returns FAILED to prevent
    the engine from starting with permissive defaults.
    """
    missing = []
    invalid = {}

    for var_name, rules in RISK_ENV_VARS.items():
        value = os.environ.get(var_name, "")

        if not value:
            missing.append(var_name)
            continue

        try:
            float_val = float(value)
        except ValueError:
            invalid[var_name] = f"Expected float, got '{value}'"
            continue

        if float_val < rules["min"]:  # type: ignore[operator]
            invalid[var_name] = f"Value {float_val} below minimum {rules['min']}"
        elif float_val > rules["max"]:  # type: ignore[operator]
            invalid[var_name] = f"Value {float_val} above maximum {rules['max']}"

    details: dict[str, Any] = {
        "total_checked": len(RISK_ENV_VARS),
        "missing": missing,
        "invalid": invalid,
    }

    if missing or invalid:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=(
                f"Risk parameters not configured safely: "
                f"{len(missing)} missing, {len(invalid)} invalid"
            ),
            details=details,
        )

    return CheckResult(
        status=CheckStatus.PASSED,
        message="All risk parameters are within safe bounds",
        details=details,
    )


def check_port_availability() -> CheckResult:
    """Ensure required ports are available or already bound to expected services."""
    port_status = {}
    all_ok = True

    for service_name, config in SERVICE_PORTS.items():
        host = os.environ.get(config["host_env"], "localhost")  # type: ignore[call-overload]
        port = int(os.environ.get(config["port_env"], config["default_port"]))  # type: ignore[call-overload]

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))

                if result == 0:
                    # Port is open (service running)
                    port_status[service_name] = {
                        "host": host,
                        "port": port,
                        "status": "running",
                    }
                else:
                    # Connection refused or timeout
                    port_status[service_name] = {
                        "host": host,
                        "port": port,
                        "status": "not running",
                        "error": f"Connection refused on {host}:{port}",
                    }
                    all_ok = False

        except Exception as e:
            port_status[service_name] = {
                "host": host,
                "port": port,
                "status": "error",
                "error": str(e),
            }
            all_ok = False

    if all_ok:
        return CheckResult(
            status=CheckStatus.PASSED,
            message="All required services are running",
            details=port_status,
        )
    return CheckResult(
        status=CheckStatus.FAILED,
        message="Required services are not running",
        details=port_status,
    )


def check_file_permissions() -> CheckResult:
    """Verify read/write permissions for critical directories."""
    missing_dirs = []
    permission_errors = []

    for path, required_perms in REQUIRED_DIRS.items():
        if not os.path.exists(path):
            # Try to create directory if it's not a file
            if not path.endswith(".env") and "." not in os.path.basename(path):
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception as e:
                    missing_dirs.append(f"{path} (failed to create: {e})")
                    continue
            # For files, just check if they exist
            elif not os.path.exists(path):
                missing_dirs.append(path)
                continue

        # Check each permission
        if required_perms & os.R_OK and not os.access(path, os.R_OK):
            permission_errors.append(f"{path}: No read permission")

        if required_perms & os.W_OK and not os.access(path, os.W_OK):
            permission_errors.append(f"{path}: No write permission")

    details = {
        "checked_paths": list(REQUIRED_DIRS.keys()),
        "missing_dirs": missing_dirs,
        "permission_errors": permission_errors,
    }

    if missing_dirs or permission_errors:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"File permission issues found: {len(missing_dirs)} missing, {len(permission_errors)} errors",
            details=details,
        )

    return CheckResult(
        status=CheckStatus.PASSED,
        message="File permissions are correctly set",
        details=details,
    )
