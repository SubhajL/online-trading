"""Map existing tests to appropriate test levels."""

from pathlib import Path
import re
from typing import Dict, List


def get_test_level(test_path: str) -> int:
    """
    Analyze a test file to determine its appropriate level.

    Levels:
    - 0: Import tests (no dependencies)
    - 1: Unit tests (mocked dependencies)
    - 2: Service tests (real DB/Redis)
    - 3: Integration tests (all services)
    - 4: End-to-end tests (with UI)

    Args:
        test_path: Path to the test file

    Returns:
        Test level (0-4)
    """
    path = Path(test_path)

    # First check directory structure for hints
    path_str = str(path)
    if "/unit/" in path_str:
        # Unit tests default to level 1 unless they're import tests
        if "import" in path.name.lower():
            return 0
        return 1
    elif "/integration/" in path_str:
        return 3
    elif "/e2e/" in path_str or "/end_to_end/" in path_str:
        return 4
    elif "/performance/" in path_str or "/chaos/" in path_str:
        return 3  # These need full system

    # Analyze file content if it exists
    try:
        content = path.read_text()
    except Exception:
        # If we can't read the file, make a guess based on name
        if "import" in path.name.lower():
            return 0
        return 1

    # Level 4: E2E with UI/Browser
    if any(pattern in content for pattern in [
        "selenium", "webdriver", "puppeteer", "playwright",
        "from app.ui", "app/ui/", "localhost:3000"
    ]):
        return 4

    # Level 3: Integration tests
    if any(pattern in content for pattern in [
        "test_integration", "test_e2e", "test_full_",
        "EventBus()", "multiple services", "all services",
        "start_all", "complete flow", "full pipeline"
    ]) or content.count("Service()") >= 2:
        return 3

    # Level 2: Service tests with real infrastructure
    if any(pattern in content for pattern in [
        "real_db", "real_redis", "real_connection",
        "@pytest.fixture\nasync def.*db", "@pytest.fixture\nasync def.*redis",
        "asyncpg", "aioredis", "create_pool",
        "test_infrastructure", "test_service"
    ]):
        return 2

    # Level 0: Import tests
    if any(pattern in content for pattern in [
        "test_import", "test_no_syntax", "test_circular",
        "from app.engine import", "assert.*is not None",
        "__all__", "test_type_definitions"
    ]) and "mock" not in content.lower():
        return 0

    # Level 1: Unit tests (default for anything with mocks)
    if any(pattern in content for pattern in [
        "mock", "patch", "MagicMock", "AsyncMock",
        "@patch", "unittest.mock"
    ]):
        return 1

    # Default to level 1 for other tests
    return 1


def categorize_existing_tests() -> Dict[int, List[str]]:
    """
    Scan existing test directories and categorize tests by level.

    Returns:
        Dictionary mapping level number to list of test file paths
    """
    categorized = {0: [], 1: [], 2: [], 3: [], 4: []}

    # Find all test files
    test_root = Path("app/engine/tests")
    test_files = []

    # Use rglob to find all test files recursively
    for pattern in ["test_*.py", "*_test.py"]:
        test_files.extend(test_root.rglob(pattern))

    # De-duplicate in case a file matches multiple patterns (e.g. `test_foo_test.py`) or
    # a mocked rglob returns the same list for both patterns.
    unique_test_files: list[Path] = []
    seen: set[Path] = set()
    for test_file in test_files:
        if test_file in seen:
            continue
        seen.add(test_file)
        unique_test_files.append(test_file)

    # Process each test file
    for test_file in unique_test_files:
        # Skip __init__.py and non-test helper files
        if test_file.name == "__init__.py" or test_file.name == "conftest.py":
            continue

        # Skip if not actually a test file
        if not test_file.name.startswith("test_") and not test_file.name.endswith("_test.py"):
            continue

        # Determine level and add to appropriate list
        level = get_test_level(str(test_file))
        categorized[level].append(str(test_file))

    # Sort paths for consistent output
    for level in categorized:
        categorized[level].sort()

    return categorized


def generate_level_report() -> str:
    """Generate a report of test distribution across levels."""
    categorized = categorize_existing_tests()

    lines = []
    lines.append("\nTest Level Distribution")
    lines.append("=" * 50)

    level_names = {
        0: "Import tests (no dependencies)",
        1: "Unit tests (mocked dependencies)",
        2: "Service tests (real DB/Redis)",
        3: "Integration tests (all services)",
        4: "End-to-end tests (with UI)"
    }

    total_tests = 0
    for level in range(5):
        count = len(categorized[level])
        total_tests += count
        lines.append(f"\nLevel {level}: {level_names[level]}")
        lines.append(f"  Count: {count}")

        if count > 0 and count <= 5:
            # Show first few examples
            lines.append("  Examples:")
            for test_path in categorized[level][:5]:
                lines.append(f"    - {test_path}")
        elif count > 5:
            lines.append(f"  Showing first 3 of {count}:")
            for test_path in categorized[level][:3]:
                lines.append(f"    - {test_path}")
            lines.append("    ...")

    lines.append(f"\nTotal tests: {total_tests}")

    return "\n".join(lines)
