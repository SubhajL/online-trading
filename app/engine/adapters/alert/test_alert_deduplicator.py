import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import asyncio
import redis
import uuid

from app.engine.adapters.alert.alert_deduplicator import AlertDeduplicator
from app.engine.adapters.alert.test_helpers import get_redis_client, is_ci, skip_if_no_service
from typing import Any



class TestAlertDeduplicator:
    @pytest.fixture
    def redis_client(self) -> Any:
        """Get Redis client for testing."""
        client = get_redis_client()
        yield client
        # Cleanup: Clear test keys
        try:
            keys = client.keys("alert:dedup:test:*")
            if keys:
                client.delete(*keys)
        except Exception:
            pass

    @pytest.fixture
    def deduplicator(self) -> Any:
        """Create deduplicator with real or mock Redis."""
        # Use real Redis (available in both local and CI)
        return AlertDeduplicator(ttl_seconds=60)

    def test_is_duplicate_new_key(self, deduplicator: Any) -> None:
        """Test is_duplicate returns False for new keys."""
        skip_if_no_service('redis')(lambda: None)()
        # Use unique key for each test run
        key = f"test:key:{uuid.uuid4().hex[:8]}"

        result = deduplicator.is_duplicate(key)

        assert result is False

    def test_is_duplicate_existing_key(self, deduplicator: Any) -> None:
        """Test is_duplicate returns True for existing keys."""
        skip_if_no_service('redis')(lambda: None)()
        # Use unique key for each test run
        key = f"test:key:{uuid.uuid4().hex[:8]}"

        # Add key first
        deduplicator.add(key)

        result = deduplicator.is_duplicate(key)

        assert result is True

    def test_add_key(self, deduplicator: Any) -> None:
        """Test adding a key to deduplicator."""
        skip_if_no_service('redis')(lambda: None)()
        # Use unique key for each test run
        key = f"test:key:{uuid.uuid4().hex[:8]}"

        deduplicator.add(key)

        # Verify the key was added
        assert deduplicator.is_duplicate(key) is True

    def test_clear_key(self, deduplicator: Any) -> None:
        """Test clearing a key from deduplicator."""
        skip_if_no_service('redis')(lambda: None)()
        # Use unique key for each test run
        key = f"test:key:{uuid.uuid4().hex[:8]}"

        # Add key first
        deduplicator.add(key)
        assert deduplicator.is_duplicate(key) is True

        # Clear it
        deduplicator.clear(key)

        # Verify it's gone
        assert deduplicator.is_duplicate(key) is False

    def test_custom_ttl(self) -> None:
        """Test custom TTL for deduplication."""
        skip_if_no_service('redis')(lambda: None)()
        # Test with 1 second TTL
        dedup = AlertDeduplicator(ttl_seconds=1)
        key = f"test:ttl:{uuid.uuid4().hex[:8]}"

        dedup.add(key)
        assert dedup.is_duplicate(key) is True

        # Wait for TTL to expire
        import time
        time.sleep(1.5)

        # Key should be gone
        assert dedup.is_duplicate(key) is False

    def test_redis_connection_error(self) -> None:
        # Test with invalid Redis connection
        with patch("app.engine.adapters.alert.alert_deduplicator.redis.Redis") as mock_redis_class:
            mock_redis = Mock()
            mock_redis.get.side_effect = Exception("Redis connection error")
            mock_redis_class.return_value = mock_redis

            dedup = AlertDeduplicator(ttl_seconds=60)

            # Should return False on error (allowing alert to be sent)
            result = dedup.is_duplicate("key")
            assert result is False

    @pytest.mark.asyncio
    async def test_async_compatibility(self, deduplicator: Any) -> None:
        """Test async compatibility."""
        skip_if_no_service('redis')(lambda: None)()
        # Test that methods can be used in async context
        key = f"test:async:{uuid.uuid4().hex[:8]}"
        result = await asyncio.to_thread(deduplicator.is_duplicate, key)
        assert isinstance(result, bool)