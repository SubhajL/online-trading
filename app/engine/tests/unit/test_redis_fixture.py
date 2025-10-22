import os
import pytest


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_client_fixture_ping(redis_client):
    """redis_client from fixture should be connected and respond to PING."""
    pong = await redis_client.ping()
    assert pong is True


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_set_get_roundtrip(redis_client, redis_key):
    """Set/get roundtrip succeeds with binary payloads."""
    key = redis_key
    payload = b"hello-fixture"

    await redis_client.set(key, payload)
    got = await redis_client.get(key)

    assert got == payload


def test_redis_fixture_skips_without_url(monkeypatch):
    """When REDIS_URL is missing, helper signals skip (no fallback)."""
    from app.engine.tests.redis_helpers import create_redis_client_or_skip

    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(pytest.skip.Exception):
        # The helper should skip the test when no URL is provided
        _ = create_redis_client_or_skip()
