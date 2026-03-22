"""Verify configuration files and database schema."""

import asyncio
import os
from pathlib import Path
import re
from typing import Any

import yaml

from .check_results import CheckResult, CheckStatus

# Configuration file patterns to check
CONFIG_PATTERNS = [
    "**/*.yaml",
    "**/*.yml",
    ".env",
]

# Required tables in database - ALL production tables must exist
REQUIRED_TABLES = [
    # Core time-series data
    "candles",
    "indicators",
    "swings",
    # Smart Money Concept tables
    "smc_events",
    "zones",
    # Trading tables
    "orders",
    "positions",
    "balances",
    # Reporting and alerts
    "reports",
    "alert_snapshots",  # Added for telegram alerts
]

# Services to check connectivity
# Services marked as required must be running for the system to start
# Optional services will only generate warnings if unreachable
SERVICES_TO_CHECK = {
    "postgres": {
        "type": "database",
        "host_env": "POSTGRES_HOST",
        "port_env": "POSTGRES_PORT",
        "required": True,
    },
    "redis": {
        "type": "redis",
        "host_env": "REDIS_HOST",
        "port_env": "REDIS_PORT",
        "required": True,
    },
    "router": {
        "type": "http",
        "url_env": "ROUTER_URL",
        "default_url": "http://localhost:8080",
        "required": True,  # Router is required for production system
    },
}


def substitute_env_vars(content: str) -> str:
    """Substitute ${VAR:-default} patterns with environment variable values."""

    def replacer(match):
        var_name = match.group(1)
        default_value = match.group(2)
        return os.environ.get(var_name, default_value)

    # Pattern matches ${VAR:-default} format
    pattern = r"\$\{([A-Z_][A-Z0-9_]*):-(.*?)\}"
    return re.sub(pattern, replacer, content)


def validate_yaml_configs() -> CheckResult:
    """Parse and validate all YAML configuration files."""
    config_files = []
    invalid_files = []
    validation_errors = {}

    # Find all config files
    found_files: set[Path] = set()  # Use set to avoid duplicates
    for pattern in CONFIG_PATTERNS:
        if pattern.endswith(".yaml") or pattern.endswith(".yml"):
            found_files.update(Path().glob(pattern))
        elif pattern == ".env" and Path(".env").exists():
            # Skip .env as it's not YAML
            continue
    config_files = list(found_files)

    if not config_files:
        return CheckResult(
            status=CheckStatus.WARNING,
            message="No configuration files found",
            details={"searched_patterns": CONFIG_PATTERNS},
        )

    # Validate each file
    for config_file in config_files:
        try:
            content = config_file.read_text()
            # Substitute environment variables
            substituted_content = substitute_env_vars(content)
            data = yaml.safe_load(substituted_content)

            # Basic validation - check it parsed to a dict
            if not isinstance(data, (dict, list)):
                invalid_files.append(str(config_file))
                validation_errors[str(config_file)] = "Invalid structure"
                continue

            # For engine config.yaml, just verify it has some expected structure
            if config_file.name == "config.yaml" and "engine" in str(config_file):
                # Just check it has some common config keys
                expected_sections = ["database", "redis", "binance"]
                has_section = any(section in data for section in expected_sections)
                if not has_section:
                    validation_errors[str(config_file)] = (
                        f"Config missing expected sections: {expected_sections}"
                    )
                    invalid_files.append(str(config_file))

        except Exception as e:
            invalid_files.append(str(config_file))
            validation_errors[str(config_file)] = str(e)

    details: dict[str, Any] = {
        "total_files": len(config_files),
        "invalid_files": invalid_files,
    }

    if validation_errors:
        details["validation_errors"] = validation_errors

    if invalid_files:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"Found {len(invalid_files)} invalid configuration files",
            details=details,
        )
    return CheckResult(
        status=CheckStatus.PASSED,
        message="All configuration files are valid",
        details=details,
    )


async def check_database_schema() -> CheckResult:
    """Connect to database and verify all required tables exist."""
    try:
        import asyncpg

        # Get connection parameters from environment
        conn_params = {
            "host": os.environ.get("POSTGRES_HOST", "localhost"),
            "port": int(os.environ.get("POSTGRES_PORT", "5432")),
            "database": os.environ.get("POSTGRES_DB", "trading_platform"),
            "user": os.environ.get("POSTGRES_USER", "trading_user"),
            "password": os.environ.get(
                "POSTGRES_PASSWORD",
                "your_secure_password_here",
            ),
        }

        pool = await asyncpg.create_pool(**conn_params, min_size=1, max_size=2)

        async with pool.acquire() as conn:
            # Get all tables
            tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)

            table_names = {row["table_name"] for row in tables}
            missing_required = [t for t in REQUIRED_TABLES if t not in table_names]

            # Check if candles is a hypertable (TimescaleDB)
            is_hypertable = False
            has_indexes = 0

            if "candles" in table_names:
                # Check if it's a hypertable
                hypertable_check = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables
                        WHERE hypertable_name = 'candles'
                    )
                """)
                is_hypertable = bool(hypertable_check) if hypertable_check is not None else False

                # Count indexes
                index_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE tablename = 'candles'
                """)
                has_indexes = index_count or 0

        await pool.close()

        details = {
            "found_tables": len(table_names),
            "existing_tables": sorted(table_names),
            "required_tables": REQUIRED_TABLES,
            "missing_required": missing_required,
            "candles_is_hypertable": is_hypertable,
            "candles_indexes": has_indexes,
        }

        if missing_required:
            return CheckResult(
                status=CheckStatus.FAILED,
                message=f"Missing {len(missing_required)} required tables",
                details=details,
            )
        return CheckResult(
            status=CheckStatus.PASSED,
            message="Database schema is properly configured",
            details=details,
        )

    except Exception as e:
        return CheckResult(
            status=CheckStatus.FAILED,
            message="Failed to connect to database",
            details={"error": str(e)},
        )


async def verify_service_connectivity() -> CheckResult:
    """Attempt basic connections to all required services."""
    reachable_services = []
    unreachable_required = {}
    unreachable_optional = {}

    # Check PostgreSQL
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ.get("POSTGRES_DB", "trading_platform"),
            user=os.environ.get("POSTGRES_USER", "trading_user"),
            password=os.environ.get("POSTGRES_PASSWORD", "your_secure_password_here"),
        )
        await conn.close()
        reachable_services.append("postgres")
    except Exception as e:
        if SERVICES_TO_CHECK.get("postgres", {}).get("required", True):
            unreachable_required["postgres"] = str(e)
        else:
            unreachable_optional["postgres"] = str(e)

    # Check Redis
    try:
        import redis.asyncio as aioredis

        redis_url = f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}"
        redis = aioredis.from_url(redis_url)
        await redis.ping()
        await redis.close()
        reachable_services.append("redis")
    except Exception as e:
        if SERVICES_TO_CHECK.get("redis", {}).get("required", True):
            unreachable_required["redis"] = str(e)
        else:
            unreachable_optional["redis"] = str(e)

    # Check HTTP services
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            router_url = os.environ.get("ROUTER_URL", "http://localhost:8001")
            try:
                async with session.get(
                    f"{router_url}/healthz",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    if resp.status < 500:  # Consider 4xx as "reachable"
                        reachable_services.append("router")
                    else:
                        error_msg = f"HTTP {resp.status}"
                        if SERVICES_TO_CHECK.get("router", {}).get("required", True):
                            unreachable_required["router"] = error_msg
                        else:
                            unreachable_optional["router"] = error_msg
            except Exception as e:
                if SERVICES_TO_CHECK.get("router", {}).get("required", True):
                    unreachable_required["router"] = str(e)
                else:
                    unreachable_optional["router"] = str(e)

    except Exception as e:
        unreachable_required["http_client"] = str(e)

    details = {
        "reachable_services": reachable_services,
        "unreachable_required": unreachable_required,
        "unreachable_optional": unreachable_optional,
        "total_checked": len(SERVICES_TO_CHECK),
    }

    if unreachable_required:
        return CheckResult(
            status=CheckStatus.FAILED,
            message=f"Cannot reach {len(unreachable_required)} required services",
            details=details,
        )
    if unreachable_optional:
        return CheckResult(
            status=CheckStatus.WARNING,
            message="Some optional services are unreachable",
            details=details,
        )
    return CheckResult(
        status=CheckStatus.PASSED,
        message="All services are reachable",
        details=details,
    )


# Synchronous wrappers for async functions
def check_database_schema_sync() -> CheckResult:
    """Synchronous wrapper for check_database_schema."""
    return asyncio.run(check_database_schema())


def verify_service_connectivity_sync() -> CheckResult:
    """Synchronous wrapper for verify_service_connectivity."""
    return asyncio.run(verify_service_connectivity())
