import pytest
import yaml
from pathlib import Path


def test_github_workflows_directory_exists():
    """Verify GitHub workflows directory exists"""
    workflows_dir = Path(__file__).parent.parent / ".github/workflows"
    assert workflows_dir.exists(), f"GitHub workflows directory not found at {workflows_dir}"


def test_ci_workflow_exists():
    """Verify CI workflow file exists"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"
    assert ci_workflow.exists(), f"CI workflow not found at {ci_workflow}"


def test_cd_workflow_exists():
    """Verify CD workflow file exists"""
    cd_workflow = Path(__file__).parent.parent / ".github/workflows/cd.yml"
    assert cd_workflow.exists(), f"CD workflow not found at {cd_workflow}"


def test_ci_workflow_structure():
    """Verify CI workflow has proper structure"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"

    with open(ci_workflow, 'r') as f:
        content = f.read()
        config = yaml.safe_load(content)

    # Check workflow name
    assert 'name' in config
    assert 'CI' in config['name'] or 'Continuous Integration' in config['name']

    # Check triggers (handle 'on' being parsed as True)
    assert 'on:' in content or True in config

    # Check jobs
    assert 'jobs' in config
    assert len(config['jobs']) > 0


def test_ci_workflow_has_essential_jobs():
    """Verify CI workflow contains essential jobs"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"

    with open(ci_workflow, 'r') as f:
        content = f.read()
        config = yaml.safe_load(content)

    jobs = config['jobs']

    # Check for essential CI jobs (lint is included in test jobs)
    essential_job_types = ['test', 'build']
    job_names = list(jobs.keys())

    for job_type in essential_job_types:
        assert any(job_type in job_name.lower() for job_name in job_names), \
            f"Missing essential job type: {job_type}"

    # Check that linting is included in the workflow
    assert 'lint' in content.lower() or 'flake8' in content or 'eslint' in content


def test_ci_workflow_tests_all_services():
    """Verify CI workflow tests all services"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"

    with open(ci_workflow, 'r') as f:
        content = f.read()

    # Check that all services are tested
    services = ['engine', 'router', 'bff', 'ui']
    for service in services:
        assert service in content.lower(), f"Service {service} not tested in CI"


def test_ci_workflow_has_matrix_strategy():
    """Verify CI workflow uses matrix strategy for multiple versions"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"

    with open(ci_workflow, 'r') as f:
        config = yaml.safe_load(f)

    # Check at least one job uses matrix strategy
    has_matrix = False
    for job_name, job_config in config['jobs'].items():
        if 'strategy' in job_config and 'matrix' in job_config['strategy']:
            has_matrix = True
            break

    assert has_matrix, "CI workflow should use matrix strategy for testing multiple versions"


def test_cd_workflow_structure():
    """Verify CD workflow has proper structure"""
    cd_workflow = Path(__file__).parent.parent / ".github/workflows/cd.yml"

    with open(cd_workflow, 'r') as f:
        content = f.read()
        config = yaml.safe_load(content)

    # Check workflow name
    assert 'name' in config
    assert 'CD' in config['name'] or 'Deploy' in config['name'] or 'Continuous Deployment' in config['name']

    # Check triggers (handle 'on' being parsed as True)
    assert 'on:' in content or True in config

    # Check that CD triggers are appropriate
    assert 'tags:' in content or 'release:' in content or 'workflow_dispatch:' in content


def test_cd_workflow_has_deployment_jobs():
    """Verify CD workflow contains deployment jobs"""
    cd_workflow = Path(__file__).parent.parent / ".github/workflows/cd.yml"

    with open(cd_workflow, 'r') as f:
        config = yaml.safe_load(f)

    jobs = config['jobs']

    # Check for deployment-related jobs
    deployment_keywords = ['deploy', 'build', 'push', 'release']
    job_names = list(jobs.keys())

    has_deployment_job = any(
        any(keyword in job_name.lower() for keyword in deployment_keywords)
        for job_name in job_names
    )

    assert has_deployment_job, "CD workflow should contain deployment jobs"


def test_workflows_use_caching():
    """Verify workflows use caching for dependencies"""
    workflows = [
        Path(__file__).parent.parent / ".github/workflows/ci.yml",
        Path(__file__).parent.parent / ".github/workflows/cd.yml"
    ]

    for workflow_path in workflows:
        with open(workflow_path, 'r') as f:
            content = f.read()

        # Check for cache actions
        assert 'actions/cache' in content or 'cache:' in content, \
            f"{workflow_path.name} should use caching for better performance"


def test_workflows_have_security_scanning():
    """Verify workflows include security scanning"""
    ci_workflow = Path(__file__).parent.parent / ".github/workflows/ci.yml"

    with open(ci_workflow, 'r') as f:
        content = f.read()

    # Check for security scanning tools
    security_tools = ['snyk', 'trivy', 'codeql', 'security', 'vulnerability', 'scan']
    has_security = any(tool in content.lower() for tool in security_tools)

    assert has_security, "CI workflow should include security scanning"