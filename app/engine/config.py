"""
Centralized configuration management with Pydantic validation.
"""

import os
from typing import Optional, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, Field, validator, SecretStr
from pydantic_settings import BaseSettings


class EventBusConfig(BaseModel):
    """Event bus configuration with validation."""

    max_queue_size: int = Field(default=10000, gt=0)
    num_workers: int = Field(default=4, gt=0)
    enable_persistence: bool = Field(default=False)
    dead_letter_queue_size: int = Field(default=1000, gt=0)

    @validator("max_queue_size")
    def validate_max_queue_size(cls, v):
        if v <= 0:
            raise ValueError("max_queue_size must be positive")
        return v

    @validator("num_workers")
    def validate_num_workers(cls, v):
        if v <= 0:
            raise ValueError("num_workers must be positive")
        return v

    @classmethod
    def from_env(cls) -> "EventBusConfig":
        """Load configuration from environment variables."""
        return cls(
            max_queue_size=int(os.getenv("EVENT_BUS_MAX_QUEUE_SIZE", "10000")),
            num_workers=int(os.getenv("EVENT_BUS_NUM_WORKERS", "4")),
            enable_persistence=os.getenv("EVENT_BUS_ENABLE_PERSISTENCE", "false").lower() == "true",
            dead_letter_queue_size=int(os.getenv("EVENT_BUS_DEAD_LETTER_SIZE", "1000"))
        )


class DatabaseConfig(BaseModel):
    """Database configuration with connection pooling."""

    host: str = Field(default="localhost")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="trading_platform")
    username: str = Field(default="postgres")
    password: SecretStr = Field(default=SecretStr(""))
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0)
    pool_timeout: int = Field(default=30, ge=1)

    @property
    def connection_string(self) -> str:
        """Generate connection string for asyncpg."""
        pwd = self.password.get_secret_value()
        return f"postgresql://{self.username}:{pwd}@{self.host}:{self.port}/{self.database}"


class RedisConfig(BaseModel):
    """Redis configuration."""

    host: str = Field(default="localhost")
    port: int = Field(default=6379, ge=1, le=65535)
    password: Optional[SecretStr] = None
    database: int = Field(default=0, ge=0, le=15)
    max_connections: int = Field(default=10, ge=1)

    @property
    def connection_url(self) -> str:
        """Generate connection URL for Redis."""
        if self.password:
            pwd = self.password.get_secret_value()
            return f"redis://:{pwd}@{self.host}:{self.port}/{self.database}"
        return f"redis://{self.host}:{self.port}/{self.database}"


class VaultConfig(BaseModel):
    """HashiCorp Vault configuration."""

    url: str = Field(default="http://localhost:8200")
    token: Optional[SecretStr] = None
    namespace: Optional[str] = None
    mount_point: str = Field(default="secret")
    transit_mount: str = Field(default="transit")
    key_name: str = Field(default="trading-platform")

    @classmethod
    def from_env(cls) -> "VaultConfig":
        """Load Vault configuration from environment."""
        token = os.getenv("VAULT_TOKEN")
        return cls(
            url=os.getenv("VAULT_ADDR", "http://localhost:8200"),
            token=SecretStr(token) if token else None,
            namespace=os.getenv("VAULT_NAMESPACE"),
            mount_point=os.getenv("VAULT_MOUNT_POINT", "secret"),
            transit_mount=os.getenv("VAULT_TRANSIT_MOUNT", "transit"),
            key_name=os.getenv("VAULT_KEY_NAME", "trading-platform")
        )


class SecurityConfig(BaseModel):
    """Security configuration."""

    enable_vault: bool = Field(default=True)
    enable_encryption: bool = Field(default=True)
    api_key_rotation_days: int = Field(default=30, ge=1)
    max_failed_auth_attempts: int = Field(default=5, ge=1)
    jwt_secret: Optional[SecretStr] = None
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiry_seconds: int = Field(default=3600, ge=60)


class ObservabilityConfig(BaseModel):
    """Monitoring and observability configuration."""

    enable_metrics: bool = Field(default=True)
    enable_tracing: bool = Field(default=True)
    enable_logging: bool = Field(default=True)

    metrics_port: int = Field(default=8000, ge=1024, le=65535)
    jaeger_endpoint: str = Field(default="http://localhost:14268/api/traces")
    log_level: str = Field(default="INFO")
    structured_logging: bool = Field(default=True)

    health_check_interval: int = Field(default=30, ge=1)
    slo_targets: Dict[str, float] = Field(default_factory=lambda: {
        "availability": 0.999,
        "latency_p99": 1.0,
        "error_rate": 0.001
    })


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration."""

    failure_threshold: int = Field(default=5, ge=1)
    success_threshold: int = Field(default=2, ge=1)
    timeout_seconds: int = Field(default=60, ge=1)
    half_open_requests: int = Field(default=3, ge=1)


class RateLimiterConfig(BaseModel):
    """Rate limiter configuration."""

    requests_per_second: float = Field(default=10.0, gt=0)
    burst_size: int = Field(default=20, ge=1)

    binance_spot_rps: float = Field(default=20.0, gt=0)
    binance_futures_rps: float = Field(default=20.0, gt=0)


class AppConfig(BaseSettings):
    """Main application configuration."""

    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    rate_limiter: RateLimiterConfig = Field(default_factory=RateLimiterConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"

    @classmethod
    def load_from_env(cls) -> "AppConfig":
        """Load complete configuration from environment."""
        return cls(
            environment=os.getenv("ENVIRONMENT", "development"),
            debug=os.getenv("DEBUG", "false").lower() == "true",
            event_bus=EventBusConfig.from_env(),
            vault=VaultConfig.from_env()
        )

    def validate_secrets(self) -> None:
        """Validate that all required secrets are present."""
        if self.environment == "production":
            if not self.database.password.get_secret_value():
                raise ValueError("Database password required in production")
            if self.security.enable_vault and not self.vault.token:
                raise ValueError("Vault token required when Vault is enabled")
            if not self.security.jwt_secret:
                raise ValueError("JWT secret required for authentication")