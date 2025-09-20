"""
Unit tests for EventBusFactory.
Written first following TDD principles.
"""

import pytest
from dataclasses import dataclass
from unittest.mock import Mock, AsyncMock

from app.engine.core.event_bus_factory import (
    EventBusFactory,
    EventBusConfig,
    InvalidConfigurationError,
)
from app.engine.core.interfaces import (
    EventBusInterface,
    SubscriptionManagerInterface,
    EventProcessorInterface,
)


@dataclass
class TestConfig:
    """Test configuration for factory."""

    max_queue_size: int = 1000
    num_workers: int = 4
    subscription_limit: int = 500
    processing_timeout: float = 30.0


class TestEventBusConfig:
    def test_config_defaults(self):
        config = EventBusConfig()

        assert config.max_queue_size == 10000
        assert config.num_workers == 4
        assert config.enable_persistence == False
        assert config.dead_letter_queue_size == 1000

    def test_config_custom_values(self):
        config = EventBusConfig(
            max_queue_size=5000,
            num_workers=8,
            enable_persistence=True,
            dead_letter_queue_size=500,
        )

        assert config.max_queue_size == 5000
        assert config.num_workers == 8
        assert config.enable_persistence == True
        assert config.dead_letter_queue_size == 500

    def test_config_validation_positive_values(self):
        with pytest.raises(ValueError) as exc_info:
            EventBusConfig(max_queue_size=0)
        assert "max_queue_size must be positive" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            EventBusConfig(num_workers=0)
        assert "num_workers must be positive" in str(exc_info.value)

    def test_config_validation_max_values(self):
        with pytest.raises(ValueError) as exc_info:
            EventBusConfig(max_queue_size=1000000)
        assert "max_queue_size too large" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            EventBusConfig(num_workers=100)
        assert "num_workers too large" in str(exc_info.value)


class TestEventBusFactory:
    def test_factory_initialization(self):
        factory = EventBusFactory()
        assert factory is not None

    def test_create_event_bus_with_defaults(self):
        factory = EventBusFactory()

        event_bus = factory.create_event_bus()

        assert event_bus is not None
        assert hasattr(event_bus, "start")
        assert hasattr(event_bus, "stop")
        assert hasattr(event_bus, "publish")
        assert hasattr(event_bus, "subscribe")

    def test_create_event_bus_with_custom_config(self):
        factory = EventBusFactory()
        config = EventBusConfig(max_queue_size=5000, num_workers=2)

        event_bus = factory.create_with_config(config)

        assert event_bus is not None
        # Should use the custom configuration
        assert event_bus._config.max_queue_size == 5000
        assert event_bus._config.num_workers == 2

    def test_create_for_testing_with_mocks(self):
        factory = EventBusFactory()

        event_bus = factory.create_for_testing()

        assert event_bus is not None
        # Should have mock dependencies
        assert hasattr(event_bus._subscription_manager, "_is_mock")
        assert hasattr(event_bus._event_processor, "_is_mock")

    def test_create_with_custom_dependencies(self):
        factory = EventBusFactory()

        # Create mock dependencies
        subscription_manager = Mock(spec=SubscriptionManagerInterface)
        subscription_manager._is_mock = True

        event_processor = Mock(spec=EventProcessorInterface)
        event_processor._is_mock = True

        event_bus = factory.create_with_dependencies(
            subscription_manager=subscription_manager, event_processor=event_processor
        )

        assert event_bus is not None
        assert event_bus._subscription_manager is subscription_manager
        assert event_bus._event_processor is event_processor

    def test_factory_validates_invalid_config(self):
        factory = EventBusFactory()

        with pytest.raises(InvalidConfigurationError) as exc_info:
            factory.create_with_config(None)

        assert "Configuration cannot be None" in str(exc_info.value)

    def test_factory_creates_independent_instances(self):
        factory = EventBusFactory()

        event_bus1 = factory.create_event_bus()
        event_bus2 = factory.create_event_bus()

        assert event_bus1 is not event_bus2
        assert event_bus1._subscription_manager is not event_bus2._subscription_manager
        assert event_bus1._event_processor is not event_bus2._event_processor

    def test_factory_with_custom_subscription_config(self):
        factory = EventBusFactory()
        config = EventBusConfig(
            subscription_config={"max_subscriptions": 100, "default_priority": 5}
        )

        event_bus = factory.create_with_config(config)

        assert event_bus is not None
        # Subscription manager should use custom config
        assert event_bus._subscription_manager._config.max_subscriptions == 100
        assert event_bus._subscription_manager._config.default_priority == 5

    def test_factory_with_custom_processing_config(self):
        factory = EventBusFactory()
        config = EventBusConfig(
            processing_config={
                "max_processing_time_seconds": 60.0,
                "max_concurrent_handlers": 20,
            }
        )

        event_bus = factory.create_with_config(config)

        assert event_bus is not None
        # Event processor should use custom config
        assert event_bus._event_processor._config.max_processing_time_seconds == 60.0
        assert event_bus._event_processor._config.max_concurrent_handlers == 20

    def test_factory_validates_dependency_interfaces(self):
        factory = EventBusFactory()

        # Use a simple object that doesn't auto-create attributes
        class InvalidManager:
            pass

        invalid_manager = InvalidManager()

        with pytest.raises(InvalidConfigurationError) as exc_info:
            factory.create_with_dependencies(
                subscription_manager=invalid_manager,
                event_processor=Mock(spec=EventProcessorInterface),
            )

        assert "Invalid subscription manager" in str(exc_info.value)

    def test_factory_singleton_pattern_disabled_by_default(self):
        factory = EventBusFactory()

        # Should create new instances each time
        bus1 = factory.create_event_bus()
        bus2 = factory.create_event_bus()

        assert bus1 is not bus2

    def test_factory_error_handling_for_component_creation(self):
        factory = EventBusFactory()

        # Test with configuration that would cause component creation to fail
        # The config creation itself should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            EventBusConfig(max_queue_size=-1)  # Invalid

        assert "max_queue_size must be positive" in str(exc_info.value)
