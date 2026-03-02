"""Alert deduplication using Redis to prevent duplicate notifications."""

import logging
import os
import urllib.parse

import redis

logger = logging.getLogger(__name__)


class AlertDeduplicator:
    """Deduplicate alerts within a time window using Redis.

    Supports multiple Redis configuration methods (in order of precedence):
    1. Explicit redis_host/redis_port parameters
    2. REDIS_URL environment variable (supports redis://, rediss:// for TLS, ACL usernames)
    3. REDIS_HOST/REDIS_PORT environment variables
    """

    def __init__(
        self,
        redis_host: str | None = None,
        redis_port: int | None = None,
        redis_db: int = 1,
        ttl_seconds: int = 60,
        key_prefix: str = "alert:dedup",
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

        try:
            # Explicit parameters take precedence - use Redis() directly
            if redis_host is not None or redis_port is not None:
                host = redis_host if redis_host is not None else "localhost"
                port = redis_port if redis_port is not None else 6379
                self.redis_client = redis.Redis(
                    host=host,
                    port=port,
                    db=redis_db,
                    decode_responses=True,
                )
                self.redis_client.ping()
                logger.info("Alert deduplicator connected to Redis at %s:%d", host, port)
                return

            # Try REDIS_URL - use from_url to preserve scheme (rediss://), ACL username, etc.
            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                self.redis_client = redis.from_url(
                    redis_url,
                    db=redis_db,
                    decode_responses=True,
                )
                self.redis_client.ping()
                # Extract host for logging (don't log password)
                parsed = urllib.parse.urlparse(redis_url)
                logger.info(
                    "Alert deduplicator connected to Redis via URL at %s:%d",
                    parsed.hostname or "unknown",
                    parsed.port or 6379,
                )
                return

            # Fall back to REDIS_HOST/REDIS_PORT
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=redis_db,
                decode_responses=True,
            )
            self.redis_client.ping()
            logger.info("Alert deduplicator connected to Redis at %s:%d", host, port)

        except Exception as e:
            logger.exception("Failed to connect to Redis: %s", e)
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

    def reserve(self, key: str) -> bool:
        """Atomically reserve a deduplication key.

        Returns True if the key was newly reserved (caller should proceed with sending),
        or False if the key already existed (caller should treat as duplicate).

        If Redis is unavailable, returns True (fail-open for alert delivery).
        """
        if not self.redis_client:
            return True

        try:
            full_key = f"{self.key_prefix}:{key}"
            result = self.redis_client.set(full_key, "1", ex=self.ttl_seconds, nx=True)
            return result is True
        except Exception as e:
            logger.error(f"Error reserving dedup key: {e}")
            return True

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
