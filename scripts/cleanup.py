#!/usr/bin/env python3
"""CLI tool for system cleanup and recovery operations."""
import asyncio
import argparse
import json
from pathlib import Path
from typing import List
from recovery_system import RecoverySystem, RecoveryTask, RecoveryAction


class CleanupCLI:
    """CLI for cleanup and recovery operations."""

    def __init__(self):
        self.recovery_system = RecoverySystem()

    async def cleanup_logs(self, max_age_days: int) -> None:
        """Clean up old log files."""
        task = RecoveryTask(
            RecoveryAction.CLEANUP_LOGS,
            parameters={"max_age_days": max_age_days}
        )

        result = await self.recovery_system.execute_recovery(task)

        if result.success:
            print(f"✓ {result.message}")
        else:
            print(f"✗ Failed: {result.error}")

    async def cleanup_temp(self) -> None:
        """Clean up temporary files."""
        task = RecoveryTask(RecoveryAction.CLEANUP_TEMP)
        result = await self.recovery_system.execute_recovery(task)

        if result.success:
            print(f"✓ {result.message}")
        else:
            print(f"✗ Failed: {result.error}")

    async def reset_cache(self, patterns: List[str]) -> None:
        """Reset Redis cache."""
        task = RecoveryTask(
            RecoveryAction.RESET_CACHE,
            parameters={"patterns": patterns}
        )

        result = await self.recovery_system.execute_recovery(task)

        if result.success:
            print(f"✓ {result.message}")
        else:
            print(f"✗ Failed: {result.error}")

    async def clear_locks(self) -> None:
        """Clear stale lock files."""
        task = RecoveryTask(RecoveryAction.CLEAR_LOCKS)
        result = await self.recovery_system.execute_recovery(task)

        if result.success:
            print(f"✓ {result.message}")
        else:
            print(f"✗ Failed: {result.error}")

    async def restore_config(self, backup_dir: str) -> None:
        """Restore configuration from backup."""
        task = RecoveryTask(
            RecoveryAction.RESTORE_CONFIG,
            parameters={"backup_dir": backup_dir}
        )

        result = await self.recovery_system.execute_recovery(task)

        if result.success:
            print(f"✓ {result.message}")
        else:
            print(f"✗ Failed: {result.error}")

    async def full_cleanup(self) -> None:
        """Run full system cleanup."""
        print("Running full system cleanup...\n")

        summary = await self.recovery_system.run_full_cleanup()

        print("\nCleanup Summary:")
        print(f"Total tasks: {summary['total_tasks']}")
        print(f"Successful: {summary['successful']}")
        print(f"Failed: {summary['failed']}")
        print("\nTask Results:")

        for result in summary['results']:
            status = "✓" if result['success'] else "✗"
            print(f"{status} {result['action']}: {result['message']} ({result['duration']:.2f}s)")

    async def show_history(self, limit: int) -> None:
        """Show recovery action history."""
        history = self.recovery_system.get_recovery_history(limit)

        if not history:
            print("No recovery history found")
            return

        print(f"\nRecovery History (last {limit} actions):")
        print("-" * 80)
        print(f"{'Timestamp':<20} {'Action':<20} {'Target':<15} {'Success':<8} {'Duration'}")
        print("-" * 80)

        for entry in history:
            success = "Yes" if entry['success'] else "No"
            target = entry['target'] or "-"
            print(
                f"{entry['timestamp'][:19]:<20} "
                f"{entry['action']:<20} "
                f"{target:<15} "
                f"{success:<8} "
                f"{entry['duration']:.2f}s"
            )

            if entry.get('error'):
                print(f"  Error: {entry['error']}")

    async def backup_configs(self) -> None:
        """Backup current configuration files."""
        backup_dir = Path.cwd() / "backups"
        backup_dir.mkdir(exist_ok=True)

        config_files = [
            Path.cwd() / ".env",
            Path.cwd() / "config.yaml",
            Path.cwd() / "app" / "engine" / "config.yaml"
        ]

        backed_up = 0
        for config_file in config_files:
            if config_file.exists():
                backup_file = backup_dir / f"{config_file.name}.backup"
                try:
                    import shutil
                    shutil.copy2(config_file, backup_file)
                    backed_up += 1
                    print(f"✓ Backed up: {config_file} -> {backup_file}")
                except Exception as e:
                    print(f"✗ Failed to backup {config_file}: {e}")

        print(f"\nBacked up {backed_up} configuration files to {backup_dir}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="System cleanup and recovery operations"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Log cleanup
    logs_parser = subparsers.add_parser("logs", help="Clean up old log files")
    logs_parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Delete logs older than this many days (default: 7)"
    )

    # Temp cleanup
    temp_parser = subparsers.add_parser("temp", help="Clean up temporary files")

    # Cache reset
    cache_parser = subparsers.add_parser("cache", help="Reset Redis cache")
    cache_parser.add_argument(
        "--patterns",
        nargs="+",
        default=["temp:*"],
        help="Cache key patterns to delete (default: temp:*)"
    )

    # Lock cleanup
    locks_parser = subparsers.add_parser("locks", help="Clear stale lock files")

    # Config backup
    backup_parser = subparsers.add_parser("backup", help="Backup configuration files")

    # Config restore
    restore_parser = subparsers.add_parser("restore", help="Restore configuration from backup")
    restore_parser.add_argument(
        "--dir",
        default="./backups",
        help="Backup directory (default: ./backups)"
    )

    # Full cleanup
    full_parser = subparsers.add_parser("full", help="Run full system cleanup")

    # History
    history_parser = subparsers.add_parser("history", help="Show recovery action history")
    history_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of history entries to show (default: 20)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = CleanupCLI()

    if args.command == "logs":
        await cli.cleanup_logs(args.days)
    elif args.command == "temp":
        await cli.cleanup_temp()
    elif args.command == "cache":
        await cli.reset_cache(args.patterns)
    elif args.command == "locks":
        await cli.clear_locks()
    elif args.command == "backup":
        await cli.backup_configs()
    elif args.command == "restore":
        await cli.restore_config(args.dir)
    elif args.command == "full":
        await cli.full_cleanup()
    elif args.command == "history":
        await cli.show_history(args.limit)


if __name__ == "__main__":
    asyncio.run(main())