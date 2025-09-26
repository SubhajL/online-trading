"""Recovery system for handling failures and cleanup in the trading platform."""
import asyncio
import psutil
import os
import shutil
import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum


logger = logging.getLogger(__name__)


class RecoveryAction(Enum):
    """Types of recovery actions."""
    CLEANUP_LOGS = "cleanup_logs"
    CLEANUP_TEMP = "cleanup_temp"
    RESET_CACHE = "reset_cache"
    RESTART_SERVICE = "restart_service"
    RESTORE_CONFIG = "restore_config"
    CLEAR_LOCKS = "clear_locks"
    DATABASE_CLEANUP = "database_cleanup"


@dataclass
class RecoveryTask:
    """A recovery task to be executed."""
    action: RecoveryAction
    target: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, higher is more urgent
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class RecoveryResult:
    """Result of a recovery action."""
    task: RecoveryTask
    success: bool
    message: str
    timestamp: datetime
    duration: float
    error: Optional[str] = None


class RecoverySystem:
    """System for handling recovery and cleanup tasks."""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path(__file__).parent.parent
        self.recovery_handlers: Dict[RecoveryAction, Callable] = {
            RecoveryAction.CLEANUP_LOGS: self._cleanup_logs,
            RecoveryAction.CLEANUP_TEMP: self._cleanup_temp,
            RecoveryAction.RESET_CACHE: self._reset_cache,
            RecoveryAction.RESTART_SERVICE: self._restart_service,
            RecoveryAction.RESTORE_CONFIG: self._restore_config,
            RecoveryAction.CLEAR_LOCKS: self._clear_locks,
            RecoveryAction.DATABASE_CLEANUP: self._database_cleanup,
        }
        self.recovery_history: List[RecoveryResult] = []

    async def execute_recovery(self, task: RecoveryTask) -> RecoveryResult:
        """Execute a recovery task."""
        start_time = datetime.now()
        logger.info(f"Executing recovery task: {task.action.value} for {task.target}")

        handler = self.recovery_handlers.get(task.action)
        if not handler:
            return RecoveryResult(
                task=task,
                success=False,
                message=f"No handler for action: {task.action}",
                timestamp=start_time,
                duration=0,
                error="Handler not found"
            )

        retries = 0
        while retries <= task.max_retries:
            try:
                await handler(task)
                duration = (datetime.now() - start_time).total_seconds()
                result = RecoveryResult(
                    task=task,
                    success=True,
                    message=f"Successfully executed {task.action.value}",
                    timestamp=start_time,
                    duration=duration
                )
                self.recovery_history.append(result)
                return result

            except Exception as e:
                logger.error(f"Recovery task failed (attempt {retries + 1}): {e}")
                retries += 1
                if retries <= task.max_retries:
                    await asyncio.sleep(task.retry_delay)
                else:
                    duration = (datetime.now() - start_time).total_seconds()
                    result = RecoveryResult(
                        task=task,
                        success=False,
                        message=f"Failed after {task.max_retries} retries",
                        timestamp=start_time,
                        duration=duration,
                        error=str(e)
                    )
                    self.recovery_history.append(result)
                    return result

    async def _cleanup_logs(self, task: RecoveryTask) -> None:
        """Clean up old log files."""
        log_dirs = task.parameters.get("directories", [
            self.base_path / "logs",
            self.base_path / "app" / "engine" / "logs",
            self.base_path / "app" / "router" / "logs",
            self.base_path / "app" / "bff" / "logs"
        ])

        max_age_days = task.parameters.get("max_age_days", 7)
        cutoff_date = datetime.now() - timedelta(days=max_age_days)

        total_cleaned = 0
        total_size = 0

        for log_dir in log_dirs:
            if isinstance(log_dir, str):
                log_dir = Path(log_dir)

            if not log_dir.exists():
                continue

            for log_file in log_dir.glob("**/*.log*"):
                try:
                    stat = log_file.stat()
                    if datetime.fromtimestamp(stat.st_mtime) < cutoff_date:
                        total_size += stat.st_size
                        log_file.unlink()
                        total_cleaned += 1
                except Exception as e:
                    logger.warning(f"Failed to delete log file {log_file}: {e}")

        logger.info(f"Cleaned {total_cleaned} log files, freed {total_size / 1024 / 1024:.2f} MB")

    async def _cleanup_temp(self, task: RecoveryTask) -> None:
        """Clean up temporary files."""
        temp_dirs = task.parameters.get("directories", [
            self.base_path / "temp",
            self.base_path / "tmp",
            Path("/tmp") / "trading_platform"
        ])

        total_cleaned = 0
        total_size = 0

        for temp_dir in temp_dirs:
            if isinstance(temp_dir, str):
                temp_dir = Path(temp_dir)

            if not temp_dir.exists():
                continue

            try:
                for item in temp_dir.iterdir():
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink()
                        total_cleaned += 1
                        total_size += size
                    elif item.is_dir():
                        shutil.rmtree(item)
                        total_cleaned += 1
            except Exception as e:
                logger.warning(f"Failed to clean temp directory {temp_dir}: {e}")

        logger.info(f"Cleaned {total_cleaned} temp items, freed {total_size / 1024 / 1024:.2f} MB")

    async def _reset_cache(self, task: RecoveryTask) -> None:
        """Reset Redis cache."""
        import redis

        redis_config = task.parameters.get("redis_config", {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", 6379)),
            "password": os.getenv("REDIS_PASSWORD")
        })

        patterns = task.parameters.get("patterns", ["*"])

        try:
            r = redis.Redis(**redis_config)

            total_deleted = 0
            for pattern in patterns:
                keys = r.keys(pattern)
                if keys:
                    deleted = r.delete(*keys)
                    total_deleted += deleted
                    logger.info(f"Deleted {deleted} keys matching pattern: {pattern}")

            logger.info(f"Total cache keys deleted: {total_deleted}")
        except Exception as e:
            logger.error(f"Failed to reset cache: {e}")
            raise

    async def _restart_service(self, task: RecoveryTask) -> None:
        """Restart a service using the process monitor."""
        from process_monitor import ProcessMonitor, MonitorConfig

        service_name = task.target
        if not service_name:
            raise ValueError("No service name specified for restart")

        monitor = ProcessMonitor(MonitorConfig())

        # Stop the service
        stopped = await monitor.stop_process(service_name)
        if not stopped:
            logger.warning(f"Failed to stop service {service_name}")

        # Wait before restarting
        await asyncio.sleep(task.parameters.get("restart_delay", 5.0))

        # Start the service
        started = await monitor.start_process(service_name)
        if not started:
            raise RuntimeError(f"Failed to start service {service_name}")

        logger.info(f"Successfully restarted service: {service_name}")

    async def _restore_config(self, task: RecoveryTask) -> None:
        """Restore configuration from backup."""
        config_files = task.parameters.get("config_files", [
            self.base_path / ".env",
            self.base_path / "config.yaml",
            self.base_path / "app" / "engine" / "config.yaml"
        ])

        backup_dir = Path(task.parameters.get("backup_dir", self.base_path / "backups"))

        restored = 0
        for config_file in config_files:
            if isinstance(config_file, str):
                config_file = Path(config_file)

            backup_file = backup_dir / f"{config_file.name}.backup"

            if backup_file.exists() and config_file.exists():
                # Create a temporary backup of current config
                temp_backup = config_file.with_suffix(".temp_backup")
                shutil.copy2(config_file, temp_backup)

                try:
                    shutil.copy2(backup_file, config_file)
                    restored += 1
                    logger.info(f"Restored config: {config_file}")
                    temp_backup.unlink()
                except Exception as e:
                    # Restore from temp backup on failure
                    shutil.copy2(temp_backup, config_file)
                    temp_backup.unlink()
                    logger.error(f"Failed to restore {config_file}: {e}")

        logger.info(f"Restored {restored} configuration files")

    async def _clear_locks(self, task: RecoveryTask) -> None:
        """Clear file locks and PID files."""
        lock_patterns = task.parameters.get("patterns", [
            "*.lock",
            "*.pid",
            ".*.swp"
        ])

        search_dirs = task.parameters.get("directories", [
            self.base_path,
            Path("/tmp"),
            Path("/var/run")
        ])

        total_cleared = 0
        for search_dir in search_dirs:
            if isinstance(search_dir, str):
                search_dir = Path(search_dir)

            if not search_dir.exists():
                continue

            for pattern in lock_patterns:
                try:
                    for lock_file in search_dir.glob(f"**/{pattern}"):
                        # Check if it's a stale lock
                        if self._is_stale_lock(lock_file):
                            lock_file.unlink()
                            total_cleared += 1
                            logger.info(f"Cleared lock file: {lock_file}")
                except Exception as e:
                    logger.warning(f"Error clearing locks in {search_dir}: {e}")

        logger.info(f"Cleared {total_cleared} lock files")

    async def _database_cleanup(self, task: RecoveryTask) -> None:
        """Clean up database (remove old data, optimize tables)."""
        # This is a placeholder - actual implementation would use database connection
        logger.info("Database cleanup would be performed here")

        # Example operations:
        # - Delete old candle data beyond retention period
        # - Vacuum/optimize tables
        # - Clear orphaned records
        # - Reset sequences if needed

        retention_days = task.parameters.get("retention_days", 30)
        tables = task.parameters.get("tables", ["candles", "indicators", "orders"])

        logger.info(f"Would clean tables {tables} with {retention_days} day retention")

    def _is_stale_lock(self, lock_file: Path) -> bool:
        """Check if a lock file is stale."""
        try:
            # Check if file is older than 1 hour
            stat = lock_file.stat()
            age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
            if age > timedelta(hours=1):
                return True

            # Check if PID file points to non-existent process
            if lock_file.suffix == ".pid":
                try:
                    pid = int(lock_file.read_text().strip())
                    if not psutil.pid_exists(pid):
                        return True
                except:
                    return True

            return False
        except Exception:
            return True

    async def run_full_cleanup(self) -> Dict[str, Any]:
        """Run a full system cleanup."""
        logger.info("Starting full system cleanup")

        tasks = [
            RecoveryTask(RecoveryAction.CLEANUP_LOGS, parameters={"max_age_days": 7}),
            RecoveryTask(RecoveryAction.CLEANUP_TEMP),
            RecoveryTask(RecoveryAction.CLEAR_LOCKS),
            RecoveryTask(RecoveryAction.RESET_CACHE, parameters={"patterns": ["temp:*", "test:*"]}),
        ]

        results = []
        for task in tasks:
            result = await self.execute_recovery(task)
            results.append(result)

        success_count = sum(1 for r in results if r.success)

        summary = {
            "total_tasks": len(tasks),
            "successful": success_count,
            "failed": len(tasks) - success_count,
            "results": [
                {
                    "action": r.task.action.value,
                    "success": r.success,
                    "message": r.message,
                    "duration": r.duration
                }
                for r in results
            ]
        }

        logger.info(f"Cleanup complete: {success_count}/{len(tasks)} tasks successful")
        return summary

    def get_recovery_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent recovery history."""
        return [
            {
                "action": r.task.action.value,
                "target": r.task.target,
                "success": r.success,
                "message": r.message,
                "timestamp": r.timestamp.isoformat(),
                "duration": r.duration,
                "error": r.error
            }
            for r in self.recovery_history[-limit:]
        ]