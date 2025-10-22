import os
import pytest
import redis.asyncio as redis


def create_redis_client_or_skip():
    """Create an asyncio Redis client from REDIS_URL or skip the test.

    No host/port fallback; enforces explicit URL configuration.
    """
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set; skipping Redis test")
    return redis.from_url(url, decode_responses=False)
