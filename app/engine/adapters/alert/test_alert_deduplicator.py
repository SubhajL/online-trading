import asyncio
from typing import Any
from unittest.mock import Mock, patch

import pytest

from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator


class TestAlertDeduplicator:
    @pytest.fixture
    def mock_redis(self) -> Any:
        redis = Mock()
        redis.get = Mock(return_value=None)
        redis.setex = Mock()
        redis.delete = Mock()
        return redis

    @pytest.fixture
    def deduplicator(self, mock_redis: Any) -> Any:
        with patch(
            "app.engine.adapters.alert.alert_deduplicator.redis.Redis", return_value=mock_redis
        ):
            return AlertDeduplicator(ttl_seconds=60)

    def test_is_duplicate_new_key(
        self,
        deduplicator: Any,
        mock_redis: Any,
    ) -> None:
        key = "test:key:123"
        mock_redis.get.return_value = None

        result = deduplicator.is_duplicate(key)

        assert result is False
        mock_redis.get.assert_called_once_with(f"alert:dedup:{key}")

    def test_is_duplicate_existing_key(
        self,
        deduplicator: Any,
        mock_redis: Any,
    ) -> None:
        key = "test:key:123"
        mock_redis.get.return_value = b"1"

        result = deduplicator.is_duplicate(key)

        assert result is True
        mock_redis.get.assert_called_once_with(f"alert:dedup:{key}")

    def test_add_key(self, deduplicator: Any, mock_redis: Any) -> None:
        key = "test:key:123"

        deduplicator.add(key)

        mock_redis.setex.assert_called_once_with(
            f"alert:dedup:{key}",
            60,  # ttl_seconds
            "1",
        )

    def test_clear_key(self, deduplicator: Any, mock_redis: Any) -> None:
        key = "test:key:123"

        deduplicator.clear(key)

        mock_redis.delete.assert_called_once_with(f"alert:dedup:{key}")

    def test_custom_ttl(self, mock_redis: Any) -> None:
        with patch(
            "app.engine.adapters.alert.alert_deduplicator.redis.Redis", return_value=mock_redis
        ):
            dedup = AlertDeduplicator(ttl_seconds=300)
            dedup.add("key")

            mock_redis.setex.assert_called_once_with(
                "alert:dedup:key",
                300,
                "1",
            )

    def test_redis_connection_error(
        self,
        deduplicator: Any,
        mock_redis: Any,
    ) -> None:
        mock_redis.get.side_effect = Exception("Redis connection error")

        # Should return False on error (allowing alert to be sent)
        result = deduplicator.is_duplicate("key")
        assert result is False

    @pytest.mark.asyncio
    async def test_async_compatibility(self, deduplicator: Any) -> None:
        # Test that methods can be used in async context
        result = await asyncio.to_thread(deduplicator.is_duplicate, "async_key")
        assert isinstance(result, bool)


class TestAlertDeduplicatorEnvConfig:
    """Test Redis configuration from environment variables."""

    def test_uses_redis_host_env_var(self, monkeypatch: Any) -> None:
        """AlertDeduplicator reads REDIS_HOST from environment."""
        monkeypatch.setenv("REDIS_HOST", "redis-server")
        monkeypatch.setenv("REDIS_PORT", "6379")

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.Redis") as mock_redis_class:
            mock_redis_class.return_value.ping.return_value = True
            AlertDeduplicator()

            mock_redis_class.assert_called_once()
            call_kwargs = mock_redis_class.call_args[1]
            assert call_kwargs["host"] == "redis-server"

    def test_uses_redis_port_env_var(self, monkeypatch: Any) -> None:
        """AlertDeduplicator reads REDIS_PORT from environment."""
        monkeypatch.setenv("REDIS_HOST", "localhost")
        monkeypatch.setenv("REDIS_PORT", "6380")

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.Redis") as mock_redis_class:
            mock_redis_class.return_value.ping.return_value = True
            AlertDeduplicator()

            mock_redis_class.assert_called_once()
            call_kwargs = mock_redis_class.call_args[1]
            assert call_kwargs["port"] == 6380

    def test_defaults_to_localhost_when_no_env(self, monkeypatch: Any) -> None:
        """AlertDeduplicator defaults to localhost:6379 without env vars."""
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.Redis") as mock_redis_class:
            mock_redis_class.return_value.ping.return_value = True
            AlertDeduplicator()

            mock_redis_class.assert_called_once()
            call_kwargs = mock_redis_class.call_args[1]
            assert call_kwargs["host"] == "localhost"
            assert call_kwargs["port"] == 6379

    def test_explicit_params_override_env_vars(self, monkeypatch: Any) -> None:
        """Explicit parameters take precedence over environment variables."""
        monkeypatch.setenv("REDIS_HOST", "env-host")
        monkeypatch.setenv("REDIS_PORT", "9999")

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.Redis") as mock_redis_class:
            mock_redis_class.return_value.ping.return_value = True
            AlertDeduplicator(redis_host="explicit-host", redis_port=7777)

            mock_redis_class.assert_called_once()
            call_kwargs = mock_redis_class.call_args[1]
            assert call_kwargs["host"] == "explicit-host"
            assert call_kwargs["port"] == 7777

    def test_uses_redis_url_env_var(self, monkeypatch: Any) -> None:
        """AlertDeduplicator uses from_url when REDIS_URL is set."""
        redis_url = "redis://my-redis-host:6380/1"
        monkeypatch.setenv("REDIS_URL", redis_url)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            mock_from_url.assert_called_once()
            assert mock_from_url.call_args[0][0] == redis_url

    def test_redis_url_takes_precedence_over_host_port(self, monkeypatch: Any) -> None:
        """REDIS_URL takes precedence over REDIS_HOST/REDIS_PORT."""
        redis_url = "redis://url-host:9999/0"
        monkeypatch.setenv("REDIS_URL", redis_url)
        monkeypatch.setenv("REDIS_HOST", "fallback-host")
        monkeypatch.setenv("REDIS_PORT", "1111")

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            # Should use from_url with REDIS_URL, not REDIS_HOST/PORT
            mock_from_url.assert_called_once()
            assert mock_from_url.call_args[0][0] == redis_url

    def test_redis_url_with_password(self, monkeypatch: Any) -> None:
        """AlertDeduplicator passes full URL to from_url (including password)."""
        redis_url = "redis://:secret123@secure-host:6379/0"
        monkeypatch.setenv("REDIS_URL", redis_url)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            # Password is embedded in URL, passed to from_url
            mock_from_url.assert_called_once()
            assert mock_from_url.call_args[0][0] == redis_url

    def test_redis_url_without_port_uses_default(self, monkeypatch: Any) -> None:
        """REDIS_URL without explicit port is passed as-is to from_url."""
        redis_url = "redis://host-only/0"
        monkeypatch.setenv("REDIS_URL", redis_url)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            mock_from_url.assert_called_once()
            assert mock_from_url.call_args[0][0] == redis_url

    def test_rediss_url_uses_from_url_for_tls(self, monkeypatch: Any) -> None:
        """REDIS_URL with rediss:// scheme uses from_url to preserve TLS."""
        rediss_url = "rediss://default:token123@tls-host.upstash.io:6379/0"
        monkeypatch.setenv("REDIS_URL", rediss_url)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            # Should use from_url to preserve rediss:// scheme
            mock_from_url.assert_called_once()
            call_args = mock_from_url.call_args
            assert call_args[0][0] == rediss_url

    def test_redis_url_with_acl_username(self, monkeypatch: Any) -> None:
        """REDIS_URL with ACL username uses from_url to preserve auth."""
        acl_url = "redis://myuser:mypassword@acl-host:6379/0"
        monkeypatch.setenv("REDIS_URL", acl_url)
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            # Should use from_url to preserve username in ACL auth
            mock_from_url.assert_called_once()
            call_args = mock_from_url.call_args
            assert call_args[0][0] == acl_url

    def test_redis_url_from_url_includes_decode_responses(self, monkeypatch: Any) -> None:
        """from_url call includes decode_responses=True."""
        monkeypatch.setenv("REDIS_URL", "redis://some-host:6379/0")
        monkeypatch.delenv("REDIS_HOST", raising=False)
        monkeypatch.delenv("REDIS_PORT", raising=False)

        with patch("app.engine.adapters.alert.alert_deduplicator.redis.from_url") as mock_from_url:
            mock_from_url.return_value.ping.return_value = True
            AlertDeduplicator()

            call_kwargs = mock_from_url.call_args[1]
            assert call_kwargs.get("decode_responses") is True
