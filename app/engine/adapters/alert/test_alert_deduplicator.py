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
