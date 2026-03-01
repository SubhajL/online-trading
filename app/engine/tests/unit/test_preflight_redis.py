import os
import asyncio
import pytest

from app.engine.preflight.check_redis import check_redis_connectivity, RedisPreflightError


class TestRedisPreflight:
    def test_missing_env_vars(self, monkeypatch):
        # Ensure REDIS_URL is not present so fallback path is exercised
        monkeypatch.delenv("REDIS_URL", raising=False)
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

    @pytest.mark.asyncio
    async def test_uses_redis_url_when_set(self, monkeypatch):
        """Preflight prefers REDIS_URL and supports rediss scheme without needing host/port vars."""
        from app.engine.preflight import check_redis as check_mod

        # Ensure host/port are not set so fallback would normally fail
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        rediss_url = "rediss://default:token@example.upstash.io:6379/0"
        monkeypatch.setenv("REDIS_URL", rediss_url)

        captured = {}

        class DummyClient:
            async def ping(self):  # noqa: D401
                return True

            async def close(self):
                return None

        def fake_from_url(url, **kwargs):
            captured["url"] = url
            return DummyClient()

        # Patch redis.from_url inside the module to intercept the URL
        monkeypatch.setattr(check_mod.redis, "from_url", fake_from_url)

        await check_redis_connectivity(0.5)
        assert captured.get("url") == rediss_url
