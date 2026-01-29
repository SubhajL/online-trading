"""Main orchestrator for preflight checks."""

import time

from .check_results import CheckResult, CheckStatus, PreflightResults
from .verify_configuration import (
    check_database_schema_sync,
    validate_yaml_configs,
    verify_service_connectivity_sync,
)
from .verify_dependencies import (
    check_python_packages,
    check_python_version,
    check_system_commands,
)
from .verify_environment import (
    check_file_permissions,
    check_port_availability,
    check_required_env_vars,
    check_risk_parameters,
)

# Define check order and names
PREFLIGHT_CHECKS = [
    # Environment checks first
    ("environment", check_required_env_vars),
    ("risk_parameters", check_risk_parameters),
    ("python_version", check_python_version),
    ("packages", check_python_packages),
    ("system_commands", check_system_commands),
    ("ports", check_port_availability),
    ("permissions", check_file_permissions),
    ("yaml_configs", validate_yaml_configs),
    # These require async wrappers
    ("database", lambda: check_database_schema_sync()),
    ("services", lambda: verify_service_connectivity_sync()),
]


def run_all_checks(fail_fast: bool = False) -> PreflightResults:
    """
    Run all preflight checks in order.

    Args:
        fail_fast: Stop on first failure if True

    Returns:
        Aggregated results with timing and recommendations
    """
    start_time = time.time()
    checks: dict[str, CheckResult] = {}
    overall_status = CheckStatus.PASSED
    can_proceed = True

    for check_name, check_func in PREFLIGHT_CHECKS:
        try:
            # Run the check
            result = check_func()
            checks[check_name] = result

            # Update overall status
            if result.status == CheckStatus.FAILED:
                overall_status = CheckStatus.FAILED
                can_proceed = False
                if fail_fast:
                    break
            elif result.status == CheckStatus.WARNING and overall_status != CheckStatus.FAILED:
                overall_status = CheckStatus.WARNING

        except Exception as e:
            # Handle unexpected errors
            checks[check_name] = CheckResult(
                status=CheckStatus.FAILED,
                message=f"Check failed with error: {e!s}",
                details={"error": str(e), "type": type(e).__name__},
            )
            overall_status = CheckStatus.FAILED
            can_proceed = False
            if fail_fast:
                break

    total_time = time.time() - start_time

    return PreflightResults(
        checks=checks,
        overall_status=overall_status,
        total_time_seconds=total_time,
        can_proceed=can_proceed,
    )


def generate_preflight_report(results: PreflightResults) -> str:
    """
    Generate a human-readable report of preflight check results.

    Args:
        results: The aggregated preflight results

    Returns:
        Formatted string for console output
    """
    lines = []

    # Header
    lines.append("\n" + "=" * 60)
    lines.append("PREFLIGHT CHECK RESULTS")
    lines.append("=" * 60)

    # Overall status
    status_symbol = {
        CheckStatus.PASSED: "✅",
        CheckStatus.WARNING: "⚠️ ",
        CheckStatus.FAILED: "❌",
    }

    lines.append(
        f"\nOverall Status: {status_symbol[results.overall_status]} "
        f"{results.overall_status.value.upper()}",
    )
    lines.append(f"Total Time: {results.total_time_seconds:.2f}s")

    if results.can_proceed:
        if results.overall_status == CheckStatus.PASSED:
            lines.append("\n✅ All preflight checks passed! Ready to start services.")
        else:
            lines.append("\n⚠️  Can proceed with warnings. Review issues below.")
    else:
        lines.append("\n❌ Cannot proceed. Fix the issues below before starting.")

    # Individual check results
    lines.append("\n" + "-" * 60)
    lines.append("CHECK DETAILS:")
    lines.append("-" * 60)

    for check_name, result in results.checks.items():
        symbol = status_symbol[result.status]
        lines.append(f"\n{symbol} {check_name}: {result.message}")

        # Show details for failures and warnings
        if result.status != CheckStatus.PASSED:
            if result.details.get("missing"):
                lines.append(f"   Missing: {', '.join(result.details['missing'])}")

            if result.details.get("invalid"):
                lines.append("   Invalid:")
                for key, msg in result.details["invalid"].items():
                    lines.append(f"     - {key}: {msg}")

            if "error" in result.details:
                lines.append(f"   Error: {result.details['error']}")

            if result.details.get("missing_commands"):
                lines.append(
                    f"   Missing commands: {', '.join(result.details['missing_commands'])}",
                )

            if "version_mismatches" in result.details:
                lines.append("   Version mismatches:")
                for pkg, versions in result.details["version_mismatches"].items():
                    lines.append(
                        f"     - {pkg}: required={versions['required']}, "
                        f"installed={versions['installed']}",
                    )

    # Recommendations
    if not results.can_proceed:
        lines.append("\n" + "=" * 60)
        lines.append("RECOMMENDED ACTIONS:")
        lines.append("=" * 60)

        if (
            "environment" in results.checks
            and results.checks["environment"].status == CheckStatus.FAILED
        ):
            lines.append("\n1. Set missing environment variables in .env file")
            lines.append("   cp .env.example .env")
            lines.append("   # Edit .env and add required values")

        if "packages" in results.checks and results.checks["packages"].status == CheckStatus.FAILED:
            lines.append("\n2. Install missing Python packages")
            lines.append("   pip install -r app/engine/requirements.txt")

        if (
            "system_commands" in results.checks
            and results.checks["system_commands"].status == CheckStatus.FAILED
        ):
            lines.append("\n3. Install missing system commands")
            details = results.checks["system_commands"].details
            if "docker" in details.get("missing_commands", []):
                lines.append("   # Install Docker: https://docs.docker.com/get-docker/")
            if "psql" in details.get("missing_commands", []):
                lines.append("   # Install PostgreSQL client: brew install postgresql")

        if "ports" in results.checks and results.checks["ports"].status == CheckStatus.FAILED:
            lines.append("\n4. Start required services")
            lines.append("   make infra-up  # Start PostgreSQL and Redis")

    lines.append("\n" + "=" * 60)

    return "\n".join(lines)
