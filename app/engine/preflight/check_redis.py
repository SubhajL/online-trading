import os
from typing import Optional

import asyncio
import redis.asyncio as redis

REQUIRED_VARS = ["REDIS_HOST", "REDIS_PORT"]


class RedisPreflightError(RuntimeError):
    pass


async def check_redis_connectivity(timeout_seconds: float = 5.0) -> None:
    """
    Validate Redis env and connectivity.

    Required env:
    - REDIS_HOST
    - REDIS_PORT
    Optional:
    - REDIS_PASSWORD
    - REDIS_DB (defaults 0)
    """
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise RedisPreflightError(
            f"Missing Redis env vars: {', '.join(missing)}. Set REDIS_HOST and REDIS_PORT."
        )

    host = os.getenv("REDIS_HOST")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD")
    db = int(os.getenv("REDIS_DB", "0"))

    url = f"redis://{host}:{port}/{db}"
    if password:
        url = f"redis://:{password}@{host}:{port}/{db}"

    client = redis.from_url(url, decode_responses=False)

    try:
        await asyncio.wait_for(client.ping(), timeout=timeout_seconds)
    except Exception as e:  # noqa: BLE001
        raise RedisPreflightError(
            f"Unable to connect to Redis at {host}:{port}/{db}: {e}"
        )
    finally:
        await client.close()