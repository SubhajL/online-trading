import os
import asyncio
import pytest

from app.engine.preflight.check_redis import check_redis_connectivity, RedisPreflightError


class TestRedisPreflight:
    def test_missing_env_vars(self, monkeypatch):
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with pytest.raises(RedisPreflightError) as exc:
            asyncio.run(check_redis_connectivity(0.1))
        assert "Missing Redis env vars" in str(exc.value)

    @pytest.mark.redis
    @pytest.mark.asyncio
    async def test_success_ping(self, monkeypatch):
        # These values should match local docker compose if running
        monkeypatch.setenv("REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
        monkeypatch.setenv("REDIS_PORT", os.getenv("REDIS_PORT", "6379"))
        if os.getenv("REDIS_PASSWORD"):
            monkeypatch.setenv("REDIS_PASSWORD", os.getenv("REDIS_PASSWORD", ""))
        monkeypatch.setenv("REDIS_DB", os.getenv("REDIS_DB", "0"))

        try:
            await check_redis_connectivity(1.0)
        except RedisPreflightError as e:
            pytest.skip(f"Redis not reachable: {e}")