"""
Configuration management for production trading engine.
Following C-4: Prefer simple, composable, testable functions.
"""

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass
class Config:
    """Application configuration."""

    # Database settings
    database_url: str = "postgresql://localhost/trading"
    max_connections: int = 20
    connection_timeout: int = 30

    # Redis settings
    redis_url: str = "redis://localhost:6379"
    redis_pool_size: int = 10

    # Trading settings
    risk_limit: float = 0.02
    max_position_size: float = 100000
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])

    # System settings
    environment: str = "development"
    debug_mode: bool = False
    log_level: str = "INFO"

    # Performance settings
    event_queue_size: int = 10000
    worker_threads: int = 4

    # Monitoring
    metrics_port: int = 9090
    health_check_interval: int = 30


@dataclass
class ConfigWatcher:
    """Watches for config changes."""

    current_config: Config
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reload(self) -> Config:
        """Atomically reload configuration."""
        with self.lock:
            try:
                # Load new config
                new_config = load_config_from_env()

                # Validate
                validate_config_schema(new_config.__dict__)

                # Update atomically
                self.current_config = new_config
                logger.info("Configuration reloaded successfully")
                return new_config

            except Exception as e:
                logger.error(f"Failed to reload config: {e}")
                raise ConfigError(f"Config reload failed: {e}")


def load_config_from_env() -> Config:
    """
    Parse environment variables with type coercion.
    Follows 12-factor app principles.
    Uses TRADING_ prefix for all env vars.
    """
    config = Config()

    # Parse environment variables
    if "TRADING_DATABASE_URL" in os.environ:
        config.database_url = os.environ["TRADING_DATABASE_URL"]

    if "TRADING_REDIS_URL" in os.environ:
        config.redis_url = os.environ["TRADING_REDIS_URL"]

    if "TRADING_MAX_CONNECTIONS" in os.environ:
        value = int(os.environ["TRADING_MAX_CONNECTIONS"])
        if value <= 0:
            raise ConfigError("max_connections must be positive")
        config.max_connections = value

    if "TRADING_RISK_LIMIT" in os.environ:
        config.risk_limit = float(os.environ["TRADING_RISK_LIMIT"])

    if "TRADING_DEBUG_MODE" in os.environ:
        value = os.environ["TRADING_DEBUG_MODE"].lower()
        config.debug_mode = value in ("true", "1", "yes", "on")

    if "TRADING_SYMBOLS" in os.environ:
        symbols_str = os.environ["TRADING_SYMBOLS"]
        config.symbols = [s.strip() for s in symbols_str.split(",")]

    if "TRADING_ENVIRONMENT" in os.environ:
        config.environment = os.environ["TRADING_ENVIRONMENT"]

    if "TRADING_LOG_LEVEL" in os.environ:
        config.log_level = os.environ["TRADING_LOG_LEVEL"]

    if "TRADING_EVENT_QUEUE_SIZE" in os.environ:
        config.event_queue_size = int(os.environ["TRADING_EVENT_QUEUE_SIZE"])

    if "TRADING_WORKER_THREADS" in os.environ:
        config.worker_threads = int(os.environ["TRADING_WORKER_THREADS"])

    return config


def validate_config_schema(config_dict: Dict[str, Any]) -> None:
    """
    Ensure all required fields present.
    Validate ranges/formats.
    Check interdependencies.
    """
    # Check required fields
    required_fields = ["database_url", "redis_url", "max_connections", "risk_limit"]
    for field in required_fields:
        if field not in config_dict:
            raise ConfigError(f"Required field '{field}' is missing")

    # Type validation
    if not isinstance(config_dict.get("max_connections"), int):
        raise ConfigError("max_connections type error: must be an integer")

    # Range validation
    risk_limit = config_dict.get("risk_limit", 0)
    if not 0 < risk_limit <= 1:
        raise ConfigError(f"risk_limit must be between 0 and 1, got {risk_limit}")

    max_connections = config_dict.get("max_connections", 0)
    if max_connections <= 0:
        raise ConfigError(f"max_connections must be positive, got {max_connections}")

    # Production constraints
    if config_dict.get("environment") == "production":
        # Stricter limits in production
        if max_connections < 20:
            raise ConfigError("Production requires at least 20 connections")

        if risk_limit > 0.02:
            raise ConfigError("Production risk_limit cannot exceed 0.02")

        if config_dict.get("debug_mode", False):
            raise ConfigError("Debug mode cannot be enabled in production")

        if "localhost" in config_dict.get("database_url", ""):
            raise ConfigError("Production cannot use localhost database")


def merge_config_sources(
    defaults: Dict[str, Any],
    file_config: Optional[Dict[str, Any]] = None,
    env_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combine env vars, config files, and defaults.
    Precedence: env > file > defaults.
    Handles nested dictionaries.
    """

    def deep_merge(base: Dict, override: Dict) -> Dict:
        """Recursively merge dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dicts
                result[key] = deep_merge(result[key], value)
            else:
                # Override value
                result[key] = value

        return result

    # Start with defaults
    merged = defaults.copy()

    # Apply file config
    if file_config:
        merged = deep_merge(merged, file_config)

    # Apply env config (highest priority)
    if env_config:
        merged = deep_merge(merged, env_config)

    return merged


def get_config_for_environment(environment: str) -> Config:
    """
    Return environment-specific config.
    Applies appropriate defaults and constraints.
    """
    config = Config()
    config.environment = environment

    if environment == "development":
        # Relaxed settings for development
        config.debug_mode = True
        config.risk_limit = 0.05
        config.max_connections = 5
        config.log_level = "DEBUG"

    elif environment == "staging":
        # Production-like but slightly relaxed
        config.debug_mode = False
        config.risk_limit = 0.03
        config.max_connections = 15
        config.log_level = "INFO"
        config.database_url = "postgresql://staging.db.internal/trading"
        config.redis_url = "redis://staging.redis.internal:6379"

    elif environment == "production":
        # Strict production settings
        config.debug_mode = False
        config.risk_limit = 0.02
        config.max_connections = 50
        config.log_level = "WARNING"
        config.database_url = "postgresql://prod.db.internal/trading"
        config.redis_url = "redis://prod.redis.internal:6379"
        config.event_queue_size = 50000
        config.worker_threads = 8

    else:
        raise ConfigError(f"Unknown environment: {environment}")

    return config


def watch_config_changes(initial_config: Config) -> ConfigWatcher:
    """
    Monitor for config updates.
    Triggers safe reloads without dropping connections.
    Returns a watcher that can reload config atomically.
    """
    watcher = ConfigWatcher(current_config=initial_config)

    # In production, could set up file watchers, signals, or polling
    # For now, return the watcher which supports manual reload

    logger.info(f"Config watcher initialized for {initial_config.environment}")
    return watcher


def export_config_schema() -> Dict[str, Any]:
    """
    Generate JSON schema for config validation.
    Includes documentation, examples, and constraints.
    """
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Trading Engine Configuration",
        "type": "object",
        "properties": {
            "database_url": {
                "type": "string",
                "description": "PostgreSQL connection URL",
                "format": "uri",
                "examples": ["postgresql://user:pass@host:5432/trading"],
            },
            "redis_url": {
                "type": "string",
                "description": "Redis connection URL",
                "format": "uri",
                "examples": ["redis://localhost:6379"],
            },
            "max_connections": {
                "type": "integer",
                "description": "Maximum database connection pool size",
                "minimum": 1,
                "maximum": 1000,
                "default": 20,
            },
            "risk_limit": {
                "type": "number",
                "description": "Maximum risk per trade as fraction of capital",
                "minimum": 0.001,
                "maximum": 1.0,
                "default": 0.02,
            },
            "debug_mode": {
                "type": "boolean",
                "description": "Enable debug logging and diagnostics",
                "default": False,
            },
            "environment": {
                "type": "string",
                "description": "Deployment environment",
                "enum": ["development", "staging", "production"],
                "default": "development",
            },
            "symbols": {
                "type": "array",
                "description": "Trading symbols to monitor",
                "items": {"type": "string"},
                "examples": [["BTCUSDT", "ETHUSDT"]],
            },
            "event_queue_size": {
                "type": "integer",
                "description": "Maximum events in processing queue",
                "minimum": 100,
                "maximum": 100000,
                "default": 10000,
            },
            "worker_threads": {
                "type": "integer",
                "description": "Number of worker threads for processing",
                "minimum": 1,
                "maximum": 32,
                "default": 4,
            },
        },
        "required": ["database_url", "redis_url", "max_connections", "risk_limit"],
        "additionalProperties": False,
        "examples": [
            {
                "database_url": "postgresql://trading:secret@db.internal:5432/trading",
                "redis_url": "redis://redis.internal:6379",
                "max_connections": 50,
                "risk_limit": 0.02,
                "environment": "production",
                "debug_mode": False,
                "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
                "event_queue_size": 50000,
                "worker_threads": 8,
            }
        ],
    }

    return schema
