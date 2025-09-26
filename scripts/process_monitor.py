"""Process monitoring system for the trading platform."""
import asyncio
import psutil
import time
import os
import signal
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    """Status of a monitored process."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class ProcessRecoveryPolicy:
    """Policy for recovering failed processes."""
    auto_restart: bool = True
    restart_command: List[str] = field(default_factory=list)
    working_directory: Optional[str] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    restart_delay: float = 5.0


@dataclass
class ProcessInfo:
    """Information about a monitored process."""
    name: str
    pid: Optional[int] = None
    status: ProcessStatus = ProcessStatus.STOPPED
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    restart_count: int = 0
    last_start_time: Optional[float] = None
    command: List[str] = field(default_factory=list)
    recovery_policy: Optional[ProcessRecoveryPolicy] = None


@dataclass
class MonitorConfig:
    """Configuration for process monitoring."""
    check_interval: float = 5.0
    restart_delay: float = 10.0
    max_restart_attempts: int = 3
    cpu_threshold: float = 80.0
    memory_threshold: float = 75.0
    log_level: str = "INFO"


class ProcessMonitor:
    """Monitor and manage system processes."""

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()
        self.processes: Dict[str, ProcessInfo] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self.on_high_resource_usage: Optional[Callable[[str, float, float], None]] = None

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    async def register_process(
        self,
        name: str,
        recovery_policy: ProcessRecoveryPolicy
    ) -> None:
        """Register a process for monitoring."""
        if name in self.processes:
            logger.warning(f"Process {name} is already registered")
            return

        self.processes[name] = ProcessInfo(
            name=name,
            recovery_policy=recovery_policy,
            command=recovery_policy.restart_command
        )
        logger.info(f"Registered process: {name}")

    async def start_process(self, name: str) -> bool:
        """Start a monitored process."""
        if name not in self.processes:
            logger.error(f"Process {name} is not registered")
            return False

        process_info = self.processes[name]
        if not process_info.recovery_policy or not process_info.recovery_policy.restart_command:
            logger.error(f"No restart command configured for process {name}")
            return False

        try:
            # Update status
            process_info.status = ProcessStatus.STARTING

            # Prepare environment
            env = os.environ.copy()
            if process_info.recovery_policy.environment_vars:
                env.update(process_info.recovery_policy.environment_vars)

            # Start the process
            cmd = process_info.recovery_policy.restart_command
            cwd = process_info.recovery_policy.working_directory

            logger.info(f"Starting process {name}: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Update process info
            process_info.pid = process.pid
            process_info.status = ProcessStatus.RUNNING
            process_info.last_start_time = time.time()

            logger.info(f"Process {name} started with PID {process.pid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start process {name}: {e}")
            process_info.status = ProcessStatus.FAILED
            return False

    async def stop_process(self, name: str, timeout: int = 30) -> bool:
        """Stop a monitored process."""
        if name not in self.processes:
            logger.error(f"Process {name} is not registered")
            return False

        process_info = self.processes[name]
        if not process_info.pid:
            logger.warning(f"Process {name} has no PID")
            process_info.status = ProcessStatus.STOPPED
            return True

        try:
            process = psutil.Process(process_info.pid)

            if process.is_running():
                # Send SIGTERM
                logger.info(f"Stopping process {name} (PID {process_info.pid})")
                process.terminate()

                # Wait for process to terminate
                try:
                    process.wait(timeout=timeout)
                except psutil.TimeoutExpired:
                    logger.warning(f"Process {name} did not terminate, sending SIGKILL")
                    process.kill()
                    process.wait(timeout=5)

            process_info.status = ProcessStatus.STOPPED
            process_info.pid = None
            logger.info(f"Process {name} stopped")
            return True

        except psutil.NoSuchProcess:
            logger.warning(f"Process {name} (PID {process_info.pid}) not found")
            process_info.status = ProcessStatus.STOPPED
            process_info.pid = None
            return True
        except Exception as e:
            logger.error(f"Failed to stop process {name}: {e}")
            return False

    async def restart_process(self, name: str) -> bool:
        """Restart a monitored process."""
        logger.info(f"Restarting process {name}")

        # Stop the process
        if not await self.stop_process(name):
            logger.error(f"Failed to stop process {name} for restart")
            return False

        # Wait before restarting
        await asyncio.sleep(self.config.restart_delay)

        # Start the process
        return await self.start_process(name)

    async def check_process_health(self, name: str) -> Dict[str, Any]:
        """Check the health of a process."""
        if name not in self.processes:
            return {"error": f"Process {name} not registered"}

        process_info = self.processes[name]
        health = {
            "name": name,
            "status": process_info.status,
            "running": False,
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "restart_count": process_info.restart_count
        }

        if process_info.pid:
            try:
                process = psutil.Process(process_info.pid)
                if process.is_running():
                    health["running"] = True
                    health["cpu_percent"] = process.cpu_percent(interval=0.1)
                    health["memory_percent"] = process.memory_percent()

                    # Update process info
                    process_info.cpu_percent = health["cpu_percent"]
                    process_info.memory_percent = health["memory_percent"]
            except psutil.NoSuchProcess:
                health["running"] = False
                process_info.status = ProcessStatus.STOPPED
            except Exception as e:
                logger.error(f"Error checking process {name} health: {e}")

        return health

    async def _check_and_recover_process(self, name: str) -> None:
        """Check process and recover if needed."""
        process_info = self.processes[name]
        health = await self.check_process_health(name)

        # Check if process is running
        if not health["running"] and process_info.status == ProcessStatus.RUNNING:
            logger.warning(f"Process {name} is not running")
            process_info.status = ProcessStatus.FAILED

            # Attempt restart if policy allows
            if (process_info.recovery_policy and
                process_info.recovery_policy.auto_restart and
                process_info.restart_count < self.config.max_restart_attempts):

                process_info.restart_count += 1
                logger.info(f"Attempting to restart {name} (attempt {process_info.restart_count})")

                process_info.status = ProcessStatus.RESTARTING
                if await self.start_process(name):
                    logger.info(f"Successfully restarted {name}")
                else:
                    logger.error(f"Failed to restart {name}")
                    if process_info.restart_count >= self.config.max_restart_attempts:
                        process_info.status = ProcessStatus.FAILED
            else:
                process_info.status = ProcessStatus.FAILED

        # Check resource usage
        if health["running"]:
            cpu = health["cpu_percent"]
            mem = health["memory_percent"]

            if cpu > self.config.cpu_threshold or mem > self.config.memory_threshold:
                logger.warning(
                    f"Process {name} using high resources: "
                    f"CPU={cpu}%, Memory={mem}%"
                )
                if self.on_high_resource_usage:
                    self.on_high_resource_usage(name, cpu, mem)

    async def _monitor_all_processes(self) -> None:
        """Monitor all registered processes."""
        tasks = []
        for name in self.processes:
            task = self._check_and_recover_process(name)
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start_monitoring(self) -> None:
        """Start the monitoring loop."""
        if self._running:
            logger.warning("Monitoring is already running")
            return

        self._running = True
        logger.info("Starting process monitoring")

        while self._running:
            try:
                await self._monitor_all_processes()
                await asyncio.sleep(self.config.check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.config.check_interval)

    async def stop_monitoring(self) -> None:
        """Stop the monitoring loop."""
        logger.info("Stopping process monitoring")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def get_all_process_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all monitored processes."""
        status = {}
        for name, info in self.processes.items():
            status[name] = {
                "status": info.status,
                "pid": info.pid,
                "cpu_percent": info.cpu_percent,
                "memory_percent": info.memory_percent,
                "restart_count": info.restart_count,
                "last_start_time": (
                    datetime.fromtimestamp(info.last_start_time).isoformat()
                    if info.last_start_time else None
                )
            }
        return status

    async def start_all_processes(self) -> Dict[str, bool]:
        """Start all registered processes."""
        results = {}
        for name in self.processes:
            results[name] = await self.start_process(name)
        return results

    async def stop_all_processes(self) -> Dict[str, bool]:
        """Stop all running processes."""
        results = {}
        for name in self.processes:
            results[name] = await self.stop_process(name)
        return results