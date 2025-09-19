"""
Factory for creating EventBus instances with dependency injection.
Provides flexible configuration and testing support.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional
from unittest.mock import Mock, AsyncMock
import os

from app.engine.core.interfaces import (
    EventBusInterface,
    SubscriptionManagerInterface,
    EventProcessorInterface
)

if TYPE_CHECKING:
    from app.engine.bus_refactored import EventBus
from app.engine.core.subscription_manager import SubscriptionManager, SubscriptionConfig
from app.engine.core.event_processor import EventProcessor, EventProcessingConfig
from app.engine.core.security import SecureConfig, SecurityLevel, validate_environment


class InvalidConfigurationError(Exception):
    """Raised when configuration is invalid."""
    pass


@dataclass
class EventBusConfig:
    """Configuration for EventBus creation."""
    max_queue_size: int = 10000
    num_workers: int = 4
    enable_persistence: bool = False
    dead_letter_queue_size: int = 1000
    subscription_config: Optional[Dict[str, Any]] = None
    processing_config: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")

        if self.max_queue_size > 100000:
            raise ValueError("max_queue_size too large (max 100000)")

        if self.num_workers <= 0:
            raise ValueError("num_workers must be positive")

        if self.num_workers > 50:
            raise ValueError("num_workers too large (max 50)")

        if self.dead_letter_queue_size < 0:
            raise ValueError("dead_letter_queue_size must be non-negative")

    @classmethod
    def from_secure_config(cls, secure_config: Optional[SecureConfig] = None) -> 'EventBusConfig':
        """Create configuration from secure config with validation."""
        if not secure_config:
            # Determine security level from environment
            env = os.getenv('ENVIRONMENT', 'development').lower()
            security_level = SecurityLevel.PRODUCTION if env == 'production' else SecurityLevel.DEVELOPMENT
            secure_config = SecureConfig(security_level)

        # Validate environment before loading
        audit = secure_config.audit()
        if audit.security_score < 0.5 and secure_config.security_level == SecurityLevel.PRODUCTION:
            raise InvalidConfigurationError(
                f"Security audit failed with score {audit.security_score}. "
                f"Missing required: {', '.join(audit.missing_required)}"
            )

        return cls(
            max_queue_size=int(secure_config.get('EVENT_BUS_MAX_QUEUE_SIZE', 10000)),
            num_workers=int(secure_config.get('EVENT_BUS_NUM_WORKERS', 4)),
            enable_persistence=secure_config.get('EVENT_BUS_ENABLE_PERSISTENCE', 'false').lower() == 'true',
            dead_letter_queue_size=int(secure_config.get('EVENT_BUS_DEAD_LETTER_SIZE', 1000)),
            subscription_config=cls._load_subscription_config(secure_config),
            processing_config=cls._load_processing_config(secure_config)
        )

    @staticmethod
    def _load_subscription_config(secure_config: SecureConfig) -> Dict[str, Any]:
        """Load subscription configuration from secure config."""
        return {
            'max_subscriptions': int(secure_config.get('SUBSCRIPTION_MAX_COUNT', 1000)),
            'default_priority': int(secure_config.get('SUBSCRIPTION_DEFAULT_PRIORITY', 0)),
            'default_max_retries': int(secure_config.get('SUBSCRIPTION_DEFAULT_RETRIES', 3))
        }

    @staticmethod
    def _load_processing_config(secure_config: SecureConfig) -> Dict[str, Any]:
        """Load processing configuration from secure config."""
        return {
            'max_processing_time_seconds': float(secure_config.get('PROCESSING_MAX_TIME', 30.0)),
            'max_concurrent_handlers': int(secure_config.get('PROCESSING_MAX_CONCURRENT', 10)),
            'circuit_breaker_enabled': secure_config.get('CIRCUIT_BREAKER_ENABLED', 'true').lower() == 'true'
        }


class EventBusFactory:
    """
    Factory for creating EventBus instances with proper dependency injection.

    Supports default configurations, custom configurations, and testing mocks.
    """

    def create_event_bus(self) -> 'EventBus':
        """
        Create EventBus with default configuration.

        Returns:
            EventBus instance with default components
        """
        config = EventBusConfig()
        return self.create_with_config(config)

    def create_secure_event_bus(self, security_level: Optional[SecurityLevel] = None) -> 'EventBus':
        """
        Create EventBus with secure configuration and validation.

        Args:
            security_level: Security level for validation (auto-detected if not provided)

        Returns:
            EventBus instance with validated secure configuration

        Raises:
            InvalidConfigurationError: If security validation fails
        """
        # Create secure config with validation
        if security_level is None:
            env = os.getenv('ENVIRONMENT', 'development').lower()
            security_level = SecurityLevel.PRODUCTION if env == 'production' else SecurityLevel.DEVELOPMENT

        secure_config = SecureConfig(security_level)

        # Create EventBus config from secure config
        config = EventBusConfig.from_secure_config(secure_config)

        return self.create_with_config(config)

    def create_with_config(self, config: EventBusConfig) -> 'EventBus':
        """
        Create EventBus with custom configuration.

        Args:
            config: EventBus configuration

        Returns:
            EventBus instance with configured components

        Raises:
            InvalidConfigurationError: If configuration is invalid
        """
        if config is None:
            raise InvalidConfigurationError("Configuration cannot be None")

        try:
            # Create subscription manager with custom config
            subscription_config = SubscriptionConfig()
            if config.subscription_config:
                for key, value in config.subscription_config.items():
                    if hasattr(subscription_config, key):
                        setattr(subscription_config, key, value)

            subscription_manager = SubscriptionManager(subscription_config)

            # Create event processor with custom config
            processing_config = EventProcessingConfig()
            if config.processing_config:
                for key, value in config.processing_config.items():
                    if hasattr(processing_config, key):
                        setattr(processing_config, key, value)

            event_processor = EventProcessor(processing_config)

            return self.create_with_dependencies(
                subscription_manager=subscription_manager,
                event_processor=event_processor,
                config=config
            )

        except Exception as e:
            if isinstance(e, (ValueError, InvalidConfigurationError)):
                raise
            raise InvalidConfigurationError(f"Failed to create EventBus: {e}")

    def create_for_testing(self) -> 'EventBus':
        """
        Create EventBus with mock dependencies for testing.

        Returns:
            EventBus instance with mock components
        """
        # Create mock subscription manager
        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager._is_mock = True

        # Setup async methods
        subscription_manager.add_subscription = AsyncMock(return_value="test-sub-id")
        subscription_manager.remove_subscription = AsyncMock(return_value=True)
        subscription_manager.get_subscriptions_for_event = AsyncMock(return_value=[])
        subscription_manager.get_subscription_count = AsyncMock(return_value=0)
        subscription_manager.get_active_subscription_count = AsyncMock(return_value=0)
        subscription_manager.record_subscription_failure = AsyncMock()
        subscription_manager.record_subscription_success = AsyncMock()

        # Create mock event processor
        event_processor = Mock(spec=EventProcessorInterface)
        event_processor._is_mock = True

        # Setup async methods
        from app.engine.core.event_processor import EventProcessingResult, EventProcessingStats
        from uuid import uuid4

        mock_result = EventProcessingResult(
            event_id=uuid4(),
            successful_handlers=1,
            failed_handlers=0,
            errors=[],
            processing_time=0.001
        )
        mock_stats = EventProcessingStats()

        event_processor.process_event = AsyncMock(return_value=mock_result)
        event_processor.get_stats = AsyncMock(return_value=mock_stats)
        event_processor.reset_stats = AsyncMock()

        return self.create_with_dependencies(
            subscription_manager=subscription_manager,
            event_processor=event_processor
        )

    def create_with_dependencies(
        self,
        subscription_manager: SubscriptionManagerInterface,
        event_processor: EventProcessorInterface,
        config: Optional[EventBusConfig] = None
    ) -> 'EventBus':
        """
        Create EventBus with custom dependencies.

        Args:
            subscription_manager: Subscription management component
            event_processor: Event processing component
            config: Optional configuration (uses defaults if None)

        Returns:
            EventBus instance with injected dependencies

        Raises:
            InvalidConfigurationError: If dependencies are invalid
        """
        # Validate dependencies
        self._validate_subscription_manager(subscription_manager)
        self._validate_event_processor(event_processor)

        if config is None:
            config = EventBusConfig()

        # Import here to avoid circular imports
        from app.engine.bus import EventBus

        return EventBus(
            subscription_manager=subscription_manager,
            event_processor=event_processor,
            config=config
        )

    def _validate_subscription_manager(self, manager: Any) -> None:
        """
        Validate subscription manager has required interface.

        Args:
            manager: Manager to validate

        Raises:
            InvalidConfigurationError: If manager is invalid
        """
        required_methods = [
            'add_subscription', 'remove_subscription', 'get_subscriptions_for_event',
            'get_subscription_count', 'get_active_subscription_count',
            'record_subscription_failure', 'record_subscription_success'
        ]

        for method in required_methods:
            if not hasattr(manager, method):
                raise InvalidConfigurationError(
                    f"Invalid subscription manager: missing method '{method}'"
                )

    def _validate_event_processor(self, processor: Any) -> None:
        """
        Validate event processor has required interface.

        Args:
            processor: Processor to validate

        Raises:
            InvalidConfigurationError: If processor is invalid
        """
        required_methods = ['process_event', 'get_stats', 'reset_stats']

        for method in required_methods:
            if not hasattr(processor, method):
                raise InvalidConfigurationError(
                    f"Invalid event processor: missing method '{method}'"
                )