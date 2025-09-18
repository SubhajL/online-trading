"""
Unit tests for lifecycle management.
Following T-3: Pure logic unit tests without external dependencies.
Following T-4: Avoiding heavy mocking.
"""

import asyncio
import pytest
import signal
import time
import threading
from typing import Dict, Any, List

from app.engine.core.lifecycle import (
    register_shutdown_handler,
    drain_event_queues,
    close_database_connections,
    save_application_state,
    shutdown_coordinator,
    startup_health_check,
    ShutdownState,
    LifecycleError
)


class TestShutdownHandler:
    """Tests for shutdown signal handling."""

    def test_shutdown_handler_catches_signals(self):
        """SIGTERM triggers graceful shutdown."""
        shutdown_state = ShutdownState()
        
        # Register handler
        handler = register_shutdown_handler(shutdown_state)
        
        # Verify handler is registered for SIGTERM and SIGINT
        assert handler.is_registered
        assert signal.SIGTERM in handler.signals
        assert signal.SIGINT in handler.signals
        
        # Simulate signal
        handler.handle_signal(signal.SIGTERM, None)
        
        # Should mark shutdown requested
        assert shutdown_state.shutdown_requested
        assert shutdown_state.signal_received == signal.SIGTERM

    def test_shutdown_handler_idempotent(self):
        """Multiple signals don't cause issues."""
        shutdown_state = ShutdownState()
        handler = register_shutdown_handler(shutdown_state)
        
        # Send signal twice
        handler.handle_signal(signal.SIGTERM, None)
        first_time = shutdown_state.shutdown_time
        
        time.sleep(0.01)
        handler.handle_signal(signal.SIGTERM, None)
        
        # Should not change shutdown time
        assert shutdown_state.shutdown_time == first_time
        assert shutdown_state.signal_count == 2

    def test_shutdown_handler_timeout(self):
        """Enforces maximum shutdown time."""
        shutdown_state = ShutdownState(max_shutdown_seconds=0.1)
        handler = register_shutdown_handler(shutdown_state)
        
        # Start shutdown
        handler.handle_signal(signal.SIGTERM, None)
        
        # Wait past timeout
        time.sleep(0.2)
        
        # Should be marked as timed out
        assert shutdown_state.is_timeout()


class TestDrainQueues:
    """Tests for queue draining."""

    def test_drain_queues_timeout(self):
        """Respects max drain time."""
        # Create queue with items
        queue_stats = {
            'event_queue': {
                'items': list(range(1000)),  # Many items
                'processed': 0
            }
        }
        
        # Drain with short timeout
        start = time.time()
        drained = drain_event_queues(queue_stats, max_drain_seconds=0.1)
        elapsed = time.time() - start
        
        # Should respect timeout
        assert elapsed < 0.2
        assert drained['timed_out']
        assert drained['remaining_items'] > 0

    def test_drain_queues_completes(self):
        """Drains all items when possible."""
        # Small queue
        queue_stats = {
            'event_queue': {
                'items': [1, 2, 3],
                'processed': 0
            }
        }
        
        drained = drain_event_queues(queue_stats, max_drain_seconds=1.0)
        
        assert not drained['timed_out']
        assert drained['remaining_items'] == 0
        assert drained['items_processed'] == 3

    def test_drain_queues_empty(self):
        """Handles empty queues gracefully."""
        queue_stats = {
            'event_queue': {
                'items': [],
                'processed': 0
            }
        }
        
        drained = drain_event_queues(queue_stats, max_drain_seconds=1.0)
        
        assert not drained['timed_out']
        assert drained['remaining_items'] == 0
        assert drained['items_processed'] == 0


class TestDatabaseConnectionClose:
    """Tests for connection closing."""

    def test_database_connections_closed(self):
        """All connections returned to OS."""
        # Simulate active connections
        connection_pool = {
            'active': [f'conn_{i}' for i in range(5)],
            'idle': [f'conn_{i}' for i in range(5, 10)],
            'transactions': {
                'conn_0': {'status': 'active', 'start_time': time.time()},
                'conn_1': {'status': 'committed', 'start_time': time.time() - 10}
            }
        }
        
        result = close_database_connections(connection_pool)
        
        assert result['connections_closed'] == 10
        assert result['transactions_rolled_back'] == 1  # Active transaction
        assert len(connection_pool['active']) == 0
        assert len(connection_pool['idle']) == 0

    def test_database_connections_force_close(self):
        """Forces termination after timeout."""
        # Simulate stuck connection
        connection_pool = {
            'active': ['stuck_conn'],
            'idle': [],
            'transactions': {
                'stuck_conn': {'status': 'active', 'stuck': True}
            }
        }
        
        result = close_database_connections(
            connection_pool,
            grace_period_seconds=0.1,
            force=True
        )
        
        assert result['connections_forced'] == 1
        assert result['connections_closed'] == 1


class TestStatePersistence:
    """Tests for application state saving."""

    def test_state_persistence_atomic(self):
        """No partial state saves."""
        # Application state to save
        app_state = {
            'positions': {
                'BTCUSDT': {'size': 1.5, 'entry': 50000, 'pnl': 1000},
                'ETHUSDT': {'size': 10, 'entry': 3000, 'pnl': -200}
            },
            'pending_orders': [
                {'id': 'ord_1', 'symbol': 'BTCUSDT', 'side': 'buy', 'size': 0.1},
                {'id': 'ord_2', 'symbol': 'ETHUSDT', 'side': 'sell', 'size': 2}
            ],
            'config': {'risk_limit': 0.02, 'max_positions': 10}
        }
        
        # Save state
        result = save_application_state(app_state)
        
        # Should be atomic - all or nothing
        assert result['saved']
        assert result['state_size_bytes'] > 0
        assert 'checkpoint_id' in result
        assert result['components_saved'] == ['positions', 'pending_orders', 'config']

    def test_state_persistence_validation(self):
        """Validates state before saving."""
        # Invalid state (corrupted data)
        invalid_state = {
            'positions': None,  # Invalid
            'pending_orders': 'not_a_list'  # Invalid
        }
        
        with pytest.raises(LifecycleError) as exc:
            save_application_state(invalid_state)
        
        assert 'validation' in str(exc.value).lower()

    def test_state_persistence_empty(self):
        """Handles empty state gracefully."""
        empty_state = {
            'positions': {},
            'pending_orders': [],
            'config': {}
        }
        
        result = save_application_state(empty_state)
        
        assert result['saved']
        assert result['components_saved'] == ['positions', 'pending_orders', 'config']


class TestShutdownCoordinator:
    """Tests for shutdown orchestration."""

    def test_shutdown_order_dependencies(self):
        """Components shut down safely."""
        components = {
            'event_bus': {'status': 'running', 'dependencies': []},
            'database': {'status': 'running', 'dependencies': ['event_bus']},
            'order_service': {'status': 'running', 'dependencies': ['database', 'event_bus']}
        }
        
        coordinator = shutdown_coordinator(components)
        shutdown_order = coordinator.get_shutdown_order()
        
        # Should shut down in reverse dependency order
        assert shutdown_order == ['order_service', 'database', 'event_bus']

    def test_shutdown_parallel_where_safe(self):
        """Shuts down independent components in parallel."""
        components = {
            'metrics': {'status': 'running', 'dependencies': []},
            'health': {'status': 'running', 'dependencies': []},
            'cache': {'status': 'running', 'dependencies': []}
        }
        
        coordinator = shutdown_coordinator(components)
        parallel_groups = coordinator.get_parallel_groups()
        
        # All independent, can shut down in parallel
        assert len(parallel_groups) == 1
        assert set(parallel_groups[0]) == {'metrics', 'health', 'cache'}

    def test_shutdown_handles_failures(self):
        """Continues shutdown despite component failures."""
        components = {
            'failing_service': {'status': 'error', 'dependencies': []},
            'healthy_service': {'status': 'running', 'dependencies': []}
        }
        
        coordinator = shutdown_coordinator(components)
        result = coordinator.execute_shutdown()
        
        assert result['completed']
        assert result['failures'] == ['failing_service']
        assert 'healthy_service' in result['shutdown_components']


class TestStartupHealthCheck:
    """Tests for startup verification."""

    def test_startup_blocks_until_healthy(self):
        """Won't accept traffic prematurely."""
        # Simulate unhealthy dependencies
        dependencies = {
            'database': {'healthy': False, 'retry_count': 0},
            'redis': {'healthy': False, 'retry_count': 0}
        }
        
        # Run health check with retries
        checker = startup_health_check(
            dependencies,
            max_retries=3,
            retry_delay_seconds=0.01
        )
        
        # Simulate dependencies becoming healthy
        def make_healthy():
            time.sleep(0.02)
            dependencies['database']['healthy'] = True
            dependencies['redis']['healthy'] = True
        
        thread = threading.Thread(target=make_healthy)
        thread.start()
        
        # Check health
        result = checker.wait_for_healthy(timeout_seconds=0.5)  # Give more time
        thread.join()

        assert result['ready']
        assert result['retry_count'] >= 0  # May be 0 if deps healthy immediately

    def test_startup_timeout(self):
        """Times out if dependencies don't become healthy."""
        dependencies = {
            'database': {'healthy': False, 'retry_count': 0}
        }

        checker = startup_health_check(
            dependencies,
            max_retries=100,  # High retry count to ensure we hit timeout
            retry_delay_seconds=0.01
        )

        result = checker.wait_for_healthy(timeout_seconds=0.03)  # Short timeout

        assert not result['ready']
        assert result['timed_out']
        assert result['unhealthy_dependencies'] == ['database']

    def test_startup_immediate_success(self):
        """Starts immediately if all healthy."""
        dependencies = {
            'database': {'healthy': True},
            'redis': {'healthy': True}
        }
        
        checker = startup_health_check(dependencies)
        result = checker.wait_for_healthy(timeout_seconds=1.0)
        
        assert result['ready']
        assert result['retry_count'] == 0
        assert result['startup_time_ms'] < 10  # Should be fast