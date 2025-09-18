"""
Redis Adapter

Redis adapter for caching, session management, and real-time data storage.
Provides high-performance caching for trading data and coordination between services.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager

import aioredis
from aioredis import Redis

from ...types import Candle, TechnicalIndicators, SMCSignal, TimeFrame


logger = logging.getLogger(__name__)


class RedisAdapter:
    """
    Redis adapter for caching and real-time data operations.

    Features:
    - Connection pooling
    - JSON serialization with Decimal support
    - Key expiration management
    - Pub/Sub messaging
    - Health monitoring
    - Batch operations
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        database: int = 0,
        max_connections: int = 10,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
        retry_on_timeout: bool = True,
        decode_responses: bool = False
    ):
        self.host = host
        self.port = port
        self.password = password
        self.database = database
        self.max_connections = max_connections
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.decode_responses = decode_responses

        self._redis: Optional[Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._initialized = False

        # Key prefixes for different data types
        self.KEY_PREFIXES = {
            "candle": "candle:",
            "indicator": "indicator:",
            "signal": "signal:",
            "zone": "zone:",
            "decision": "decision:",
            "session": "session:",
            "cache": "cache:",
            "health": "health:",
            "metrics": "metrics:"
        }

        logger.info(f"RedisAdapter configured for {host}:{port}/{database}")

    async def initialize(self):
        """Initialize Redis connection"""
        if self._initialized:
            return

        try:
            connection_params = {
                "host": self.host,
                "port": self.port,
                "db": self.database,
                "max_connections": self.max_connections,
                "socket_timeout": self.socket_timeout,
                "socket_connect_timeout": self.socket_connect_timeout,
                "retry_on_timeout": self.retry_on_timeout,
                "decode_responses": self.decode_responses
            }

            if self.password:
                connection_params["password"] = self.password

            self._redis = aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.database}",
                **{k: v for k, v in connection_params.items() if k not in ["host", "port", "db"]}
            )

            # Test connection
            await self._redis.ping()

            self._initialized = True
            logger.info("Redis adapter initialized successfully")

        except Exception as e:
            logger.error(f"Error initializing Redis adapter: {e}")
            raise

    async def close(self):
        """Close Redis connection"""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None

        if self._redis:
            await self._redis.close()
            self._redis = None

        self._initialized = False
        logger.info("Redis adapter closed")

    def _ensure_connected(self):
        """Ensure Redis is connected"""
        if not self._initialized or not self._redis:
            raise RuntimeError("Redis not initialized")

    def _serialize_value(self, value: Any) -> str:
        """Serialize value to JSON string with Decimal support"""
        def decimal_encoder(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(value, default=decimal_encoder, separators=(',', ':'))

    def _deserialize_value(self, value: str) -> Any:
        """Deserialize JSON string to Python object"""
        if not value:
            return None
        return json.loads(value)

    def _build_key(self, prefix: str, *parts: str) -> str:
        """Build Redis key with prefix and parts"""
        key_prefix = self.KEY_PREFIXES.get(prefix, f"{prefix}:")
        return key_prefix + ":".join(str(part) for part in parts)

    # ============================================================================
    # Basic Key-Value Operations
    # ============================================================================

    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None,
        prefix: str = "cache"
    ) -> bool:
        """Set a key-value pair with optional expiration"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, key)
            serialized_value = self._serialize_value(value)

            if expire:
                result = await self._redis.setex(redis_key, expire, serialized_value)
            else:
                result = await self._redis.set(redis_key, serialized_value)

            return bool(result)

        except Exception as e:
            logger.error(f"Error setting key {key}: {e}")
            return False

    async def get(self, key: str, prefix: str = "cache") -> Optional[Any]:
        """Get value by key"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, key)
            value = await self._redis.get(redis_key)

            if value is None:
                return None

            return self._deserialize_value(value.decode() if isinstance(value, bytes) else value)

        except Exception as e:
            logger.error(f"Error getting key {key}: {e}")
            return None

    async def delete(self, key: str, prefix: str = "cache") -> bool:
        """Delete a key"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, key)
            result = await self._redis.delete(redis_key)
            return bool(result)

        except Exception as e:
            logger.error(f"Error deleting key {key}: {e}")
            return False

    async def exists(self, key: str, prefix: str = "cache") -> bool:
        """Check if key exists"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, key)
            result = await self._redis.exists(redis_key)
            return bool(result)

        except Exception as e:
            logger.error(f"Error checking key existence {key}: {e}")
            return False

    async def expire(self, key: str, seconds: int, prefix: str = "cache") -> bool:
        """Set expiration for a key"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, key)
            result = await self._redis.expire(redis_key, seconds)
            return bool(result)

        except Exception as e:
            logger.error(f"Error setting expiration for key {key}: {e}")
            return False

    # ============================================================================
    # Hash Operations
    # ============================================================================

    async def hset(
        self,
        hash_key: str,
        field: str,
        value: Any,
        prefix: str = "cache"
    ) -> bool:
        """Set field in hash"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, hash_key)
            serialized_value = self._serialize_value(value)
            result = await self._redis.hset(redis_key, field, serialized_value)
            return bool(result)

        except Exception as e:
            logger.error(f"Error setting hash field {hash_key}:{field}: {e}")
            return False

    async def hget(
        self,
        hash_key: str,
        field: str,
        prefix: str = "cache"
    ) -> Optional[Any]:
        """Get field from hash"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, hash_key)
            value = await self._redis.hget(redis_key, field)

            if value is None:
                return None

            return self._deserialize_value(value.decode() if isinstance(value, bytes) else value)

        except Exception as e:
            logger.error(f"Error getting hash field {hash_key}:{field}: {e}")
            return None

    async def hgetall(self, hash_key: str, prefix: str = "cache") -> Dict[str, Any]:
        """Get all fields from hash"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, hash_key)
            result = await self._redis.hgetall(redis_key)

            if not result:
                return {}

            # Deserialize all values
            deserialized = {}
            for field, value in result.items():
                field_str = field.decode() if isinstance(field, bytes) else field
                value_str = value.decode() if isinstance(value, bytes) else value
                deserialized[field_str] = self._deserialize_value(value_str)

            return deserialized

        except Exception as e:
            logger.error(f"Error getting all hash fields {hash_key}: {e}")
            return {}

    async def hdel(self, hash_key: str, field: str, prefix: str = "cache") -> bool:
        """Delete field from hash"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, hash_key)
            result = await self._redis.hdel(redis_key, field)
            return bool(result)

        except Exception as e:
            logger.error(f"Error deleting hash field {hash_key}:{field}: {e}")
            return False

    # ============================================================================
    # List Operations
    # ============================================================================

    async def lpush(self, list_key: str, value: Any, prefix: str = "cache") -> int:
        """Push value to the left of list"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, list_key)
            serialized_value = self._serialize_value(value)
            result = await self._redis.lpush(redis_key, serialized_value)
            return int(result)

        except Exception as e:
            logger.error(f"Error pushing to list {list_key}: {e}")
            return 0

    async def rpush(self, list_key: str, value: Any, prefix: str = "cache") -> int:
        """Push value to the right of list"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, list_key)
            serialized_value = self._serialize_value(value)
            result = await self._redis.rpush(redis_key, serialized_value)
            return int(result)

        except Exception as e:
            logger.error(f"Error pushing to list {list_key}: {e}")
            return 0

    async def lpop(self, list_key: str, prefix: str = "cache") -> Optional[Any]:
        """Pop value from the left of list"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, list_key)
            value = await self._redis.lpop(redis_key)

            if value is None:
                return None

            return self._deserialize_value(value.decode() if isinstance(value, bytes) else value)

        except Exception as e:
            logger.error(f"Error popping from list {list_key}: {e}")
            return None

    async def lrange(
        self,
        list_key: str,
        start: int = 0,
        end: int = -1,
        prefix: str = "cache"
    ) -> List[Any]:
        """Get range of values from list"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, list_key)
            values = await self._redis.lrange(redis_key, start, end)

            result = []
            for value in values:
                value_str = value.decode() if isinstance(value, bytes) else value
                result.append(self._deserialize_value(value_str))

            return result

        except Exception as e:
            logger.error(f"Error getting list range {list_key}: {e}")
            return []

    async def ltrim(self, list_key: str, start: int, end: int, prefix: str = "cache") -> bool:
        """Trim list to specified range"""
        self._ensure_connected()

        try:
            redis_key = self._build_key(prefix, list_key)
            result = await self._redis.ltrim(redis_key, start, end)
            return bool(result)

        except Exception as e:
            logger.error(f"Error trimming list {list_key}: {e}")
            return False

    # ============================================================================
    # Trading Data Specific Operations
    # ============================================================================

    async def cache_candle(
        self,
        candle: Candle,
        expire_seconds: int = 3600
    ) -> bool:
        """Cache a candle with expiration"""
        key = f"{candle.symbol}:{candle.timeframe.value}:{int(candle.open_time.timestamp())}"
        candle_data = {
            "symbol": candle.symbol,
            "timeframe": candle.timeframe.value,
            "open_time": candle.open_time.isoformat(),
            "close_time": candle.close_time.isoformat(),
            "open_price": candle.open_price,
            "high_price": candle.high_price,
            "low_price": candle.low_price,
            "close_price": candle.close_price,
            "volume": candle.volume,
            "quote_volume": candle.quote_volume,
            "trades": candle.trades,
            "taker_buy_base_volume": candle.taker_buy_base_volume,
            "taker_buy_quote_volume": candle.taker_buy_quote_volume
        }

        return await self.set(key, candle_data, expire=expire_seconds, prefix="candle")

    async def get_cached_candle(
        self,
        symbol: str,
        timeframe: TimeFrame,
        timestamp: datetime
    ) -> Optional[Candle]:
        """Get cached candle"""
        key = f"{symbol}:{timeframe.value}:{int(timestamp.timestamp())}"
        data = await self.get(key, prefix="candle")

        if not data:
            return None

        try:
            return Candle(
                symbol=data["symbol"],
                timeframe=TimeFrame(data["timeframe"]),
                open_time=datetime.fromisoformat(data["open_time"]),
                close_time=datetime.fromisoformat(data["close_time"]),
                open_price=Decimal(str(data["open_price"])),
                high_price=Decimal(str(data["high_price"])),
                low_price=Decimal(str(data["low_price"])),
                close_price=Decimal(str(data["close_price"])),
                volume=Decimal(str(data["volume"])),
                quote_volume=Decimal(str(data["quote_volume"])),
                trades=data["trades"],
                taker_buy_base_volume=Decimal(str(data["taker_buy_base_volume"])),
                taker_buy_quote_volume=Decimal(str(data["taker_buy_quote_volume"]))
            )

        except Exception as e:
            logger.error(f"Error deserializing cached candle: {e}")
            return None

    async def cache_latest_indicators(
        self,
        indicators: TechnicalIndicators,
        expire_seconds: int = 300
    ) -> bool:
        """Cache latest technical indicators"""
        key = f"{indicators.symbol}:{indicators.timeframe.value}:latest"
        indicators_data = {
            "symbol": indicators.symbol,
            "timeframe": indicators.timeframe.value,
            "timestamp": indicators.timestamp.isoformat(),
            "ema_9": indicators.ema_9,
            "ema_21": indicators.ema_21,
            "ema_50": indicators.ema_50,
            "ema_200": indicators.ema_200,
            "rsi_14": indicators.rsi_14,
            "macd_line": indicators.macd_line,
            "macd_signal": indicators.macd_signal,
            "macd_histogram": indicators.macd_histogram,
            "atr_14": indicators.atr_14,
            "bb_upper": indicators.bb_upper,
            "bb_middle": indicators.bb_middle,
            "bb_lower": indicators.bb_lower,
            "bb_width": indicators.bb_width,
            "bb_percent": indicators.bb_percent
        }

        return await self.set(key, indicators_data, expire=expire_seconds, prefix="indicator")

    async def get_latest_indicators(
        self,
        symbol: str,
        timeframe: TimeFrame
    ) -> Optional[TechnicalIndicators]:
        """Get latest cached technical indicators"""
        key = f"{symbol}:{timeframe.value}:latest"
        data = await self.get(key, prefix="indicator")

        if not data:
            return None

        try:
            return TechnicalIndicators(
                symbol=data["symbol"],
                timeframe=TimeFrame(data["timeframe"]),
                timestamp=datetime.fromisoformat(data["timestamp"]),
                ema_9=Decimal(str(data["ema_9"])) if data["ema_9"] else None,
                ema_21=Decimal(str(data["ema_21"])) if data["ema_21"] else None,
                ema_50=Decimal(str(data["ema_50"])) if data["ema_50"] else None,
                ema_200=Decimal(str(data["ema_200"])) if data["ema_200"] else None,
                rsi_14=Decimal(str(data["rsi_14"])) if data["rsi_14"] else None,
                macd_line=Decimal(str(data["macd_line"])) if data["macd_line"] else None,
                macd_signal=Decimal(str(data["macd_signal"])) if data["macd_signal"] else None,
                macd_histogram=Decimal(str(data["macd_histogram"])) if data["macd_histogram"] else None,
                atr_14=Decimal(str(data["atr_14"])) if data["atr_14"] else None,
                bb_upper=Decimal(str(data["bb_upper"])) if data["bb_upper"] else None,
                bb_middle=Decimal(str(data["bb_middle"])) if data["bb_middle"] else None,
                bb_lower=Decimal(str(data["bb_lower"])) if data["bb_lower"] else None,
                bb_width=Decimal(str(data["bb_width"])) if data["bb_width"] else None,
                bb_percent=Decimal(str(data["bb_percent"])) if data["bb_percent"] else None
            )

        except Exception as e:
            logger.error(f"Error deserializing cached indicators: {e}")
            return None

    # ============================================================================
    # Pub/Sub Operations
    # ============================================================================

    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
        self._ensure_connected()

        try:
            serialized_message = self._serialize_value(message)
            result = await self._redis.publish(channel, serialized_message)
            return int(result)

        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}")
            return 0

    async def subscribe(self, *channels: str):
        """Subscribe to channels"""
        self._ensure_connected()

        try:
            if not self._pubsub:
                self._pubsub = self._redis.pubsub()

            await self._pubsub.subscribe(*channels)
            return self._pubsub

        except Exception as e:
            logger.error(f"Error subscribing to channels {channels}: {e}")
            return None

    async def unsubscribe(self, *channels: str):
        """Unsubscribe from channels"""
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(*channels)
            except Exception as e:
                logger.error(f"Error unsubscribing from channels {channels}: {e}")

    # ============================================================================
    # Batch Operations
    # ============================================================================

    async def mget(self, keys: List[str], prefix: str = "cache") -> List[Optional[Any]]:
        """Get multiple keys"""
        self._ensure_connected()

        try:
            redis_keys = [self._build_key(prefix, key) for key in keys]
            values = await self._redis.mget(*redis_keys)

            result = []
            for value in values:
                if value is None:
                    result.append(None)
                else:
                    value_str = value.decode() if isinstance(value, bytes) else value
                    result.append(self._deserialize_value(value_str))

            return result

        except Exception as e:
            logger.error(f"Error getting multiple keys: {e}")
            return [None] * len(keys)

    async def mset(self, key_value_pairs: Dict[str, Any], prefix: str = "cache") -> bool:
        """Set multiple key-value pairs"""
        self._ensure_connected()

        try:
            redis_pairs = {}
            for key, value in key_value_pairs.items():
                redis_key = self._build_key(prefix, key)
                redis_pairs[redis_key] = self._serialize_value(value)

            result = await self._redis.mset(redis_pairs)
            return bool(result)

        except Exception as e:
            logger.error(f"Error setting multiple keys: {e}")
            return False

    # ============================================================================
    # Health and Monitoring
    # ============================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check"""
        try:
            self._ensure_connected()

            # Test ping
            ping_result = await self._redis.ping()

            # Get Redis info
            info = await self._redis.info()

            # Get database size
            dbsize = await self._redis.dbsize()

            return {
                "status": "healthy" if ping_result else "unhealthy",
                "ping": ping_result,
                "database_size": dbsize,
                "memory_usage": info.get("used_memory_human", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    async def get_key_count(self, pattern: str = "*") -> int:
        """Get count of keys matching pattern"""
        try:
            self._ensure_connected()
            keys = await self._redis.keys(pattern)
            return len(keys)

        except Exception as e:
            logger.error(f"Error getting key count: {e}")
            return 0

    async def clear_cache(self, prefix: Optional[str] = None) -> int:
        """Clear cache with optional prefix filter"""
        try:
            self._ensure_connected()

            if prefix:
                pattern = self._build_key(prefix, "*")
                keys = await self._redis.keys(pattern)
                if keys:
                    return await self._redis.delete(*keys)
                return 0
            else:
                # Clear entire database
                result = await self._redis.flushdb()
                return 1 if result else 0

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0

    # ============================================================================
    # Context Manager Support
    # ============================================================================

    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()