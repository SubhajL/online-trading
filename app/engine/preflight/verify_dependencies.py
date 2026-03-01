"""Verify system dependencies and requirements."""

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .check_results import CheckResult, CheckStatus

# Minimum Python version required
MIN_PYTHON_VERSION = (3, 11)

# Required system commands
REQUIRED_COMMANDS = [
    "docker",
    "psql",
    "redis-cli",
    "git",
    "make",
]

# Optional but recommended commands
OPTIONAL_COMMANDS = [
    "gh",  # GitHub CLI
    "htop",  # Process monitoring
]


def check_python_version() -> CheckResult:
    """Ensure Python version meets minimum requirements."""
    current_version = sys.version_info
    current_str = f"{current_version[0]}.{current_version[1]}.{current_version[2]}"
    min_str = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}"

    meets_requirement = current_version[0] > MIN_PYTHON_VERSION[0] or (
        current_version[0] == MIN_PYTHON_VERSION[0] and current_version[1] >= MIN_PYTHON_VERSION[1]
    )

    details = {
        "current_version": current_str,
        "min_version": min_str,
        "meets_requirement": meets_requirement,
    }

    if meets_requirement:
        return CheckResult(
            status=CheckStatus.PASSED,
            message=f"Python {current_str} meets minimum requirement of {min_str}",
            details=details,
        )
    return CheckResult(
        status=CheckStatus.FAILED,
        message=f"Python {current_str} is below minimum requirement of {min_str}",
        details=details,
    )


def check_python_packages() -> CheckResult:
    """Verify all required Python packages are installed with correct versions."""
    requirements_path = Path("app/engine/requirements.txt")

    if not requirements_path.exists():
        return CheckResult(
            status=CheckStatus.FAILED,
            message="requirements.txt not found",
            details={"error": f"Expected at {requirements_path}"},
        )

    # Parse requirements
    required_packages = {}
    requirements_text = requirements_path.read_text()

    for line in requirements_text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Handle different requirement formats
        if "==" in line:
            pkg, version = line.split("==", 1)
            required_packages[pkg.strip()] = version.strip()
        elif ">=" in line or "<=" in line or "~=" in line:
            # For now, just get package name
            pkg = line.split("[")[0].split(">")[0].split("<")[0].split("~")[0]
            required_packages[pkg.strip()] = "any"
        else:
            required_packages[line.strip()] = "any"

    # Get installed packages
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            check=True,
        )
        installed_lines = result.stdout.strip().split("\n")
    except subprocess.CalledProcessError:
        return CheckResult(
            status=CheckStatus.FAILED,
            message="Failed to get installed packages",
            details={"error": "pip freeze failed"},
        )

    # Parse installed packages
    installed_packages = {}
    for line in installed_lines:
        if "==" in line:
            pkg, version = line.split("==", 1)
            # Normalize package names (e.g., prometheus-client vs prometheus_client)
            normalized_pkg = pkg.strip().replace("_", "-").lower()
            installed_packages[normalized_pkg] = version.strip()
            # Also store with underscores for compatibility
            installed_packages[pkg.strip().replace("-", "_").lower()] = version.strip()

    # Check for missing packages
    missing_packages = []
    version_mismatches = {}

    for pkg, required_version in required_packages.items():
        # Try multiple variations of the package name
        normalized_pkg = pkg.lower().replace("_", "-")
        underscore_pkg = pkg.lower().replace("-", "_")
        found = False
        found_pkg = None

        for variant in [pkg, normalized_pkg, underscore_pkg]:
            if variant in installed_packages:
                found = True
                found_pkg = variant
                break

        if not found:
            missing_packages.append(pkg)
        elif (
            found
            and required_version != "any"
            and installed_packages[found_pkg] != required_version
        ):
            version_mismatches[pkg] = {
                "required": required_version,
                "installed": installed_packages[found_pkg],
            }

    details: dict[str, Any] = {
        "total_required": len(required_packages),
        "missing_packages": missing_packages,
    }

    if version_mismatches:
        details["version_mismatches"] = version_mismatches

    if missing_packages:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"Missing {len(missing_packages)} required packages",
            details=details,
        )
    if version_mismatches:
        return CheckResult(
            status=CheckStatus.WARNING,
            message=f"All packages installed but {len(version_mismatches)} have version mismatches",
            details=details,
        )
    return CheckResult(
        status=CheckStatus.PASSED,
        message="All required packages are installed",
        details=details,
    )


def check_system_commands() -> CheckResult:
    """Check for required system commands."""
    missing_commands = []
    optional_missing = []
    command_paths = {}

    # Check required commands
    for cmd in REQUIRED_COMMANDS:
        path = shutil.which(cmd)
        if path:
            command_paths[cmd] = path
        else:
            missing_commands.append(cmd)

    # Check optional commands
    for cmd in OPTIONAL_COMMANDS:
        path = shutil.which(cmd)
        if path:
            command_paths[cmd] = path
        else:
            optional_missing.append(cmd)

    details = {
        "checked_commands": REQUIRED_COMMANDS + OPTIONAL_COMMANDS,
        "missing_commands": missing_commands,
        "optional_missing": optional_missing,
        "found_paths": command_paths,
    }

    if missing_commands:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"Missing {len(missing_commands)} required system commands",
            details=details,
        )
    if optional_missing:
        return CheckResult(
            status=CheckStatus.WARNING,
            message="All required system commands are available (some optional missing)",
            details=details,
        )
    return CheckResult(
        status=CheckStatus.PASSED,
        message="All required system commands are available",
        details=details,
    )
