import os
from typing import Optional
from urllib.parse import urlparse, urlunparse


def get_test_database_url() -> str:
    """Get test database URL, ensuring isolation from production"""
    # Check if TEST_DATABASE_URL is explicitly set
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        return test_url
    
    # Fall back to modifying DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "postgresql://localhost/trader")
    
    # Parse the URL
    parsed = urlparse(database_url)
    
    # Append '_test' to the database name
    path_parts = parsed.path.split('/')
    if len(path_parts) > 1 and path_parts[1]:
        path_parts[1] = f"{path_parts[1]}_test"
    else:
        path_parts = ['', 'trader_test']
    
    # Reconstruct the URL
    test_parsed = parsed._replace(path='/'.join(path_parts))
    test_url = urlunparse(test_parsed)
    
    return test_url


class TestDatabase:
    """Context manager for test database setup and teardown"""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or get_test_database_url()
        self._original_url = os.getenv("DATABASE_URL")
    
    async def __aenter__(self):
        """Set up test database environment"""
        # Override DATABASE_URL for the duration of the test
        os.environ["DATABASE_URL"] = self.database_url
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Restore original database environment"""
        if self._original_url:
            os.environ["DATABASE_URL"] = self._original_url
        else:
            os.environ.pop("DATABASE_URL", None)


def ensure_test_database() -> None:
    """Ensure we're using a test database, not production"""
    database_url = os.getenv("DATABASE_URL", "")
    if "test" not in database_url.lower() and not os.getenv("ALLOW_PRODUCTION_DATABASE"):
        raise RuntimeError(
            "Tests must use a test database. "
            "Set TEST_DATABASE_URL or ensure DATABASE_URL contains 'test'."
        )
