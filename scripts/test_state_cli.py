#!/usr/bin/env python3
"""Tests for state management CLI."""
import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from state_manager import StateManager, StateType, StateSnapshot
from io import StringIO
import sys


class TestStateCLI:
    """Tests for state management CLI operations."""

    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager."""
        manager = Mock(spec=StateManager)
        manager.state_dir = Path("/tmp/test_state")
        return manager

    @pytest.fixture
    def mock_args(self):
        """Create mock arguments."""
        args = Mock()
        args.command = None
        return args

    @pytest.mark.asyncio
    async def test_save_state_process(self, mock_state_manager):
        """Test saving process state."""
        # Import the CLI module
        from state import StateCLI

        # Setup
        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.save_process_state = AsyncMock(
            return_value=Path("/tmp/state/process_20240115_100000.json")
        )

        # Execute
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.save_state("process")

        # Verify
        mock_state_manager.save_process_state.assert_called_once()
        output = mock_stdout.getvalue()
        assert "✓ Saved process state" in output

    @pytest.mark.asyncio
    async def test_save_state_configuration(self, mock_state_manager):
        """Test saving configuration state."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager._save_configuration_state = AsyncMock(
            return_value=Path("/tmp/state/configuration_20240115_100000.json")
        )

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.save_state("configuration")

        mock_state_manager._save_configuration_state.assert_called_once()
        output = mock_stdout.getvalue()
        assert "✓ Saved configuration state" in output

    @pytest.mark.asyncio
    async def test_save_state_invalid_type(self):
        """Test saving with invalid state type."""
        from state import StateCLI

        cli = StateCLI()

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.save_state("invalid")

        output = mock_stdout.getvalue()
        assert "Invalid state type: invalid" in output
        assert "Valid types:" in output

    @pytest.mark.asyncio
    async def test_load_state_with_data(self, mock_state_manager):
        """Test loading and displaying state."""
        from state import StateCLI

        # Setup test data
        snapshot = StateSnapshot(
            timestamp=datetime.now(),
            state_type=StateType.PROCESS,
            data={"processes": {"engine": "running", "router": "stopped"}},
            metadata={"host": "test-host", "user": "test-user"},
            version="1.0"
        )

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.load_state = AsyncMock(return_value=snapshot)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.load_state("process")

        output = mock_stdout.getvalue()
        assert "State: process" in output
        assert "Timestamp:" in output
        assert "Version: 1.0" in output
        assert "test-host" in output
        assert '"engine": "running"' in output

    @pytest.mark.asyncio
    async def test_load_state_not_found(self, mock_state_manager):
        """Test loading state when no snapshot exists."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.load_state = AsyncMock(return_value=None)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.load_state("process")

        output = mock_stdout.getvalue()
        assert "No state found for process" in output

    @pytest.mark.asyncio
    async def test_restore_process_state_success(self, mock_state_manager):
        """Test successful process state restoration."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.restore_process_state = AsyncMock(return_value=True)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.restore_state("process")

        mock_state_manager.restore_process_state.assert_called_once()
        output = mock_stdout.getvalue()
        assert "✓ Process state restored successfully" in output

    @pytest.mark.asyncio
    async def test_restore_process_state_failure(self, mock_state_manager):
        """Test failed process state restoration."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.restore_process_state = AsyncMock(return_value=False)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.restore_state("process")

        output = mock_stdout.getvalue()
        assert "✗ Failed to restore process state" in output

    @pytest.mark.asyncio
    async def test_create_checkpoint(self, mock_state_manager):
        """Test creating a checkpoint."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.create_checkpoint = AsyncMock(return_value={
            "process": Path("/tmp/checkpoint/process.json"),
            "configuration": Path("/tmp/checkpoint/config.json")
        })

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.create_checkpoint("pre-deploy")

        mock_state_manager.create_checkpoint.assert_called_once_with("pre-deploy")
        output = mock_stdout.getvalue()
        assert "Creating checkpoint 'pre-deploy'" in output
        assert "Checkpoint created with 2 states" in output
        assert "✓ process:" in output
        assert "✓ configuration:" in output

    @pytest.mark.asyncio
    async def test_restore_checkpoint_success(self, mock_state_manager):
        """Test successful checkpoint restoration."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.restore_checkpoint = AsyncMock(return_value=True)

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.restore_checkpoint("pre-deploy")

        mock_state_manager.restore_checkpoint.assert_called_once_with("pre-deploy")
        output = mock_stdout.getvalue()
        assert "Restoring from checkpoint 'pre-deploy'" in output
        assert "✓ Checkpoint restored successfully" in output

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, mock_state_manager):
        """Test listing available checkpoints."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.list_checkpoints = Mock(return_value=[
            {
                "name": "pre-deploy",
                "timestamp": "2024-01-15T10:00:00",
                "states": ["process", "configuration"]
            },
            {
                "name": "maintenance",
                "timestamp": "2024-01-14T15:30:00",
                "states": ["process"]
            }
        ])

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.list_checkpoints()

        output = mock_stdout.getvalue()
        assert "Available Checkpoints (2):" in output
        assert "pre-deploy" in output
        assert "2024-01-15T10:00:00" in output
        assert "process, configuration" in output

    @pytest.mark.asyncio
    async def test_list_checkpoints_empty(self, mock_state_manager):
        """Test listing checkpoints when none exist."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.list_checkpoints = Mock(return_value=[])

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.list_checkpoints()

        output = mock_stdout.getvalue()
        assert "No checkpoints found" in output

    @pytest.mark.asyncio
    async def test_list_snapshots(self, mock_state_manager):
        """Test listing state snapshots."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager
        mock_state_manager.list_state_snapshots = Mock(return_value=[
            {
                "filename": "process_20240115_100000.json",
                "timestamp": "2024-01-15T10:00:00"
            },
            {
                "filename": "process_20240115_090000.json",
                "timestamp": "2024-01-15T09:00:00"
            }
        ])

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.list_snapshots("process", 10)

        mock_state_manager.list_state_snapshots.assert_called_once_with(StateType.PROCESS, 10)
        output = mock_stdout.getvalue()
        assert "Snapshots for process (latest 10):" in output
        assert "process_20240115_100000.json" in output

    @pytest.mark.asyncio
    async def test_clean_old_snapshots(self, mock_state_manager):
        """Test cleaning old snapshots."""
        from state import StateCLI

        cli = StateCLI()
        cli.state_manager = mock_state_manager

        # Mock the state directory structure
        mock_state_dir = MagicMock()
        mock_state_manager.state_dir = mock_state_dir

        # Create mock directories and files
        process_dir = MagicMock()
        config_dir = MagicMock()

        # Mock old files
        old_file1 = MagicMock()
        old_file1.stat.return_value.st_mtime = (datetime.now() - timedelta(days=40)).timestamp()
        old_file2 = MagicMock()
        old_file2.stat.return_value.st_mtime = (datetime.now() - timedelta(days=35)).timestamp()
        recent_file = MagicMock()
        recent_file.stat.return_value.st_mtime = (datetime.now() - timedelta(days=10)).timestamp()

        process_dir.exists.return_value = True
        process_dir.glob.return_value = [old_file1, old_file2, recent_file]
        config_dir.exists.return_value = False

        mock_state_dir.__truediv__ = lambda self, x: process_dir if x == "process" else config_dir

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            await cli.clean_old_snapshots(30)

        # Verify old files were deleted
        old_file1.unlink.assert_called_once()
        old_file2.unlink.assert_called_once()
        recent_file.unlink.assert_not_called()

        output = mock_stdout.getvalue()
        assert "✓ Deleted 2 old process snapshots" in output
        assert "Total snapshots deleted: 2" in output