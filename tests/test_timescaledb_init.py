import pytest
from pathlib import Path


def test_timescaledb_extension_script_exists():
    """Verify TimescaleDB extension initialization script exists"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    extension_script = init_dir / "01-init-timescaledb.sql"
    assert (
        extension_script.exists()
    ), f"TimescaleDB init script not found at {extension_script}"


def test_timescaledb_extension_script_content():
    """Verify TimescaleDB extension script has correct content"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    extension_script = init_dir / "01-init-timescaledb.sql"

    with open(extension_script, "r") as f:
        content = f.read()

    # Check for TimescaleDB extension creation
    assert "CREATE EXTENSION IF NOT EXISTS timescaledb" in content
    assert "CASCADE" in content  # Should cascade to create required extensions

    # Check for performance tuning comments
    assert "-- Enable TimescaleDB extension" in content


def test_hypertables_script_exists():
    """Verify hypertables creation script exists"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"
    assert (
        hypertables_script.exists()
    ), f"Hypertables script not found at {hypertables_script}"


def test_hypertables_script_creates_tables():
    """Verify hypertables script creates required tables"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for table creation
    assert "CREATE TABLE IF NOT EXISTS candles" in content
    assert "CREATE TABLE IF NOT EXISTS trades" in content
    assert "CREATE TABLE IF NOT EXISTS order_updates" in content
    assert "CREATE TABLE IF NOT EXISTS positions" in content

    # Check for proper column definitions
    assert "TIMESTAMPTZ NOT NULL" in content  # Time column should be TIMESTAMPTZ
    assert "symbol TEXT NOT NULL" in content
    assert "open NUMERIC" in content
    assert "high NUMERIC" in content
    assert "low NUMERIC" in content
    assert "close NUMERIC" in content
    assert "volume NUMERIC" in content


def test_hypertables_script_creates_hypertables():
    """Verify script converts tables to hypertables"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for hypertable creation
    assert "SELECT create_hypertable('candles'" in content
    assert "SELECT create_hypertable('trades'" in content
    assert "SELECT create_hypertable('order_updates'" in content

    # Check for chunk time interval settings
    assert "chunk_time_interval" in content
    assert "INTERVAL '1 day'" in content or "INTERVAL '1 week'" in content


def test_hypertables_script_creates_indexes():
    """Verify script creates appropriate indexes"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for index creation
    assert "CREATE INDEX" in content
    assert "idx_candles_symbol_time" in content
    assert "idx_trades_symbol_time" in content

    # Check composite indexes
    assert "(symbol, time DESC)" in content or '(symbol, "time" DESC)' in content


def test_hypertables_script_creates_continuous_aggregates():
    """Verify script creates continuous aggregates for different timeframes"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for continuous aggregate creation
    assert "CREATE MATERIALIZED VIEW" in content
    assert "WITH (timescaledb.continuous)" in content

    # Check for different timeframes
    assert "candles_5m" in content
    assert "candles_15m" in content
    assert "candles_1h" in content
    assert "candles_4h" in content
    assert "candles_1d" in content

    # Check aggregation functions
    assert "time_bucket" in content
    assert "first(open" in content
    assert "max(high" in content
    assert "min(low" in content
    assert "last(close" in content
    assert "sum(volume" in content


def test_hypertables_script_sets_compression():
    """Verify script sets compression policies"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for compression policy
    assert (
        "ALTER TABLE candles SET" in content
        or "SELECT add_compression_policy" in content
    )
    assert "timescaledb.compress" in content or "compress_after" in content

    # Check compression is set for old data
    assert "INTERVAL '7 days'" in content or "INTERVAL '30 days'" in content


def test_hypertables_script_sets_retention():
    """Verify script sets data retention policies"""
    init_dir = Path(__file__).parent.parent / "infra/postgres/init"
    hypertables_script = init_dir / "02-create-hypertables.sql"

    with open(hypertables_script, "r") as f:
        content = f.read()

    # Check for retention policy
    assert "add_retention_policy" in content or "-- Retention policy" in content

    # Different retention for different data types
    assert "INTERVAL '1 year'" in content or "INTERVAL '365 days'" in content
