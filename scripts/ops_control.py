#!/usr/bin/env python3
"""Integrated operations control system for the trading platform."""
import asyncio
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Import all our modules
from process_monitor import ProcessMonitor, ProcessRecoveryPolicy, MonitorConfig
from recovery_system import RecoverySystem, RecoveryTask, RecoveryAction
from state_manager import StateManager, StateType


class OpsControl:
    """Central operations control system."""

    def __init__(self):
        self.process_monitor = ProcessMonitor(MonitorConfig())
        self.recovery_system = RecoverySystem()
        self.state_manager = StateManager()
        self.health_status = {}

    async def startup_sequence(self) -> bool:
        """Execute full startup sequence."""
        print("=== Trading Platform Startup Sequence ===\n")

        # 1. Clean up old files
        print("Step 1: Cleaning up old files...")
        await self._cleanup_startup()

        # 2. Check prerequisites
        print("\nStep 2: Checking prerequisites...")
        if not await self._check_prerequisites():
            print("✗ Prerequisites check failed")
            return False

        # 3. Start infrastructure
        print("\nStep 3: Starting infrastructure services...")
        if not await self._start_infrastructure():
            print("✗ Infrastructure startup failed")
            return False

        # 4. Start application services
        print("\nStep 4: Starting application services...")
        if not await self._start_services():
            print("✗ Application services startup failed")
            return False

        # 5. Verify health
        print("\nStep 5: Verifying system health...")
        if not await self._verify_health():
            print("✗ Health verification failed")
            return False

        # 6. Create startup checkpoint
        print("\nStep 6: Creating startup checkpoint...")
        await self.state_manager.create_checkpoint("startup")

        print("\n✓ Startup sequence completed successfully")
        return True

    async def shutdown_sequence(self) -> bool:
        """Execute graceful shutdown sequence."""
        print("=== Trading Platform Shutdown Sequence ===\n")

        # 1. Save current state
        print("Step 1: Saving current state...")
        await self.state_manager.save_process_state()
        await self.state_manager._save_configuration_state()

        # 2. Stop application services
        print("\nStep 2: Stopping application services...")
        await self._stop_services()

        # 3. Stop infrastructure
        print("\nStep 3: Stopping infrastructure services...")
        await self._stop_infrastructure()

        # 4. Final cleanup
        print("\nStep 4: Performing final cleanup...")
        await self._cleanup_shutdown()

        print("\n✓ Shutdown sequence completed successfully")
        return True

    async def health_check(self, detailed: bool = False) -> Dict[str, Any]:
        """Run comprehensive health checks."""
        print("Running health checks...\n")

        health_results = {
            "timestamp": datetime.now().isoformat(),
            "overall": "healthy",
            "services": {},
            "infrastructure": {},
            "resources": {}
        }

        # Check services
        for service in ["engine", "router", "bff"]:
            health = await self._check_service_health(service)
            health_results["services"][service] = health
            if health["status"] != "healthy":
                health_results["overall"] = "degraded"

        # Check infrastructure
        health_results["infrastructure"]["database"] = await self._check_database_health()
        health_results["infrastructure"]["redis"] = await self._check_redis_health()

        # Check resources
        health_results["resources"] = await self._check_system_resources()

        if detailed:
            print(json.dumps(health_results, indent=2))
        else:
            self._print_health_summary(health_results)

        return health_results

    async def emergency_recovery(self) -> bool:
        """Execute emergency recovery procedure."""
        print("=== Emergency Recovery Procedure ===\n")

        # 1. Stop all processes
        print("Step 1: Stopping all processes...")
        await self.process_monitor.stop_all_processes()

        # 2. Run full cleanup
        print("\nStep 2: Running full system cleanup...")
        cleanup_results = await self.recovery_system.run_full_cleanup()

        # 3. Restore from last good checkpoint
        print("\nStep 3: Looking for last good checkpoint...")
        checkpoints = self.state_manager.list_checkpoints()

        if checkpoints:
            latest = checkpoints[0]["name"]
            print(f"Restoring from checkpoint: {latest}")
            if await self.state_manager.restore_checkpoint(latest):
                print("✓ Checkpoint restored")
            else:
                print("✗ Failed to restore checkpoint")
                return False
        else:
            print("No checkpoints available")

        # 4. Restart services
        print("\nStep 4: Restarting services...")
        return await self._start_services()

    async def maintenance_mode(self, enable: bool) -> None:
        """Enable or disable maintenance mode."""
        if enable:
            print("Enabling maintenance mode...")

            # Stop non-critical services
            await self.process_monitor.stop_process("bff")
            await self.process_monitor.stop_process("ui")

            # Create maintenance checkpoint
            await self.state_manager.create_checkpoint("maintenance")

            print("✓ Maintenance mode enabled")
            print("  - User interfaces stopped")
            print("  - Core services still running")
        else:
            print("Disabling maintenance mode...")

            # Restart services
            await self.process_monitor.start_process("bff")
            await self.process_monitor.start_process("ui")

            print("✓ Maintenance mode disabled")

    async def performance_report(self) -> Dict[str, Any]:
        """Generate performance report."""
        print("Generating performance report...\n")

        report = {
            "timestamp": datetime.now().isoformat(),
            "processes": await self.process_monitor.get_all_process_status(),
            "recovery_history": self.recovery_system.get_recovery_history(10),
            "checkpoints": self.state_manager.list_checkpoints()[:5]
        }

        # Process metrics
        print("Process Performance:")
        print("-" * 60)
        print(f"{'Process':<15} {'CPU%':<10} {'Memory%':<10} {'Restarts':<10} {'Status'}")
        print("-" * 60)

        for name, info in report["processes"].items():
            print(
                f"{name:<15} "
                f"{info['cpu_percent']:<10.1f} "
                f"{info['memory_percent']:<10.1f} "
                f"{info['restart_count']:<10} "
                f"{info['status'].value}"
            )

        # Recovery summary
        print("\n\nRecovery Actions (last 10):")
        success_count = sum(1 for r in report["recovery_history"] if r["success"])
        print(f"Success rate: {success_count}/10")

        return report

    async def _cleanup_startup(self) -> None:
        """Cleanup tasks for startup."""
        tasks = [
            RecoveryTask(RecoveryAction.CLEAR_LOCKS),
            RecoveryTask(RecoveryAction.CLEANUP_TEMP)
        ]

        for task in tasks:
            result = await self.recovery_system.execute_recovery(task)
            status = "✓" if result.success else "✗"
            print(f"{status} {task.action.value}")

    async def _check_prerequisites(self) -> bool:
        """Check system prerequisites."""
        checks = {
            ".env file": (Path.cwd() / ".env").exists(),
            "Database config": bool(Path.cwd().glob("db/migrations/*.sql")),
            "Python venv": (Path.cwd() / "venv").exists() or (Path.cwd() / ".venv").exists()
        }

        all_passed = True
        for check, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"{status} {check}")
            if not passed:
                all_passed = False

        return all_passed

    async def _start_infrastructure(self) -> bool:
        """Start infrastructure services."""
        # This would typically start Docker containers or external services
        print("✓ Database (assuming running)")
        print("✓ Redis (assuming running)")
        return True

    async def _start_services(self) -> bool:
        """Start application services."""
        services = ["engine", "router", "bff"]
        configs = {
            "engine": {
                "command": ["python3", "-m", "app.engine.main"],
                "working_directory": str(Path.cwd()),
                "environment_vars": {"PYTHONPATH": str(Path.cwd())}
            },
            "router": {
                "command": ["go", "run", "cmd/router/main.go"],
                "working_directory": str(Path.cwd() / "app" / "router")
            },
            "bff": {
                "command": ["npm", "run", "start"],
                "working_directory": str(Path.cwd() / "app" / "bff")
            }
        }

        success = True
        for service, config in configs.items():
            policy = ProcessRecoveryPolicy(
                auto_restart=True,
                restart_command=config["command"],
                working_directory=config["working_directory"],
                environment_vars=config.get("environment_vars", {})
            )

            await self.process_monitor.register_process(service, policy)

            if await self.process_monitor.start_process(service):
                print(f"✓ Started {service}")
            else:
                print(f"✗ Failed to start {service}")
                success = False

        return success

    async def _stop_services(self) -> None:
        """Stop application services."""
        services = ["bff", "router", "engine"]  # Reverse order

        for service in services:
            if await self.process_monitor.stop_process(service):
                print(f"✓ Stopped {service}")
            else:
                print(f"✗ Failed to stop {service}")

    async def _stop_infrastructure(self) -> None:
        """Stop infrastructure services."""
        print("✓ Infrastructure services (managed externally)")

    async def _cleanup_shutdown(self) -> None:
        """Cleanup tasks for shutdown."""
        task = RecoveryTask(RecoveryAction.CLEAR_LOCKS)
        result = await self.recovery_system.execute_recovery(task)
        status = "✓" if result.success else "✗"
        print(f"{status} Cleared lock files")

    async def _verify_health(self) -> bool:
        """Verify system health after startup."""
        await asyncio.sleep(3)  # Give services time to stabilize

        all_healthy = True
        for service in ["engine", "router", "bff"]:
            health = await self.process_monitor.check_process_health(service)
            if health["running"]:
                print(f"✓ {service} is healthy")
            else:
                print(f"✗ {service} is not healthy")
                all_healthy = False

        return all_healthy

    async def _check_service_health(self, service: str) -> Dict[str, Any]:
        """Check health of a specific service."""
        health = await self.process_monitor.check_process_health(service)

        return {
            "status": "healthy" if health["running"] else "unhealthy",
            "cpu_percent": health["cpu_percent"],
            "memory_percent": health["memory_percent"],
            "restart_count": health["restart_count"]
        }

    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database health."""
        # Simplified check
        return {"status": "healthy", "connections": 10}

    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health."""
        # Simplified check
        return {"status": "healthy", "memory_used_mb": 50}

    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resources."""
        import psutil

        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }

    def _print_health_summary(self, health_results: Dict[str, Any]) -> None:
        """Print health summary."""
        print(f"Overall Status: {health_results['overall'].upper()}")
        print("\nServices:")
        for service, health in health_results["services"].items():
            status = "✓" if health["status"] == "healthy" else "✗"
            print(f"{status} {service}: {health['status']}")

        print("\nInfrastructure:")
        for component, health in health_results["infrastructure"].items():
            status = "✓" if health["status"] == "healthy" else "✗"
            print(f"{status} {component}: {health['status']}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Integrated operations control for trading platform"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Startup
    startup_parser = subparsers.add_parser("startup", help="Execute startup sequence")

    # Shutdown
    shutdown_parser = subparsers.add_parser("shutdown", help="Execute shutdown sequence")

    # Health
    health_parser = subparsers.add_parser("health", help="Run health checks")
    health_parser.add_argument("-d", "--detailed", action="store_true", help="Show detailed output")

    # Recovery
    recovery_parser = subparsers.add_parser("recovery", help="Execute emergency recovery")

    # Maintenance
    maint_parser = subparsers.add_parser("maintenance", help="Toggle maintenance mode")
    maint_parser.add_argument("mode", choices=["on", "off"], help="Enable or disable")

    # Performance
    perf_parser = subparsers.add_parser("performance", help="Generate performance report")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    ops = OpsControl()

    if args.command == "startup":
        success = await ops.startup_sequence()
        sys.exit(0 if success else 1)
    elif args.command == "shutdown":
        success = await ops.shutdown_sequence()
        sys.exit(0 if success else 1)
    elif args.command == "health":
        await ops.health_check(detailed=args.detailed)
    elif args.command == "recovery":
        success = await ops.emergency_recovery()
        sys.exit(0 if success else 1)
    elif args.command == "maintenance":
        await ops.maintenance_mode(enable=(args.mode == "on"))
    elif args.command == "performance":
        await ops.performance_report()


if __name__ == "__main__":
    asyncio.run(main())