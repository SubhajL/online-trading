#!/usr/bin/env python3
"""Tests for cleanup CLI."""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from recovery_system import RecoverySystem, RecoveryTask, RecoveryAction, RecoveryResult
from datetime import datetime
from io import StringIO


class TestCleanupCLI:
    """Tests for cleanup CLI operations."""

    @pytest.fixture
    def mock_recovery_system(self):
        """Create mock recovery system."""
        system = Mock(spec=RecoverySystem)
        return system

    @pytest.fixture
    def success_result(self):
        """Create successful recovery result."""
        task = RecoveryTask(RecoveryAction.CLEANUP_LOGS)
        return RecoveryResult(
            task=task,
            success=True,
            message="Cleaned 10 log files",
            timestamp=datetime.now(),
            duration=2.5
        )

    @pytest.fixture
    def failure_result(self):
        """Create failed recovery result."""
        task = RecoveryTask(RecoveryAction.CLEANUP_LOGS)
        return RecoveryResult(
            task=task,
            success=False,
            message="Failed to clean logs",
            timestamp=datetime.now(),
            duration=1.0,
            error="Permission denied"
        )

    @pytest.mark.asyncio
    async def test_cleanup_logs_success(self, mock_recovery_system, success_result):
        """Test successful log cleanup."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        mock_recovery_system.execute_recovery = AsyncMock(return_value=success_result)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.cleanup_logs(7)

        # Verify correct task was created
        call_args = mock_recovery_system.execute_recovery.call_args[0][0]
        assert call_args.action == RecoveryAction.CLEANUP_LOGS
        assert call_args.parameters["max_age_days"] == 7

        output = mock_stdout.getvalue()
        assert "✓ Cleaned 10 log files" in output

    @pytest.mark.asyncio
    async def test_cleanup_logs_failure(self, mock_recovery_system, failure_result):
        """Test failed log cleanup."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        mock_recovery_system.execute_recovery = AsyncMock(return_value=failure_result)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.cleanup_logs(7)

        output = mock_stdout.getvalue()
        assert "✗ Failed: Permission denied" in output

    @pytest.mark.asyncio
    async def test_cleanup_temp(self, mock_recovery_system, success_result):
        """Test temporary file cleanup."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        success_result.message = "Cleaned temp files"
        mock_recovery_system.execute_recovery = AsyncMock(return_value=success_result)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.cleanup_temp()

        call_args = mock_recovery_system.execute_recovery.call_args[0][0]
        assert call_args.action == RecoveryAction.CLEANUP_TEMP

        output = mock_stdout.getvalue()
        assert "✓ Cleaned temp files" in output

    @pytest.mark.asyncio
    async def test_reset_cache(self, mock_recovery_system, success_result):
        """Test cache reset."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        success_result.message = "Reset 50 cache keys"
        mock_recovery_system.execute_recovery = AsyncMock(return_value=success_result)

        patterns = ["temp:*", "test:*"]
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.reset_cache(patterns)

        call_args = mock_recovery_system.execute_recovery.call_args[0][0]
        assert call_args.action == RecoveryAction.RESET_CACHE
        assert call_args.parameters["patterns"] == patterns

        output = mock_stdout.getvalue()
        assert "✓ Reset 50 cache keys" in output

    @pytest.mark.asyncio
    async def test_clear_locks(self, mock_recovery_system, success_result):
        """Test clearing lock files."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        success_result.message = "Cleared 3 lock files"
        mock_recovery_system.execute_recovery = AsyncMock(return_value=success_result)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.clear_locks()

        call_args = mock_recovery_system.execute_recovery.call_args[0][0]
        assert call_args.action == RecoveryAction.CLEAR_LOCKS

        output = mock_stdout.getvalue()
        assert "✓ Cleared 3 lock files" in output

    @pytest.mark.asyncio
    async def test_restore_config(self, mock_recovery_system, success_result):
        """Test config restoration."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        success_result.message = "Restored 3 config files"
        mock_recovery_system.execute_recovery = AsyncMock(return_value=success_result)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.restore_config("./backups")

        call_args = mock_recovery_system.execute_recovery.call_args[0][0]
        assert call_args.action == RecoveryAction.RESTORE_CONFIG
        assert call_args.parameters["backup_dir"] == "./backups"

        output = mock_stdout.getvalue()
        assert "✓ Restored 3 config files" in output

    @pytest.mark.asyncio
    async def test_full_cleanup(self, mock_recovery_system):
        """Test full system cleanup."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system

        summary = {
            "total_tasks": 4,
            "successful": 3,
            "failed": 1,
            "results": [
                {
                    "action": "cleanup_logs",
                    "success": True,
                    "message": "Cleaned logs",
                    "duration": 2.5
                },
                {
                    "action": "cleanup_temp",
                    "success": True,
                    "message": "Cleaned temp",
                    "duration": 1.2
                },
                {
                    "action": "clear_locks",
                    "success": True,
                    "message": "Cleared locks",
                    "duration": 0.5
                },
                {
                    "action": "reset_cache",
                    "success": False,
                    "message": "Failed to connect",
                    "duration": 3.0
                }
            ]
        }
        mock_recovery_system.run_full_cleanup = AsyncMock(return_value=summary)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.full_cleanup()

        output = mock_stdout.getvalue()
        assert "Running full system cleanup..." in output
        assert "Cleanup Summary:" in output
        assert "Total tasks: 4" in output
        assert "Successful: 3" in output
        assert "Failed: 1" in output
        assert "✓ cleanup_logs: Cleaned logs (2.50s)" in output
        assert "✗ reset_cache: Failed to connect (3.00s)" in output

    @pytest.mark.asyncio
    async def test_show_history(self, mock_recovery_system):
        """Test showing recovery history."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system

        history = [
            {
                "action": "cleanup_logs",
                "target": None,
                "success": True,
                "timestamp": "2024-01-15T10:00:00",
                "duration": 2.5,
                "error": None
            },
            {
                "action": "restart_service",
                "target": "engine",
                "success": False,
                "timestamp": "2024-01-15T09:55:00",
                "duration": 1.0,
                "error": "Service not found"
            }
        ]
        mock_recovery_system.get_recovery_history = Mock(return_value=history)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.show_history(10)

        mock_recovery_system.get_recovery_history.assert_called_once_with(10)

        output = mock_stdout.getvalue()
        assert "Recovery History (last 10 actions):" in output
        assert "cleanup_logs" in output
        assert "Yes" in output  # Success
        assert "restart_service" in output
        assert "engine" in output
        assert "No" in output  # Failure
        assert "Error: Service not found" in output

    @pytest.mark.asyncio
    async def test_show_history_empty(self, mock_recovery_system):
        """Test showing history when empty."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()
        cli.recovery_system = mock_recovery_system
        mock_recovery_system.get_recovery_history = Mock(return_value=[])

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.show_history(10)

        output = mock_stdout.getvalue()
        assert "No recovery history found" in output

    @pytest.mark.asyncio
    async def test_backup_configs(self):
        """Test backing up configuration files."""
        from cleanup import CleanupCLI

        cli = CleanupCLI()

        # Mock Path objects and shutil
        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('shutil.copy2') as mock_copy, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            # Setup mock returns
            mock_exists.side_effect = [True, False, True]  # .env exists, config.yaml doesn't, engine config exists

            await cli.backup_configs()

            # Verify backup directory was created
            mock_mkdir.assert_called_once_with(exist_ok=True)

            # Verify files were copied
            assert mock_copy.call_count == 2

            output = mock_stdout.getvalue()
            assert "✓ Backed up: " in output
            assert ".env" in output
            assert "Backed up 2 configuration files" in output