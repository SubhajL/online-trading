"""Test suite for process monitoring system."""
import pytest
import asyncio
import psutil
from unittest.mock import Mock, patch, MagicMock
from process_monitor import (
    ProcessInfo,
    ProcessStatus,
    ProcessMonitor,
    ProcessRecoveryPolicy,
    MonitorConfig
)


class TestProcessInfo:
    def test_process_info_creation(self):
        """Test creating ProcessInfo with all attributes."""
        info = ProcessInfo(
            name="engine",
            pid=12345,
            status=ProcessStatus.RUNNING,
            cpu_percent=15.5,
            memory_percent=2.3,
            restart_count=0,
            last_start_time=1000.0,
            command=["python", "main.py"]
        )

        assert info.name == "engine"
        assert info.pid == 12345
        assert info.status == ProcessStatus.RUNNING
        assert info.cpu_percent == 15.5
        assert info.memory_percent == 2.3
        assert info.restart_count == 0
        assert info.last_start_time == 1000.0
        assert info.command == ["python", "main.py"]

    def test_process_status_enum(self):
        """Test ProcessStatus enum values."""
        assert ProcessStatus.STARTING.value == "starting"
        assert ProcessStatus.RUNNING.value == "running"
        assert ProcessStatus.STOPPED.value == "stopped"
        assert ProcessStatus.FAILED.value == "failed"
        assert ProcessStatus.RESTARTING.value == "restarting"


class TestProcessMonitor:
    @pytest.fixture
    def monitor_config(self):
        """Create test monitor configuration."""
        return MonitorConfig(
            check_interval=1.0,
            restart_delay=2.0,
            max_restart_attempts=3,
            cpu_threshold=80.0,
            memory_threshold=75.0
        )

    @pytest.fixture
    def process_monitor(self, monitor_config):
        """Create ProcessMonitor instance."""
        return ProcessMonitor(monitor_config)

    @pytest.mark.asyncio
    async def test_register_process(self, process_monitor):
        """Test registering a process for monitoring."""
        recovery_policy = ProcessRecoveryPolicy(
            auto_restart=True,
            restart_command=["python", "main.py"],
            working_directory="/app/engine",
            environment_vars={"PYTHONPATH": "/app"}
        )

        await process_monitor.register_process(
            "engine",
            recovery_policy
        )

        assert "engine" in process_monitor.processes
        assert process_monitor.processes["engine"].recovery_policy == recovery_policy

    @pytest.mark.asyncio
    async def test_start_process(self, process_monitor):
        """Test starting a monitored process."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_create.return_value = mock_process

            recovery_policy = ProcessRecoveryPolicy(
                auto_restart=True,
                restart_command=["python", "main.py"],
                working_directory="/app/engine"
            )

            await process_monitor.register_process("engine", recovery_policy)
            result = await process_monitor.start_process("engine")

            assert result is True
            assert process_monitor.processes["engine"].pid == 12345
            assert process_monitor.processes["engine"].status == ProcessStatus.RUNNING
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_process(self, process_monitor):
        """Test stopping a monitored process."""
        with patch('psutil.Process') as mock_process_class:
            mock_process = MagicMock()
            mock_process.is_running.return_value = True
            mock_process_class.return_value = mock_process

            # Register and mock a running process
            recovery_policy = ProcessRecoveryPolicy(auto_restart=False)
            await process_monitor.register_process("engine", recovery_policy)
            process_monitor.processes["engine"].pid = 12345
            process_monitor.processes["engine"].status = ProcessStatus.RUNNING

            result = await process_monitor.stop_process("engine")

            assert result is True
            assert process_monitor.processes["engine"].status == ProcessStatus.STOPPED
            mock_process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_process(self, process_monitor):
        """Test restarting a process."""
        with patch.object(process_monitor, 'stop_process') as mock_stop:
            with patch.object(process_monitor, 'start_process') as mock_start:
                mock_stop.return_value = True
                mock_start.return_value = True

                recovery_policy = ProcessRecoveryPolicy(auto_restart=True)
                await process_monitor.register_process("engine", recovery_policy)

                result = await process_monitor.restart_process("engine")

                assert result is True
                mock_stop.assert_called_once_with("engine", timeout=30)
                mock_start.assert_called_once_with("engine")

    @pytest.mark.asyncio
    async def test_check_process_health(self, process_monitor):
        """Test checking process health metrics."""
        with patch('psutil.Process') as mock_process_class:
            mock_process = MagicMock()
            mock_process.cpu_percent.return_value = 25.0
            mock_process.memory_percent.return_value = 10.0
            mock_process.is_running.return_value = True
            mock_process_class.return_value = mock_process

            recovery_policy = ProcessRecoveryPolicy(auto_restart=True)
            await process_monitor.register_process("engine", recovery_policy)
            process_monitor.processes["engine"].pid = 12345
            process_monitor.processes["engine"].status = ProcessStatus.RUNNING

            health = await process_monitor.check_process_health("engine")

            assert health["running"] is True
            assert health["cpu_percent"] == 25.0
            assert health["memory_percent"] == 10.0
            assert health["status"] == ProcessStatus.RUNNING

    @pytest.mark.asyncio
    async def test_auto_restart_on_failure(self, process_monitor):
        """Test automatic restart when process fails."""
        with patch('psutil.Process') as mock_process_class:
            mock_process = MagicMock()
            mock_process.is_running.return_value = False
            mock_process_class.return_value = mock_process

            with patch.object(process_monitor, 'start_process') as mock_start:
                mock_start.return_value = True

                recovery_policy = ProcessRecoveryPolicy(
                    auto_restart=True,
                    restart_command=["python", "main.py"]
                )
                await process_monitor.register_process("engine", recovery_policy)
                process_monitor.processes["engine"].pid = 12345
                process_monitor.processes["engine"].status = ProcessStatus.RUNNING

                await process_monitor._check_and_recover_process("engine")

                assert process_monitor.processes["engine"].restart_count == 1
                mock_start.assert_called_once_with("engine")

    @pytest.mark.asyncio
    async def test_max_restart_attempts(self, process_monitor):
        """Test that restart attempts are limited."""
        recovery_policy = ProcessRecoveryPolicy(
            auto_restart=True,
            restart_command=["python", "main.py"]
        )
        await process_monitor.register_process("engine", recovery_policy)
        process_monitor.processes["engine"].restart_count = 3  # Max attempts

        with patch.object(process_monitor, 'start_process') as mock_start:
            await process_monitor._check_and_recover_process("engine")

            # Should not attempt restart when max attempts reached
            mock_start.assert_not_called()
            assert process_monitor.processes["engine"].status == ProcessStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_all_process_status(self, process_monitor):
        """Test getting status of all monitored processes."""
        # Register multiple processes
        for name in ["engine", "router", "bff"]:
            recovery_policy = ProcessRecoveryPolicy(auto_restart=True)
            await process_monitor.register_process(name, recovery_policy)
            process_monitor.processes[name].status = ProcessStatus.RUNNING
            process_monitor.processes[name].cpu_percent = 10.0 + len(name)
            process_monitor.processes[name].memory_percent = 5.0 + len(name)

        all_status = await process_monitor.get_all_process_status()

        assert len(all_status) == 3
        assert all_status["engine"]["status"] == ProcessStatus.RUNNING
        assert all_status["router"]["status"] == ProcessStatus.RUNNING
        assert all_status["bff"]["status"] == ProcessStatus.RUNNING

    @pytest.mark.asyncio
    async def test_monitoring_loop(self, process_monitor):
        """Test the continuous monitoring loop."""
        # Mock the check method to stop after one iteration
        check_count = 0
        async def mock_check():
            nonlocal check_count
            check_count += 1
            if check_count > 1:
                process_monitor._running = False

        with patch.object(process_monitor, '_monitor_all_processes', mock_check):
            # Start monitoring in background
            monitor_task = asyncio.create_task(process_monitor.start_monitoring())

            # Give it time to run
            await asyncio.sleep(0.1)

            # Stop monitoring
            await process_monitor.stop_monitoring()
            await monitor_task

            assert check_count >= 1

    @pytest.mark.asyncio
    async def test_high_resource_alert(self, process_monitor):
        """Test alerting when process uses high resources."""
        with patch('psutil.Process') as mock_process_class:
            mock_process = MagicMock()
            mock_process.cpu_percent.return_value = 85.0  # Above threshold
            mock_process.memory_percent.return_value = 80.0  # Above threshold
            mock_process.is_running.return_value = True
            mock_process_class.return_value = mock_process

            recovery_policy = ProcessRecoveryPolicy(auto_restart=True)
            await process_monitor.register_process("engine", recovery_policy)
            process_monitor.processes["engine"].pid = 12345
            process_monitor.processes["engine"].status = ProcessStatus.RUNNING

            alerts = []
            process_monitor.on_high_resource_usage = lambda name, cpu, mem: alerts.append({
                "process": name,
                "cpu": cpu,
                "memory": mem
            })

            await process_monitor._check_and_recover_process("engine")

            assert len(alerts) == 1
            assert alerts[0]["process"] == "engine"
            assert alerts[0]["cpu"] == 85.0
            assert alerts[0]["memory"] == 80.0