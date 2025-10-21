"""Tests for config import fixer."""

import pytest
from app.engine.tools.config_import_fixer import ConfigImportFixer


def test_fix_config_to_models_import():
    """Test fixing imports from config to models."""
    content = '''from ..config import (
    BaseEvent,
    EventType,
    Candle,
    TimeFrame,
)'''

    expected = '''from ..models import (
    BaseEvent,
    EventType,
    Candle,
    TimeFrame,
)'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == expected


def test_fix_multiple_import_blocks():
    """Test fixing multiple import blocks."""
    content = '''from typing import Any
from ..bus import EventBus
from ..models import (
    BaseEvent,
    Candle,
)
from ..config import OrderSide
from ..models import TimeFrame'''

    expected = '''from typing import Any
from ..bus import EventBus
from ..models import (
    BaseEvent,
    Candle,
)
from ..models import OrderSide
from ..models import TimeFrame'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == expected


def test_preserve_real_config_imports():
    """Test that actual config imports are preserved."""
    content = '''from ..config import (
    EventBusConfig,
    DatabaseConfig,
)
from ..models import (
    BaseEvent,
    Candle,
)'''

    expected = '''from ..config import (
    EventBusConfig,
    DatabaseConfig,
)
from ..models import (
    BaseEvent,
    Candle,
)'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == expected


def test_fix_mixed_imports():
    """Test fixing imports with both config and model types."""
    content = '''from ..config import EventBusConfig, BaseEvent, Candle'''

    expected = '''from ..config import EventBusConfig
from ..models import BaseEvent, Candle'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == expected


def test_fix_single_line_model_import():
    """Test fixing single line imports of model types."""
    content = '''from ..config import BaseEvent'''

    expected = '''from ..models import BaseEvent'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == expected


def test_handle_empty_content():
    """Test handling empty content."""
    assert ConfigImportFixer.fix_config_imports("") == ""


def test_no_changes_when_no_config_imports():
    """Test that files without config imports are unchanged."""
    content = '''from ..models import BaseEvent, Candle
from typing import Any'''

    result = ConfigImportFixer.fix_config_imports(content)
    assert result == content


def test_fix_file_integration():
    """Test fixing a file with config import errors."""
    import tempfile
    import os

    content = '''from ..bus import EventBus
from ..models import (
    BaseEvent,
    Candle,
    TimeFrame,
)'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        # Fix the file
        ConfigImportFixer.fix_file(temp_path)

        # Read and verify
        with open(temp_path, 'r') as f:
            result = f.read()

        expected = '''from ..bus import EventBus
from ..models import (
    BaseEvent,
    Candle,
    TimeFrame,
)'''

        assert result == expected
    finally:
        os.unlink(temp_path)
