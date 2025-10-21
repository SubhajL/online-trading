"""Tests for import syntax fixer."""

import pytest
from app.engine.tools.import_syntax_fixer import ImportSyntaxFixer


def test_fix_missing_from_module():
    """Test fixing missing 'from module import' statements."""
    content = '''from ..bus import EventBus
from ..config import (
    EventType,
    Order,
    OrderStatus,
)'''

    expected = '''from ..bus import EventBus
from ..config import (
    EventType,
    Order,
    OrderStatus,
)'''

    result = ImportSyntaxFixer.fix_imports(content)
    assert result == expected


def test_fix_multiple_missing_from_statements():
    """Test fixing multiple missing from statements."""
    content = '''import logging
from ..adapters.db import Database
from ..config import (
    BaseEvent,
    EventType,
)
from ..shared.technical import (
    calculate_atr,
)
from ..config import (
    TimeFrame,
    Symbol,
)'''

    expected = '''import logging
from ..adapters.db import Database
from ..config import (
    BaseEvent,
    EventType,
)
from ..shared.technical import (
    calculate_atr,
)
from ..config import (
    TimeFrame,
    Symbol,
)'''

    result = ImportSyntaxFixer.fix_imports(content)
    assert result == expected


def test_preserve_correct_imports():
    """Test that correctly formatted imports are preserved."""
    content = '''from typing import Any, Dict
from ..models import (
    BaseEvent,
    EventType,
)
import numpy as np'''

    result = ImportSyntaxFixer.fix_imports(content)
    assert result == content


def test_fix_with_mixed_indentation():
    """Test fixing imports with different indentation styles."""
    content = '''from ..bus import EventBus
from ..config import (
    BaseEvent,
    Candle,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    TechnicalIndicators,
    TimeFrame,
)'''

    expected = '''from ..bus import EventBus
from ..config import (
    BaseEvent,
    Candle,
    CandleUpdateEvent,
    EventType,
    FeaturesCalculatedEvent,
    TechnicalIndicators,
    TimeFrame,
)'''

    result = ImportSyntaxFixer.fix_imports(content)
    assert result == expected


def test_handle_empty_content():
    """Test handling empty content."""
    assert ImportSyntaxFixer.fix_imports("") == ""


def test_fix_file_integration():
    """Test fixing imports in a file."""
    # Create a temporary file with broken imports
    import tempfile
    import os

    content = '''from ..bus import EventBus
from ..config import (
    EventType,
    Order,
)'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Fix the file
        ImportSyntaxFixer.fix_file(temp_path)

        # Read and verify
        with open(temp_path, 'r') as f:
            result = f.read()

        expected = '''from ..bus import EventBus
from ..config import (
    EventType,
    Order,
)'''

        assert result == expected
    finally:
        os.unlink(temp_path)


def test_get_files_with_import_errors(tmp_path):
    """Test finding files with import syntax errors."""
    # Create test files
    file1 = tmp_path / "file1.py"
    file1.write_text('''from     EventType,
    Order,
)''')

    file2 = tmp_path / "file2.py"
    file2.write_text('''from ..config import (
    EventType,
    Order,
)''')

    file3 = tmp_path / "file3.py"
    file3.write_text('''from     BaseEvent,
)''')

    # Find files with errors
    files_with_errors = ImportSyntaxFixer.get_files_with_import_errors(str(tmp_path))

    assert len(files_with_errors) == 2
    assert str(file1) in files_with_errors
    assert str(file3) in files_with_errors
    assert str(file2) not in files_with_errors
