#!/usr/bin/env python3
"""
Health check script for Docker container health checks.

Returns exit code 0 if service is healthy, 1 otherwise.
"""

import json
import sys
from urllib.error import URLError
from urllib.request import urlopen


def check_health(port: int = 8000) -> int:
    """
    Check if the engine service is healthy.

    Calls the /health/simple endpoint and verifies the response.

    Args:
        port: Port number where the engine is running (default: 8000)

    Returns:
        0 if healthy, 1 if unhealthy
    """
    url = f"http://localhost:{port}/health/simple"

    try:
        with urlopen(url, timeout=5) as response:
            if response.status != 200:
                return 1

            data = json.loads(response.read().decode())

            if data.get("status") == "ok":
                return 0

            return 1

    except (URLError, json.JSONDecodeError, KeyError, TimeoutError):
        return 1


def main(port: int = 8000) -> None:
    """
    Main entry point for health check script.

    Args:
        port: Port number where the engine is running (default: 8000)
    """
    exit_code = check_health(port)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
