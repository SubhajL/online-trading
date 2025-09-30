"""
Test helpers for CI-aware testing of alert adapters.

This module provides utilities for detecting CI environment and
conditionally using mocks vs real services based on environment.
"""
import os
from typing import Any, Optional, Dict, Callable
from unittest.mock import Mock, AsyncMock, MagicMock
import redis
import asyncio


def is_ci() -> bool:
    """Check if running in CI environment."""
    return os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"


def get_redis_client() -> Any:
    """
    Get Redis client appropriate for environment.

    In CI: Uses real Redis from GitHub Actions service
    In local: Uses real Redis from local Docker
    """
    if is_ci():
        # CI provides Redis on localhost:6379
        return redis.Redis(host='localhost', port=6379, db=0)
    else:
        # Local development uses Docker Redis
        return redis.Redis(host='localhost', port=6379, db=0)


def get_mock_telegram_client() -> Any:
    """
    Get Telegram client for testing.

    In CI: Always returns mock to avoid external API calls
    In local: Returns mock unless real credentials are provided
    """
    if is_ci():
        # Always mock in CI - no external API calls allowed
        client = AsyncMock()
        client.send_message = AsyncMock(return_value={'message_id': 12345})
        return client

    # In local, check if real credentials exist
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if bot_token and bot_token != "test-token":
        # Would return real Telegram client here
        # For now, return mock
        pass

    # Default to mock
    client = AsyncMock()
    client.send_message = AsyncMock(return_value={'message_id': 12345})
    return client


def get_mock_line_client() -> Any:
    """
    Get LINE client for testing.

    In CI: Always returns mock to avoid external API calls
    In local: Returns mock unless real credentials are provided
    """
    if is_ci():
        # Always mock in CI - no external API calls allowed
        client = AsyncMock()
        client.push_message = AsyncMock(return_value={'status': 200})
        return client

    # In local, check if real credentials exist
    access_token = os.getenv("LINE_ACCESS_TOKEN")
    if access_token and access_token != "test-token":
        # Would return real LINE client here
        # For now, return mock
        pass

    # Default to mock
    client = AsyncMock()
    client.push_message = AsyncMock(return_value={'status': 200})
    return client


class MockEventBus:
    """Mock event bus for testing."""

    def __init__(self):
        self.subscriptions = {}
        self.published_events = []

    async def subscribe(self, event_type: str, handler: Any) -> None:
        """Subscribe to event type."""
        if event_type not in self.subscriptions:
            self.subscriptions[event_type] = []
        self.subscriptions[event_type].append(handler)

    async def publish(self, event_type: str, data: Any) -> None:
        """Publish event."""
        self.published_events.append((event_type, data))

        # Trigger handlers if any
        if event_type in self.subscriptions:
            for handler in self.subscriptions[event_type]:
                await handler(data)


def get_test_event_bus() -> Any:
    """
    Get event bus for testing.

    In CI: Returns mock event bus
    In local: Could connect to real event bus if available
    """
    if is_ci():
        return MockEventBus()

    # For local, check if real event bus is available
    # For now, always return mock
    return MockEventBus()


# Helper function to skip tests that require real services in CI
def skip_if_no_service(service_name: str):
    """Decorator to skip test if service is not available."""
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            if is_ci():
                # In CI, skip tests that require external services
                if service_name in ['telegram', 'line', 'binance']:
                    import pytest
                    pytest.skip(f"{service_name} not available in CI")

            # Check if service is actually available
            if service_name == 'redis':
                try:
                    client = get_redis_client()
                    client.ping()
                except Exception:
                    import pytest
                    pytest.skip(f"{service_name} not available")

            return test_func(*args, **kwargs)

        return wrapper
    return decorator


def build_mock_event_bus() -> Any:
    """Build a mock event bus that can delegate to handlers"""
    subscriptions: Dict[str, Callable] = {}

    async def mock_subscribe(event_type: str, handler: Callable) -> None:
        subscriptions[event_type] = handler

    async def mock_publish(event_type: str, event: Any) -> None:
        if event_type in subscriptions:
            await subscriptions[event_type](event)

    mock_event_bus = MagicMock()
    mock_event_bus.subscribe = AsyncMock(side_effect=mock_subscribe)
    mock_event_bus.publish = AsyncMock(side_effect=mock_publish)
    mock_event_bus._subscriptions = subscriptions  # For test inspection

    return mock_event_bus


def inject_test_session(adapter: Any) -> None:
    """Inject a test-friendly aiohttp session into the adapter"""
    # Create a mock session that doesn't make real HTTP calls
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"ok": True, "result": {"message_id": 123}})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_response)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    mock_session.post = MagicMock(return_value=mock_context)
    mock_session.close = AsyncMock()

    # Replace the adapter's session
    if hasattr(adapter, 'session'):
        adapter.session = mock_session
    elif hasattr(adapter, '_session'):
        adapter._session = mock_session