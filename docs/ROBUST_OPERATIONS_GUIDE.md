# Robust Operations Guide

This guide documents the comprehensive operations control system implemented for the trading platform.

For staged promotion into live trading, use `docs/LIVE_TRADING_ROLLOUT_RUNBOOK.md` as the source of truth for `backtest` -> `live paper/shadow` -> `testnet soak` -> `mainnet canary` -> `mainnet tiny-risk soak` -> `progressive ramp`.

## Overview

The robust operations system provides:

- Enhanced health checks with dependency verification
- Process monitoring and automatic recovery
- State management for backup and restore
- System cleanup and recovery tools
- Unified operations control CLI

## Core Components

### 1. Enhanced Health Checks

#### Engine (Python)

- **File**: `app/engine/monitoring/enhanced_health.py`
- **Features**:
    - Service dependency checks with latency tracking
    - Event bus health monitoring (backlog size)
    - Database replication lag detection
    - Graceful degradation support
    - Historical health tracking

#### Router (Go)

- **File**: `app/router/internal/health/health.go`
- **Features**:
    - Binance API connectivity checks
    - Redis cache health monitoring
    - Order processing pipeline status
    - Comprehensive health endpoint

#### BFF (TypeScript)

- **File**: `app/bff/src/health/health.controller.enhanced.ts`
- **Features**:
    - Multi-service dependency checks
    - WebSocket connection monitoring
    - Disk space verification
    - Database pool status

### 2. Process Monitoring System

- **File**: `scripts/process_monitor.py`
- **Features**:
    - Process lifecycle management (start/stop/restart)
    - Health check intervals with thresholds
    - Automatic recovery with exponential backoff
    - CPU and memory usage tracking
    - Configurable recovery policies

### 3. Recovery System

- **File**: `scripts/recovery_system.py`
- **Actions**:
    - Log cleanup with age-based retention
    - Temporary file cleanup
    - Redis cache reset
    - Service restart with retry logic
    - Configuration restore from backup
    - Lock file cleanup
    - Database maintenance (planned)

### 4. State Management

- **File**: `scripts/state_manager.py`
- **Capabilities**:
    - Save/restore process states
    - Configuration state snapshots
    - Trading state persistence
    - System checkpoint creation
    - Time-based snapshot retrieval

## CLI Tools

### Operations Control (`scripts/ops_control.py`)

Main orchestration tool that integrates all systems:

```bash
# Start the entire platform with health checks
./ops_control.py startup

# Graceful shutdown with state saving
./ops_control.py shutdown

# Check system health
./ops_control.py health
./ops_control.py health --detailed

# Emergency recovery procedure
./ops_control.py recovery

# Toggle maintenance mode
./ops_control.py maintenance on
./ops_control.py maintenance off

# Generate performance report
./ops_control.py performance
```

### State Management (`scripts/state.py`)

Manage system state snapshots and checkpoints:

```bash
# Save current states
./state.py save process
./state.py save configuration

# View saved states
./state.py load process
./state.py load process --timestamp "2024-01-15T10:00:00"

# Restore system state
./state.py restore process

# Checkpoint operations
./state.py checkpoint create pre-deploy
./state.py checkpoint restore pre-deploy
./state.py checkpoint list

# List snapshots
./state.py list process --limit 20

# Clean old snapshots
./state.py clean --days 30
```

### Cleanup Tool (`scripts/cleanup.py`)

System maintenance and cleanup operations:

```bash
# Clean old logs
./cleanup.py logs --days 7

# Clean temporary files
./cleanup.py temp

# Reset cache
./cleanup.py cache --patterns "temp:*" "test:*"

# Clear stale locks
./cleanup.py locks

# Backup configurations
./cleanup.py backup

# Restore configurations
./cleanup.py restore --dir ./backups

# Run full cleanup
./cleanup.py full

# View recovery history
./cleanup.py history --limit 20
```

## Startup Sequence

The `ops_control.py startup` command executes:

1. **Cleanup old files** - Remove locks and temp files
2. **Check prerequisites** - Verify .env, database, Python venv
3. **Start infrastructure** - Database and Redis services
4. **Start application services** - Engine, Router, BFF in order
5. **Verify health** - Wait for services to stabilize
6. **Create checkpoint** - Save initial healthy state

## Shutdown Sequence

The `ops_control.py shutdown` command executes:

1. **Save current state** - Process and configuration snapshots
2. **Stop application services** - BFF, Router, Engine (reverse order)
3. **Stop infrastructure** - Graceful service termination
4. **Final cleanup** - Clear lock files

## Emergency Recovery

The `ops_control.py recovery` command performs:

1. **Stop all processes** - Force terminate if needed
2. **Run full cleanup** - Logs, temp, cache, locks
3. **Find last checkpoint** - Search for healthy state
4. **Restore checkpoint** - Bring system to known good state
5. **Restart services** - Follow normal startup sequence

## Health Check Endpoints

### Engine

- `GET /health` - Basic liveness check
- `GET /health/ready` - Readiness with dependencies
- `GET /health/comprehensive` - Full system status

### Router

- `GET /health` - Basic health status
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe

### BFF

- `GET /health` - Basic health check
- `GET /health/live` - Kubernetes liveness
- `GET /health/ready` - Kubernetes readiness
- `GET /health/comprehensive` - Detailed status

## Monitoring Integration

The system provides Prometheus-compatible metrics:

- Process status and restart counts
- Health check success/failure rates
- Recovery action history
- Resource usage (CPU, memory, disk)

## Best Practices

1. **Regular Checkpoints**: Create checkpoints before deployments
2. **Health Monitoring**: Use comprehensive health checks in production
3. **Automated Recovery**: Configure appropriate recovery policies
4. **State Backups**: Regular state snapshots for disaster recovery
5. **Cleanup Schedule**: Run cleanup operations during low activity

## Troubleshooting

### Service Won't Start

1. Check prerequisites: `./ops_control.py health --detailed`
2. Review logs in respective service directories
3. Try emergency recovery: `./ops_control.py recovery`

### High Resource Usage

1. Check performance: `./ops_control.py performance`
2. Run cleanup: `./cleanup.py full`
3. Review process metrics in monitoring dashboard

### State Restoration Issues

1. List available checkpoints: `./state.py checkpoint list`
2. Try older checkpoint if latest fails
3. Manually restore individual states if needed

## Configuration

All tools respect environment variables and config files:

- Process monitor config in `MonitorConfig` class
- Recovery system paths in `RecoverySystem` class
- State directory: `~/.trading_platform/state/`
- Checkpoint directory: `~/.trading_platform/state/checkpoints/`

## Testing

Comprehensive test suites ensure reliability:

- `test_enhanced_health.py` - Health check tests
- `test_process_monitor.py` - Process monitoring tests
- `test_recovery_system.py` - Recovery system tests
- `test_state_manager.py` - State management tests
- Health tests for Go Router and TypeScript BFF

All components follow TDD with >80% coverage targets.
