import pytest
from pathlib import Path


def test_redis_config_directory_exists():
    """Verify Redis configuration directory exists"""
    redis_dir = Path(__file__).parent.parent / "infra/redis"
    assert redis_dir.exists(), f"Redis directory not found at {redis_dir}"


def test_redis_config_file_exists():
    """Verify Redis configuration file exists"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"
    assert config_path.exists(), f"Redis config not found at {config_path}"


def test_redis_config_has_essential_settings():
    """Verify Redis config contains essential settings"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check for essential settings
    essential_settings = [
        "maxmemory",  # Memory limit
        "maxmemory-policy",  # Eviction policy
        "appendonly",  # Persistence
        "appendfsync",  # Persistence sync policy
        "save",  # Snapshot intervals
        "tcp-keepalive",  # Connection health
        "timeout",  # Client timeout
        "databases",  # Number of databases
    ]

    for setting in essential_settings:
        assert setting in content, f"Missing essential setting: {setting}"


def test_redis_config_memory_settings():
    """Verify Redis memory configuration"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check memory settings
    assert "maxmemory 1gb" in content or "maxmemory 512mb" in content
    assert "maxmemory-policy" in content
    assert any(
        policy in content for policy in ["allkeys-lru", "volatile-lru", "allkeys-lfu"]
    )


def test_redis_config_persistence_settings():
    """Verify Redis persistence configuration"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check persistence settings
    assert "appendonly yes" in content
    assert "appendfsync" in content
    assert any(sync in content for sync in ["everysec", "always", "no"])

    # Check snapshot settings
    assert "save" in content


def test_redis_config_network_settings():
    """Verify Redis network configuration"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check network settings
    assert "tcp-keepalive" in content
    assert "timeout" in content
    assert "tcp-backlog" in content


def test_redis_config_security_settings():
    """Verify Redis has basic security settings"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check that protected mode is considered
    assert "protected-mode" in content or "# protected-mode" in content

    # Check for command renaming or disabling (optional but good practice)
    # These might be commented out but should be mentioned
    assert "rename-command" in content or "# rename-command" in content


def test_redis_config_logging_settings():
    """Verify Redis logging configuration"""
    config_path = Path(__file__).parent.parent / "infra/redis/redis.conf"

    with open(config_path, "r") as f:
        content = f.read()

    # Check logging settings
    assert "loglevel" in content
    assert any(level in content for level in ["debug", "verbose", "notice", "warning"])
