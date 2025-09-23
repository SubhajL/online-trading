"""Alert deduplication using Redis to prevent duplicate notifications."""

import logging
from typing import Optional

import redis


logger = logging.getLogger(__name__)


class AlertDeduplicator:
    """Deduplicate alerts within a time window using Redis."""

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 1,
        ttl_seconds: int = 60,
        key_prefix: str = "alert:dedup",
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Alert deduplicator connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    def is_duplicate(self, key: str) -> bool:
        """Check if an alert with this key was recently sent."""
        if not self.redis_client:
            # If Redis is down, allow alerts to be sent
            return False

        try:
            full_key = f"{self.key_prefix}:{key}"
            exists = self.redis_client.get(full_key) is not None
            return exists

        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            # On error, allow alert to be sent
            return False

    def add(self, key: str) -> None:
        """Mark an alert as sent."""
        if not self.redis_client:
            return

        try:
            full_key = f"{self.key_prefix}:{key}"
            self.redis_client.setex(full_key, self.ttl_seconds, "1")
            logger.debug(f"Added dedup key: {key}")

        except Exception as e:
            logger.error(f"Error adding dedup key: {e}")

    def clear(self, key: str) -> None:
        """Clear a deduplication key."""
        if not self.redis_client:
            return

        try:
            full_key = f"{self.key_prefix}:{key}"
            self.redis_client.delete(full_key)
            logger.debug(f"Cleared dedup key: {key}")

        except Exception as e:
            logger.error(f"Error clearing dedup key: {e}")