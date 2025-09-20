import pytest
import yaml
import json
from pathlib import Path


def test_grafana_dashboards_directory_exists():
    """Verify Grafana dashboards provisioning directory exists"""
    dashboards_dir = (
        Path(__file__).parent.parent / "infra/grafana/provisioning/dashboards"
    )
    assert (
        dashboards_dir.exists()
    ), f"Grafana dashboards directory not found at {dashboards_dir}"


def test_grafana_dashboards_config_exists():
    """Verify dashboards provisioning configuration exists"""
    config_path = (
        Path(__file__).parent.parent
        / "infra/grafana/provisioning/dashboards/dashboards.yml"
    )
    assert config_path.exists(), f"Dashboards config not found at {config_path}"


def test_grafana_dashboards_provisioning_structure():
    """Verify dashboards provisioning config has proper structure"""
    config_path = (
        Path(__file__).parent.parent
        / "infra/grafana/provisioning/dashboards/dashboards.yml"
    )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Check basic structure
    assert "apiVersion" in config
    assert config["apiVersion"] == 1
    assert "providers" in config
    assert isinstance(config["providers"], list)
    assert len(config["providers"]) > 0


def test_dashboard_provider_configured():
    """Verify dashboard provider is properly configured"""
    config_path = (
        Path(__file__).parent.parent
        / "infra/grafana/provisioning/dashboards/dashboards.yml"
    )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    provider = config["providers"][0]

    # Check provider configuration
    assert "name" in provider
    assert provider["name"] == "Trading Platform Dashboards"
    assert provider["type"] == "file"
    assert provider["updateIntervalSeconds"] == 30
    assert provider["allowUiUpdates"] == True

    # Check options
    assert "options" in provider
    assert "path" in provider["options"]
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"


def test_dashboards_json_directory_exists():
    """Verify the actual dashboards directory exists"""
    dashboards_json_dir = Path(__file__).parent.parent / "infra/grafana/dashboards"
    assert (
        dashboards_json_dir.exists()
    ), f"Dashboards JSON directory not found at {dashboards_json_dir}"


def test_trading_metrics_dashboard_exists():
    """Verify trading metrics dashboard exists"""
    dashboard_path = (
        Path(__file__).parent.parent / "infra/grafana/dashboards/trading-metrics.json"
    )
    assert (
        dashboard_path.exists()
    ), f"Trading metrics dashboard not found at {dashboard_path}"


def test_trading_metrics_dashboard_structure():
    """Verify trading metrics dashboard has proper structure"""
    dashboard_path = (
        Path(__file__).parent.parent / "infra/grafana/dashboards/trading-metrics.json"
    )

    with open(dashboard_path, "r") as f:
        dashboard = json.load(f)

    # Check dashboard metadata
    assert "title" in dashboard
    assert "Trading Metrics" in dashboard["title"]
    assert "uid" in dashboard
    assert "version" in dashboard
    assert "tags" in dashboard
    assert "trading" in dashboard["tags"]

    # Check dashboard panels
    assert "panels" in dashboard
    assert isinstance(dashboard["panels"], list)
    assert len(dashboard["panels"]) > 0


def test_trading_metrics_dashboard_has_key_panels():
    """Verify dashboard contains key trading panels"""
    dashboard_path = (
        Path(__file__).parent.parent / "infra/grafana/dashboards/trading-metrics.json"
    )

    with open(dashboard_path, "r") as f:
        dashboard = json.load(f)

    panel_titles = [panel["title"] for panel in dashboard["panels"]]

    # Check for essential trading panels
    expected_panels = [
        "Candle Data",
        "Trading Volume",
        "Open Positions",
        "P&L Summary",
        "Order History",
        "Success Rate",
    ]

    for expected_panel in expected_panels:
        assert any(
            expected_panel in title for title in panel_titles
        ), f"Missing expected panel: {expected_panel}"


def test_system_metrics_dashboard_exists():
    """Verify system metrics dashboard exists"""
    dashboard_path = (
        Path(__file__).parent.parent / "infra/grafana/dashboards/system-metrics.json"
    )
    assert (
        dashboard_path.exists()
    ), f"System metrics dashboard not found at {dashboard_path}"


def test_system_metrics_dashboard_has_monitoring_panels():
    """Verify system dashboard contains monitoring panels"""
    dashboard_path = (
        Path(__file__).parent.parent / "infra/grafana/dashboards/system-metrics.json"
    )

    with open(dashboard_path, "r") as f:
        dashboard = json.load(f)

    panel_titles = [panel["title"] for panel in dashboard["panels"]]

    # Check for essential system monitoring panels
    expected_panels = [
        "CPU Usage",
        "Memory Usage",
        "API Response Time",
        "WebSocket Connections",
        "Database Connections",
        "Error Rate",
    ]

    for expected_panel in expected_panels:
        assert any(
            expected_panel in title for title in panel_titles
        ), f"Missing expected system panel: {expected_panel}"
