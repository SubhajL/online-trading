#!/usr/bin/env python3
"""CLI tool for managing and monitoring trading platform processes."""
import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from process_monitor import ProcessMonitor, ProcessRecoveryPolicy, MonitorConfig


# Default process configurations
PROCESS_CONFIGS = {
    "engine": {
        "command": ["python3", "-m", "app.engine.main"],
        "working_directory": str(Path(__file__).parent.parent),
        "environment_vars": {
            "PYTHONPATH": str(Path(__file__).parent.parent),
        },
        "auto_restart": True,
        "restart_delay": 10.0
    },
    "router": {
        "command": ["go", "run", "cmd/router/main.go"],
        "working_directory": str(Path(__file__).parent.parent / "app" / "router"),
        "environment_vars": {},
        "auto_restart": True,
        "restart_delay": 5.0
    },
    "bff": {
        "command": ["npm", "run", "start"],
        "working_directory": str(Path(__file__).parent.parent / "app" / "bff"),
        "environment_vars": {},
        "auto_restart": True,
        "restart_delay": 10.0
    },
    "ui": {
        "command": ["npm", "run", "dev"],
        "working_directory": str(Path(__file__).parent.parent / "app" / "ui"),
        "environment_vars": {},
        "auto_restart": False,
        "restart_delay": 5.0
    }
}


class ProcessManagerCLI:
    """CLI for process management."""

    def __init__(self):
        self.monitor = ProcessMonitor(MonitorConfig(
            check_interval=5.0,
            restart_delay=10.0,
            max_restart_attempts=3,
            cpu_threshold=80.0,
            memory_threshold=75.0
        ))

    async def start_process(self, name: str) -> None:
        """Start a specific process."""
        if name not in PROCESS_CONFIGS:
            print(f"Error: Unknown process '{name}'")
            print(f"Available processes: {', '.join(PROCESS_CONFIGS.keys())}")
            return

        config = PROCESS_CONFIGS[name]
        policy = ProcessRecoveryPolicy(
            auto_restart=config["auto_restart"],
            restart_command=config["command"],
            working_directory=config["working_directory"],
            environment_vars=config["environment_vars"],
            restart_delay=config["restart_delay"]
        )

        await self.monitor.register_process(name, policy)
        success = await self.monitor.start_process(name)

        if success:
            print(f"✓ Started process: {name}")
        else:
            print(f"✗ Failed to start process: {name}")

    async def stop_process(self, name: str) -> None:
        """Stop a specific process."""
        success = await self.monitor.stop_process(name)
        if success:
            print(f"✓ Stopped process: {name}")
        else:
            print(f"✗ Failed to stop process: {name}")

    async def restart_process(self, name: str) -> None:
        """Restart a specific process."""
        success = await self.monitor.restart_process(name)
        if success:
            print(f"✓ Restarted process: {name}")
        else:
            print(f"✗ Failed to restart process: {name}")

    async def status(self, detailed: bool = False) -> None:
        """Show status of all processes."""
        all_status = await self.monitor.get_all_process_status()

        if not all_status:
            print("No processes registered")
            return

        print("\nProcess Status:")
        print("-" * 60)
        print(f"{'Process':<15} {'Status':<12} {'PID':<8} {'CPU%':<8} {'Memory%':<8} {'Restarts'}")
        print("-" * 60)

        for name, status in all_status.items():
            print(
                f"{name:<15} "
                f"{status['status'].value:<12} "
                f"{status['pid'] or '-':<8} "
                f"{status['cpu_percent']:<8.1f} "
                f"{status['memory_percent']:<8.1f} "
                f"{status['restart_count']}"
            )

        if detailed:
            print("\nDetailed Information:")
            print(json.dumps(all_status, indent=2, default=str))

    async def monitor(self) -> None:
        """Start continuous monitoring."""
        print("Starting process monitoring...")
        print("Press Ctrl+C to stop\n")

        # Register all configured processes
        for name, config in PROCESS_CONFIGS.items():
            policy = ProcessRecoveryPolicy(
                auto_restart=config["auto_restart"],
                restart_command=config["command"],
                working_directory=config["working_directory"],
                environment_vars=config["environment_vars"],
                restart_delay=config["restart_delay"]
            )
            await self.monitor.register_process(name, policy)

        # Set up high resource alert handler
        def on_high_resource(name: str, cpu: float, mem: float):
            print(f"\n⚠️  High resource usage: {name} - CPU: {cpu:.1f}%, Memory: {mem:.1f}%")

        self.monitor.on_high_resource_usage = on_high_resource

        try:
            await self.monitor.start_monitoring()
        except KeyboardInterrupt:
            print("\n\nStopping monitoring...")
            await self.monitor.stop_monitoring()

    async def start_all(self) -> None:
        """Start all configured processes."""
        print("Starting all processes...")

        # Register all processes
        for name, config in PROCESS_CONFIGS.items():
            policy = ProcessRecoveryPolicy(
                auto_restart=config["auto_restart"],
                restart_command=config["command"],
                working_directory=config["working_directory"],
                environment_vars=config["environment_vars"],
                restart_delay=config["restart_delay"]
            )
            await self.monitor.register_process(name, policy)

        # Start all processes
        results = await self.monitor.start_all_processes()

        print("\nStartup Results:")
        for name, success in results.items():
            status = "✓" if success else "✗"
            print(f"{status} {name}: {'Started' if success else 'Failed'}")

    async def stop_all(self) -> None:
        """Stop all running processes."""
        print("Stopping all processes...")

        results = await self.monitor.stop_all_processes()

        print("\nShutdown Results:")
        for name, success in results.items():
            status = "✓" if success else "✗"
            print(f"{status} {name}: {'Stopped' if success else 'Failed'}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage trading platform processes"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a process")
    start_parser.add_argument("name", nargs="?", help="Process name (or 'all')")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop a process")
    stop_parser.add_argument("name", nargs="?", help="Process name (or 'all')")

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart a process")
    restart_parser.add_argument("name", help="Process name")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show process status")
    status_parser.add_argument("-d", "--detailed", action="store_true", help="Show detailed info")

    # Monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Start continuous monitoring")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = ProcessManagerCLI()

    if args.command == "start":
        if args.name == "all":
            await cli.start_all()
        elif args.name:
            await cli.start_process(args.name)
        else:
            print("Please specify a process name or 'all'")
    elif args.command == "stop":
        if args.name == "all":
            await cli.stop_all()
        elif args.name:
            await cli.stop_process(args.name)
        else:
            print("Please specify a process name or 'all'")
    elif args.command == "restart":
        await cli.restart_process(args.name)
    elif args.command == "status":
        await cli.status(detailed=args.detailed)
    elif args.command == "monitor":
        await cli.monitor()


if __name__ == "__main__":
    asyncio.run(main())