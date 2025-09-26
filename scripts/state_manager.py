"""State management system for the trading platform."""
import json
import os
import pickle
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class StateType(Enum):
    """Types of state that can be managed."""
    PROCESS = "process"
    CONFIGURATION = "configuration"
    TRADING = "trading"
    SYSTEM = "system"


@dataclass
class StateSnapshot:
    """A snapshot of system state at a point in time."""
    timestamp: datetime
    state_type: StateType
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: str = "1.0"


@dataclass
class ProcessState:
    """State of running processes."""
    processes: Dict[str, Dict[str, Any]]
    timestamp: datetime


@dataclass
class TradingState:
    """Trading-related state."""
    active_positions: Dict[str, Any]
    pending_orders: List[Dict[str, Any]]
    strategy_state: Dict[str, Any]
    timestamp: datetime


@dataclass
class SystemState:
    """Overall system state."""
    health_status: Dict[str, Any]
    resource_usage: Dict[str, Any]
    active_connections: Dict[str, Any]
    timestamp: datetime


class StateManager:
    """Manages system state persistence and recovery."""

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".trading_platform" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.current_state: Dict[StateType, Any] = {}

    async def save_state(self, state_type: StateType, data: Any) -> Path:
        """Save state to disk."""
        timestamp = datetime.now()
        snapshot = StateSnapshot(
            timestamp=timestamp,
            state_type=state_type,
            data=data if isinstance(data, dict) else asdict(data),
            metadata={
                "host": os.uname().nodename,
                "user": os.getenv("USER", "unknown")
            }
        )

        # Update current state
        self.current_state[state_type] = snapshot

        # Save to file
        filename = f"{state_type.value}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.state_dir / state_type.value / filename
        filepath.parent.mkdir(exist_ok=True)

        with open(filepath, 'w') as f:
            json.dump(asdict(snapshot), f, indent=2, default=str)

        logger.info(f"Saved {state_type.value} state to {filepath}")
        return filepath

    async def load_state(self, state_type: StateType, timestamp: Optional[datetime] = None) -> Optional[StateSnapshot]:
        """Load state from disk."""
        state_dir = self.state_dir / state_type.value

        if not state_dir.exists():
            logger.warning(f"No state directory found for {state_type.value}")
            return None

        # Find the appropriate state file
        state_files = sorted(state_dir.glob("*.json"), reverse=True)

        if not state_files:
            logger.warning(f"No state files found for {state_type.value}")
            return None

        if timestamp:
            # Find closest file to requested timestamp
            target_str = timestamp.strftime('%Y%m%d_%H%M%S')
            for file in state_files:
                if target_str in file.name:
                    target_file = file
                    break
            else:
                # Use most recent if exact match not found
                target_file = state_files[0]
        else:
            # Use most recent
            target_file = state_files[0]

        try:
            with open(target_file, 'r') as f:
                data = json.load(f)

            snapshot = StateSnapshot(
                timestamp=datetime.fromisoformat(data['timestamp']),
                state_type=StateType(data['state_type']),
                data=data['data'],
                metadata=data.get('metadata', {}),
                version=data.get('version', '1.0')
            )

            logger.info(f"Loaded {state_type.value} state from {target_file}")
            return snapshot

        except Exception as e:
            logger.error(f"Failed to load state from {target_file}: {e}")
            return None

    async def save_process_state(self) -> Path:
        """Save current process state."""
        from process_monitor import ProcessMonitor, MonitorConfig

        monitor = ProcessMonitor(MonitorConfig())
        process_status = await monitor.get_all_process_status()

        state = ProcessState(
            processes=process_status,
            timestamp=datetime.now()
        )

        return await self.save_state(StateType.PROCESS, state)

    async def restore_process_state(self, snapshot: Optional[StateSnapshot] = None) -> bool:
        """Restore process state from snapshot."""
        if not snapshot:
            snapshot = await self.load_state(StateType.PROCESS)

        if not snapshot:
            logger.error("No process state snapshot available")
            return False

        from process_monitor import ProcessMonitor, MonitorConfig, ProcessRecoveryPolicy

        monitor = ProcessMonitor(MonitorConfig())
        success_count = 0

        process_data = snapshot.data.get('processes', {})

        for process_name, info in process_data.items():
            if info.get('status') in ['running', 'starting']:
                # Register and start the process
                policy = ProcessRecoveryPolicy(
                    auto_restart=True,
                    restart_command=info.get('command', [])
                )

                await monitor.register_process(process_name, policy)

                if await monitor.start_process(process_name):
                    success_count += 1
                    logger.info(f"Restored process: {process_name}")
                else:
                    logger.error(f"Failed to restore process: {process_name}")

        logger.info(f"Restored {success_count}/{len(process_data)} processes")
        return success_count > 0

    async def save_trading_state(self, positions: Dict[str, Any],
                               orders: List[Dict[str, Any]],
                               strategy_state: Dict[str, Any]) -> Path:
        """Save current trading state."""
        state = TradingState(
            active_positions=positions,
            pending_orders=orders,
            strategy_state=strategy_state,
            timestamp=datetime.now()
        )

        return await self.save_state(StateType.TRADING, state)

    async def restore_trading_state(self, snapshot: Optional[StateSnapshot] = None) -> Optional[TradingState]:
        """Restore trading state from snapshot."""
        if not snapshot:
            snapshot = await self.load_state(StateType.TRADING)

        if not snapshot:
            logger.error("No trading state snapshot available")
            return None

        return TradingState(
            active_positions=snapshot.data.get('active_positions', {}),
            pending_orders=snapshot.data.get('pending_orders', []),
            strategy_state=snapshot.data.get('strategy_state', {}),
            timestamp=snapshot.timestamp
        )

    async def save_system_state(self, health: Dict[str, Any],
                              resources: Dict[str, Any],
                              connections: Dict[str, Any]) -> Path:
        """Save current system state."""
        state = SystemState(
            health_status=health,
            resource_usage=resources,
            active_connections=connections,
            timestamp=datetime.now()
        )

        return await self.save_state(StateType.SYSTEM, state)

    async def create_checkpoint(self, name: str) -> Dict[str, Path]:
        """Create a full system checkpoint."""
        checkpoint_dir = self.state_dir / "checkpoints" / name
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        results = {}

        # Save all state types
        for state_type in StateType:
            try:
                if state_type == StateType.PROCESS:
                    filepath = await self.save_process_state()
                elif state_type == StateType.CONFIGURATION:
                    filepath = await self._save_configuration_state()
                elif state_type == StateType.TRADING:
                    # This would need actual trading data
                    continue
                elif state_type == StateType.SYSTEM:
                    # This would need actual system data
                    continue

                # Copy to checkpoint directory
                if 'filepath' in locals():
                    import shutil
                    checkpoint_file = checkpoint_dir / filepath.name
                    shutil.copy2(filepath, checkpoint_file)
                    results[state_type.value] = checkpoint_file

            except Exception as e:
                logger.error(f"Failed to save {state_type.value} for checkpoint: {e}")

        # Save checkpoint metadata
        metadata = {
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "states": list(results.keys()),
            "files": {k: str(v) for k, v in results.items()}
        }

        metadata_file = checkpoint_dir / "checkpoint.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Created checkpoint '{name}' with {len(results)} states")
        return results

    async def restore_checkpoint(self, name: str) -> bool:
        """Restore from a checkpoint."""
        checkpoint_dir = self.state_dir / "checkpoints" / name

        if not checkpoint_dir.exists():
            logger.error(f"Checkpoint '{name}' not found")
            return False

        metadata_file = checkpoint_dir / "checkpoint.json"
        if not metadata_file.exists():
            logger.error(f"Checkpoint metadata not found")
            return False

        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        success_count = 0
        for state_type_str, filepath in metadata['files'].items():
            try:
                state_type = StateType(state_type_str)
                state_file = Path(filepath)

                if state_file.exists():
                    with open(state_file, 'r') as f:
                        data = json.load(f)

                    snapshot = StateSnapshot(
                        timestamp=datetime.fromisoformat(data['timestamp']),
                        state_type=state_type,
                        data=data['data'],
                        metadata=data.get('metadata', {}),
                        version=data.get('version', '1.0')
                    )

                    if state_type == StateType.PROCESS:
                        if await self.restore_process_state(snapshot):
                            success_count += 1
                    # Add other restore operations as needed

            except Exception as e:
                logger.error(f"Failed to restore {state_type_str}: {e}")

        logger.info(f"Restored {success_count}/{len(metadata['files'])} states from checkpoint '{name}'")
        return success_count > 0

    async def _save_configuration_state(self) -> Path:
        """Save configuration files state."""
        config_files = {
            ".env": Path.cwd() / ".env",
            "config.yaml": Path.cwd() / "config.yaml",
            "engine_config.yaml": Path.cwd() / "app" / "engine" / "config.yaml"
        }

        config_data = {}
        for name, filepath in config_files.items():
            if filepath.exists():
                config_data[name] = filepath.read_text()

        return await self.save_state(StateType.CONFIGURATION, config_data)

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all available checkpoints."""
        checkpoint_base = self.state_dir / "checkpoints"

        if not checkpoint_base.exists():
            return []

        checkpoints = []
        for checkpoint_dir in checkpoint_base.iterdir():
            if checkpoint_dir.is_dir():
                metadata_file = checkpoint_dir / "checkpoint.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                        checkpoints.append({
                            "name": metadata['name'],
                            "timestamp": metadata['timestamp'],
                            "states": metadata['states']
                        })

        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)

    def list_state_snapshots(self, state_type: StateType, limit: int = 10) -> List[Dict[str, Any]]:
        """List available snapshots for a state type."""
        state_dir = self.state_dir / state_type.value

        if not state_dir.exists():
            return []

        snapshots = []
        for file in sorted(state_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    snapshots.append({
                        "filename": file.name,
                        "timestamp": data['timestamp'],
                        "metadata": data.get('metadata', {})
                    })
            except Exception as e:
                logger.warning(f"Failed to read snapshot {file}: {e}")

        return snapshots