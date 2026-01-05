import asyncio
import os

import redis.asyncio as redis

REQUIRED_VARS = ["REDIS_HOST", "REDIS_PORT"]


class RedisPreflightError(RuntimeError):
    pass


async def check_redis_connectivity(timeout_seconds: float = 5.0) -> None:
    """
    Validate Redis env and connectivity.

    Preferred env:
    - REDIS_URL (supports redis:// and rediss://)

    Fallback env (when REDIS_URL is not set):
    - REDIS_HOST
    - REDIS_PORT
    Optional:
    - REDIS_PASSWORD
    - REDIS_DB (defaults 0)
    """
    # Prefer a full connection URL first so TLS (rediss://) works out-of-the-box
    url = os.getenv("REDIS_URL")
    if url:
        client = redis.from_url(url, decode_responses=False)
        try:
            await asyncio.wait_for(client.ping(), timeout=timeout_seconds)
            return
        except Exception as e:
            raise RedisPreflightError(
                f"Unable to connect to Redis using REDIS_URL: {e}",
            )
        finally:
            try:
                await client.close()
            except Exception:
                pass

    # Fallback to host/port/password/db if REDIS_URL isn't provided
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        raise RedisPreflightError(
            f"Missing Redis env vars: {', '.join(missing)}. Set REDIS_URL or REDIS_HOST and REDIS_PORT.",
        )

    host = os.getenv("REDIS_HOST")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD")
    db = int(os.getenv("REDIS_DB", "0"))

    # Default to non-TLS when building from parts; users can supply REDIS_URL for TLS
    built_url = f"redis://{host}:{port}/{db}"
    if password:
        built_url = f"redis://:{password}@{host}:{port}/{db}"

    client = redis.from_url(built_url, decode_responses=False)

    try:
        await asyncio.wait_for(client.ping(), timeout=timeout_seconds)
    except Exception as e:
        raise RedisPreflightError(
            f"Unable to connect to Redis at {host}:{port}/{db}: {e}",
        )
    finally:
        try:
            await client.close()
        except Exception:
            pass
