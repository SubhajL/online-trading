#!/usr/bin/env python3
"""CLI tool for system state management."""
import asyncio
import argparse
import json
from datetime import datetime
from typing import Optional
from state_manager import StateManager, StateType


class StateCLI:
    """CLI for state management operations."""

    def __init__(self):
        self.state_manager = StateManager()

    async def save_state(self, state_type: str) -> None:
        """Save current state."""
        try:
            state_enum = StateType(state_type)
        except ValueError:
            print(f"Invalid state type: {state_type}")
            print(f"Valid types: {', '.join([s.value for s in StateType])}")
            return

        if state_enum == StateType.PROCESS:
            filepath = await self.state_manager.save_process_state()
            print(f"✓ Saved process state to {filepath}")
        elif state_enum == StateType.CONFIGURATION:
            filepath = await self.state_manager._save_configuration_state()
            print(f"✓ Saved configuration state to {filepath}")
        else:
            print(f"State type '{state_type}' requires manual data input")

    async def load_state(self, state_type: str, timestamp: Optional[str] = None) -> None:
        """Load and display state."""
        try:
            state_enum = StateType(state_type)
        except ValueError:
            print(f"Invalid state type: {state_type}")
            return

        ts = None
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp)
            except ValueError:
                print(f"Invalid timestamp format: {timestamp}")
                return

        snapshot = await self.state_manager.load_state(state_enum, ts)

        if snapshot:
            print(f"\nState: {snapshot.state_type.value}")
            print(f"Timestamp: {snapshot.timestamp}")
            print(f"Version: {snapshot.version}")
            print("\nMetadata:")
            for key, value in snapshot.metadata.items():
                print(f"  {key}: {value}")
            print("\nData:")
            print(json.dumps(snapshot.data, indent=2, default=str))
        else:
            print(f"No state found for {state_type}")

    async def restore_state(self, state_type: str) -> None:
        """Restore system from saved state."""
        try:
            state_enum = StateType(state_type)
        except ValueError:
            print(f"Invalid state type: {state_type}")
            return

        if state_enum == StateType.PROCESS:
            success = await self.state_manager.restore_process_state()
            if success:
                print("✓ Process state restored successfully")
            else:
                print("✗ Failed to restore process state")
        else:
            print(f"Restore not implemented for {state_type}")

    async def create_checkpoint(self, name: str) -> None:
        """Create a system checkpoint."""
        print(f"Creating checkpoint '{name}'...")

        results = await self.state_manager.create_checkpoint(name)

        print(f"\nCheckpoint created with {len(results)} states:")
        for state_type, filepath in results.items():
            print(f"✓ {state_type}: {filepath.name}")

    async def restore_checkpoint(self, name: str) -> None:
        """Restore from a checkpoint."""
        print(f"Restoring from checkpoint '{name}'...")

        success = await self.state_manager.restore_checkpoint(name)

        if success:
            print("✓ Checkpoint restored successfully")
        else:
            print("✗ Failed to restore checkpoint")

    async def list_checkpoints(self) -> None:
        """List available checkpoints."""
        checkpoints = self.state_manager.list_checkpoints()

        if not checkpoints:
            print("No checkpoints found")
            return

        print(f"\nAvailable Checkpoints ({len(checkpoints)}):")
        print("-" * 60)
        print(f"{'Name':<20} {'Timestamp':<25} {'States'}")
        print("-" * 60)

        for cp in checkpoints:
            states = ', '.join(cp['states'])
            print(f"{cp['name']:<20} {cp['timestamp']:<25} {states}")

    async def list_snapshots(self, state_type: str, limit: int) -> None:
        """List available snapshots for a state type."""
        try:
            state_enum = StateType(state_type)
        except ValueError:
            print(f"Invalid state type: {state_type}")
            return

        snapshots = self.state_manager.list_state_snapshots(state_enum, limit)

        if not snapshots:
            print(f"No snapshots found for {state_type}")
            return

        print(f"\nSnapshots for {state_type} (latest {limit}):")
        print("-" * 70)
        print(f"{'Filename':<40} {'Timestamp':<25}")
        print("-" * 70)

        for snapshot in snapshots:
            print(f"{snapshot['filename']:<40} {snapshot['timestamp']:<25}")

    async def clean_old_snapshots(self, days: int) -> None:
        """Clean old snapshots."""
        cutoff_date = datetime.now().timestamp() - (days * 86400)
        total_deleted = 0

        for state_type in StateType:
            state_dir = self.state_manager.state_dir / state_type.value
            if not state_dir.exists():
                continue

            deleted = 0
            for file in state_dir.glob("*.json"):
                if file.stat().st_mtime < cutoff_date:
                    file.unlink()
                    deleted += 1

            if deleted > 0:
                print(f"✓ Deleted {deleted} old {state_type.value} snapshots")
                total_deleted += deleted

        print(f"\nTotal snapshots deleted: {total_deleted}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage system state snapshots and checkpoints"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Save state
    save_parser = subparsers.add_parser("save", help="Save current state")
    save_parser.add_argument(
        "type",
        choices=[s.value for s in StateType],
        help="Type of state to save"
    )

    # Load state
    load_parser = subparsers.add_parser("load", help="Load and display state")
    load_parser.add_argument(
        "type",
        choices=[s.value for s in StateType],
        help="Type of state to load"
    )
    load_parser.add_argument(
        "--timestamp",
        help="Specific timestamp to load (ISO format)"
    )

    # Restore state
    restore_parser = subparsers.add_parser("restore", help="Restore system from state")
    restore_parser.add_argument(
        "type",
        choices=[s.value for s in StateType],
        help="Type of state to restore"
    )

    # Checkpoint commands
    checkpoint_parser = subparsers.add_parser("checkpoint", help="Checkpoint operations")
    checkpoint_sub = checkpoint_parser.add_subparsers(dest="checkpoint_cmd")

    create_cp = checkpoint_sub.add_parser("create", help="Create checkpoint")
    create_cp.add_argument("name", help="Checkpoint name")

    restore_cp = checkpoint_sub.add_parser("restore", help="Restore checkpoint")
    restore_cp.add_argument("name", help="Checkpoint name")

    list_cp = checkpoint_sub.add_parser("list", help="List checkpoints")

    # List snapshots
    list_parser = subparsers.add_parser("list", help="List state snapshots")
    list_parser.add_argument(
        "type",
        choices=[s.value for s in StateType],
        help="Type of state"
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of snapshots to show (default: 10)"
    )

    # Clean old snapshots
    clean_parser = subparsers.add_parser("clean", help="Clean old snapshots")
    clean_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Delete snapshots older than this many days (default: 30)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = StateCLI()

    if args.command == "save":
        await cli.save_state(args.type)
    elif args.command == "load":
        await cli.load_state(args.type, args.timestamp)
    elif args.command == "restore":
        await cli.restore_state(args.type)
    elif args.command == "checkpoint":
        if args.checkpoint_cmd == "create":
            await cli.create_checkpoint(args.name)
        elif args.checkpoint_cmd == "restore":
            await cli.restore_checkpoint(args.name)
        elif args.checkpoint_cmd == "list":
            await cli.list_checkpoints()
        else:
            checkpoint_parser.print_help()
    elif args.command == "list":
        await cli.list_snapshots(args.type, args.limit)
    elif args.command == "clean":
        await cli.clean_old_snapshots(args.days)


if __name__ == "__main__":
    asyncio.run(main())