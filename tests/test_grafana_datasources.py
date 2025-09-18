import pytest
import yaml
from pathlib import Path


def test_grafana_datasources_directory_exists():
    """Verify Grafana datasources provisioning directory exists"""
    datasources_dir = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources"
    assert datasources_dir.exists(), f"Grafana datasources directory not found at {datasources_dir}"


def test_grafana_datasources_config_exists():
    """Verify datasources configuration file exists"""
    config_path = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources/datasources.yml"
    assert config_path.exists(), f"Datasources config not found at {config_path}"


def test_grafana_datasources_structure():
    """Verify datasources config has proper structure"""
    config_path = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources/datasources.yml"

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Check basic structure
    assert 'apiVersion' in config
    assert config['apiVersion'] == 1
    assert 'datasources' in config
    assert isinstance(config['datasources'], list)
    assert len(config['datasources']) > 0


def test_prometheus_datasource_configured():
    """Verify Prometheus datasource is configured"""
    config_path = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources/datasources.yml"

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Find Prometheus datasource
    prometheus_ds = None
    for ds in config['datasources']:
        if ds.get('type') == 'prometheus':
            prometheus_ds = ds
            break

    assert prometheus_ds is not None, "Prometheus datasource not found"

    # Check Prometheus datasource configuration
    assert prometheus_ds['name'] == 'Prometheus'
    assert prometheus_ds['access'] == 'proxy'
    assert prometheus_ds['isDefault'] == True
    assert prometheus_ds['url'] == 'http://prometheus:9090'

    # Check JSON data settings
    if 'jsonData' in prometheus_ds:
        json_data = prometheus_ds['jsonData']
        if 'httpMethod' in json_data:
            assert json_data['httpMethod'] in ['POST', 'GET']


def test_timescaledb_datasource_configured():
    """Verify TimescaleDB datasource is configured"""
    config_path = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources/datasources.yml"

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Find PostgreSQL/TimescaleDB datasource
    postgres_ds = None
    for ds in config['datasources']:
        if ds.get('type') == 'postgres':
            postgres_ds = ds
            break

    assert postgres_ds is not None, "TimescaleDB/PostgreSQL datasource not found"

    # Check PostgreSQL datasource configuration
    assert 'TimescaleDB' in postgres_ds['name'] or 'PostgreSQL' in postgres_ds['name']
    assert postgres_ds['access'] == 'proxy'
    assert postgres_ds['url'] == 'postgres:5432'

    # Check database connection details
    assert 'database' in postgres_ds
    assert postgres_ds['database'] == 'trading_platform'
    assert postgres_ds['user'] == 'trading_user'

    # Check JSON data settings
    assert 'jsonData' in postgres_ds
    json_data = postgres_ds['jsonData']
    assert json_data['sslmode'] == 'disable'
    assert 'timescaledb' in json_data
    assert json_data['timescaledb'] == True

    # Check secure JSON data (password should be configured)
    assert 'secureJsonData' in postgres_ds
    assert 'password' in postgres_ds['secureJsonData']


def test_datasources_have_required_fields():
    """Verify all datasources have required fields"""
    config_path = Path(__file__).parent.parent / "infra/grafana/provisioning/datasources/datasources.yml"

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    required_fields = ['name', 'type', 'access', 'url']

    for ds in config['datasources']:
        for field in required_fields:
            assert field in ds, f"Datasource missing required field: {field}"

        # Check field types
        assert isinstance(ds['name'], str)
        assert isinstance(ds['type'], str)
        assert ds['access'] in ['proxy', 'direct']
        assert isinstance(ds['url'], str)