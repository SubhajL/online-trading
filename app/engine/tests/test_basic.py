def test_import():
    """Test that engine modules can be imported."""
    import app.engine

    assert True


def test_python_version():
    """Ensure Python version is compatible."""
    import sys

    assert sys.version_info >= (3, 10)
