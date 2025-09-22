def test_import() -> None:
    """Test that engine modules can be imported."""
    import app.engine

    assert True


def test_python_version() -> None:
    """Ensure Python version is compatible."""
    import sys

    assert sys.version_info >= (3, 10)
