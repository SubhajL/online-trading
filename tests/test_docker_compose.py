from pathlib import Path

import pytest
import yaml


def test_timescaledb_configuration():
    """Verify TimescaleDB is properly configured in docker-compose.yml"""
    docker_compose_path = Path(__file__).parent.parent / "docker-compose.yml"

    with open(docker_compose_path, "r") as f:
        config = yaml.safe_load(f)

    # Check that postgres service uses TimescaleDB image
    postgres_service = config["services"]["postgres"]
    assert "timescale/timescaledb" in postgres_service["image"]
    assert "pg16" in postgres_service["image"] or "pg15" in postgres_service["image"]

    # Check TimescaleDB specific environment variables
    env = postgres_service["environment"]
    assert "POSTGRES_DB" in env
    assert "POSTGRES_USER" in env
    assert "POSTGRES_PASSWORD" in env

    # Check shared memory settings for TimescaleDB
    assert "shm_size" in postgres_service
    assert postgres_service["shm_size"] == "256mb"

    # Check command includes TimescaleDB settings
    if "command" in postgres_service:
        command = postgres_service["command"]
        assert "-c" in command
        assert "shared_preload_libraries=timescaledb" in " ".join(command)

    # Verify init scripts are mounted
    volumes = postgres_service["volumes"]
    init_volume = next(
        (v for v in volumes if "init" in v and "docker-entrypoint-initdb.d" in v), None
    )
    assert init_volume is not None


def test_services_use_timescaledb_connection():
    """Verify services are configured to connect to TimescaleDB"""
    docker_compose_path = Path(__file__).parent.parent / "docker-compose.yml"

    with open(docker_compose_path, "r") as f:
        config = yaml.safe_load(f)

    # Services that should connect to TimescaleDB
    db_services = ["engine", "bff"]

    for service_name in db_services:
        service = config["services"][service_name]
        env = service.get("environment", [])

        # Find DATABASE_URL
        db_url = None
        for var in env:
            if isinstance(var, str) and "DATABASE_URL" in var:
                db_url = var
                break

        assert db_url is not None, f"{service_name} should have DATABASE_URL"
        assert "postgres:5432" in db_url, f"{service_name} should connect to postgres service"


def test_monitoring_services_configured():
    """Verify Prometheus and Grafana are properly configured"""
    docker_compose_path = Path(__file__).parent.parent / "docker-compose.yml"

    with open(docker_compose_path, "r") as f:
        config = yaml.safe_load(f)

    # Check Prometheus configuration
    prometheus = config["services"]["prometheus"]
    assert "prom/prometheus" in prometheus["image"]
    assert "./infra/prometheus/prometheus.yml" in " ".join(prometheus["volumes"])

    # Check Grafana configuration
    grafana = config["services"]["grafana"]
    assert "grafana/grafana" in grafana["image"]
    volumes = grafana["volumes"]
    assert any("provisioning" in v for v in volumes)
    assert any("dashboards" in v for v in volumes)


@pytest.mark.parametrize("compose_file", ["docker-compose.yml", "docker-compose.dev.yml"])
def test_engine_and_router_auth_env_are_wired(compose_file: str):
    """Verify engine/router runtime auth variables are passed through compose."""
    docker_compose_path = Path(__file__).parent.parent / compose_file

    with open(docker_compose_path, "r") as f:
        config = yaml.safe_load(f)

    engine_env = config["services"]["engine"].get("environment", [])
    router_env = config["services"]["router"].get("environment", [])

    assert any("ROUTER_API_KEY" in str(var) for var in engine_env)
    assert any("ENGINE_INTERNAL_API_TOKEN" in str(var) for var in engine_env)
    assert any("SECURITY_REQUIRED_API_KEY" in str(var) for var in router_env)
    assert any("ENGINE_INTERNAL_API_TOKEN" in str(var) for var in router_env)


def test_soak_override_pins_critical_services_to_non_watch_commands():
    """Watchers restart services on source edits, silently dooming a soak run."""
    docker_compose_path = Path(__file__).parent.parent / "docker-compose.soak.yml"

    with open(docker_compose_path, "r") as f:
        config = yaml.safe_load(f)

    services = config["services"]
    engine_command = services["engine"]["command"]
    assert "--reload" not in engine_command
    assert engine_command[0] == "uvicorn"

    router_command = " ".join(services["router"]["command"])
    assert "air" not in router_command
    assert "go build" in router_command

    assert services["bff"]["command"] == "pnpm run start"
