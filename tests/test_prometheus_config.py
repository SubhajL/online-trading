import pytest
import yaml
from pathlib import Path


def test_prometheus_config_exists():
    """Verify Prometheus configuration file exists"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"
    assert config_path.exists(), f"Prometheus config not found at {config_path}"


def test_prometheus_config_structure():
    """Verify Prometheus config has proper structure"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Check global settings
    assert "global" in config
    assert "scrape_interval" in config["global"]
    assert "evaluation_interval" in config["global"]

    # Check scrape configs
    assert "scrape_configs" in config
    assert isinstance(config["scrape_configs"], list)
    assert len(config["scrape_configs"]) > 0


def test_prometheus_scrapes_all_services():
    """Verify Prometheus is configured to scrape all services"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    job_names = [job["job_name"] for job in config["scrape_configs"]]

    # Check for all required service jobs
    required_jobs = [
        "prometheus",
        "trading-engine",
        "trading-router",
        "trading-bff",
        "postgres",
        "redis",
    ]

    for job in required_jobs:
        assert job in job_names, f"Missing scrape job for {job}"


def test_prometheus_job_configuration():
    """Verify each job has proper configuration"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    for job in config["scrape_configs"]:
        # Each job should have a name
        assert "job_name" in job

        # Each job should have targets
        assert "static_configs" in job
        assert len(job["static_configs"]) > 0

        for static_config in job["static_configs"]:
            assert "targets" in static_config
            assert isinstance(static_config["targets"], list)
            assert len(static_config["targets"]) > 0


def test_prometheus_metrics_paths():
    """Verify appropriate metrics paths for services"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Services with custom metrics endpoints
    custom_metrics = {
        "trading-engine": "/metrics",
        "trading-router": "/metrics",
        "trading-bff": "/metrics",
    }

    for job in config["scrape_configs"]:
        job_name = job["job_name"]
        if job_name in custom_metrics:
            assert "metrics_path" in job
            assert job["metrics_path"] == custom_metrics[job_name]


def test_prometheus_scrape_intervals():
    """Verify reasonable scrape intervals"""
    config_path = Path(__file__).parent.parent / "infra/prometheus/prometheus.yml"

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Global interval should be reasonable
    global_interval = config["global"]["scrape_interval"]
    assert global_interval in ["10s", "15s", "30s", "60s"]

    # Job-specific intervals should be reasonable
    for job in config["scrape_configs"]:
        if "scrape_interval" in job:
            assert job["scrape_interval"] in ["5s", "10s", "15s", "30s", "60s"]
