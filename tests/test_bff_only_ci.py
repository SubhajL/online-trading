from pathlib import Path

import yaml


def test_bff_only_ci_postgres_healthcheck_targets_configured_database():
    workflow_path = Path(__file__).parent.parent / ".github/workflows/bff-only-ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text())

    postgres_service = workflow["jobs"]["test-bff"]["services"]["postgres"]
    health_options = postgres_service["options"]

    assert 'pg_isready -U trading_user -d trading_platform' in health_options
