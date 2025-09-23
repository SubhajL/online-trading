"""
Test suite for generic type parameter fixer

Tests the detection and fixing of missing type parameters for generic types
"""

import pytest
from app.engine.tools.generic_type_fixer import (
    detect_missing_generic_parameters,
    infer_generic_parameters,
    add_generic_type_parameters,
    fix_generic_type_parameters
)


class TestDetectMissingGenericParameters:
    """Tests for detecting missing generic type parameters"""

    def test_detect_bare_dict_type(self):
        """Should detect dict without type parameters"""
        code = '''
def get_config() -> dict:
    return {"key": "value"}

def process_data(data: dict) -> None:
    print(data)
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 2
        assert missing[0]['type_name'] == 'dict'
        assert missing[0]['line'] == 1
        assert missing[0]['context'] == 'return'
        assert missing[1]['line'] == 4
        assert missing[1]['context'] == 'argument'

    def test_detect_bare_list_type(self):
        """Should detect list without type parameters"""
        code = '''
def get_items() -> list:
    return [1, 2, 3]

items: list = []
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 2
        assert all(m['type_name'] == 'list' for m in missing)

    def test_detect_bare_tuple_type(self):
        """Should detect tuple without type parameters"""
        code = '''
def get_coordinates() -> tuple:
    return (10, 20)

coord: tuple = (0, 0)
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 2
        assert all(m['type_name'] == 'tuple' for m in missing)

    def test_detect_bare_callable_type(self):
        """Should detect Callable without type parameters"""
        code = '''
from typing import Callable

def register_callback(func: Callable) -> None:
    callbacks.append(func)
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 1
        assert missing[0]['type_name'] == 'Callable'

    def test_detect_bare_generic_classes(self):
        """Should detect other generic types without parameters"""
        code = '''
from typing import Deque, Optional
from collections import deque
from queue import Queue, PriorityQueue
from asyncio import Task, Future

items: Deque = deque()
task: Task = None
future: Future = None
q: Queue = Queue()
pq: PriorityQueue = PriorityQueue()
'''
        missing = detect_missing_generic_parameters(code)
        type_names = [m['type_name'] for m in missing]
        assert 'Deque' in type_names
        assert 'Task' in type_names
        assert 'Future' in type_names
        assert 'Queue' in type_names
        assert 'PriorityQueue' in type_names

    def test_ignore_properly_parameterized_types(self):
        """Should ignore types that already have parameters"""
        code = '''
from typing import Dict, List, Tuple, Callable

def get_config() -> Dict[str, Any]:
    return {}

items: List[int] = [1, 2, 3]
coord: Tuple[int, int] = (0, 0)
func: Callable[[str], bool] = lambda x: True
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 0

    def test_detect_in_complex_annotations(self):
        """Should detect in complex type annotations"""
        code = '''
from typing import Union, Optional

def process(data: Union[dict, None]) -> Optional[list]:
    if data:
        return list(data.values())
    return None
'''
        missing = detect_missing_generic_parameters(code)
        assert len(missing) == 2
        assert missing[0]['type_name'] == 'dict'
        assert missing[0]['within_union'] is True
        assert missing[1]['type_name'] == 'list'
        assert missing[1]['within_optional'] is True


class TestInferGenericParameters:
    """Tests for inferring generic type parameters"""

    def test_infer_dict_from_literal(self):
        """Should infer dict parameters from dict literal"""
        code = '''
def get_config() -> dict:
    return {"host": "localhost", "port": 8080}
'''
        params = infer_generic_parameters(code, 'dict', 'get_config', 1)
        assert params == '[str, Any]'

    def test_infer_dict_with_mixed_values(self):
        """Should infer dict[str, Any] for mixed value types"""
        code = '''
def get_data() -> dict:
    return {"name": "test", "count": 42, "active": True}
'''
        params = infer_generic_parameters(code, 'dict', 'get_data', 1)
        assert params == '[str, Any]'

    def test_infer_list_from_literal(self):
        """Should infer list parameters from list literal"""
        code = '''
def get_numbers() -> list:
    return [1, 2, 3, 4, 5]
'''
        params = infer_generic_parameters(code, 'list', 'get_numbers', 1)
        assert params == '[int]'

    def test_infer_list_with_mixed_types(self):
        """Should infer list[Any] for mixed types"""
        code = '''
def get_items() -> list:
    return [1, "two", 3.0, True]
'''
        params = infer_generic_parameters(code, 'list', 'get_items', 1)
        assert params == '[Any]'

    def test_infer_tuple_from_literal(self):
        """Should infer tuple parameters from tuple literal"""
        code = '''
def get_point() -> tuple:
    return (10, 20)
'''
        params = infer_generic_parameters(code, 'tuple', 'get_point', 1)
        assert params == '[int, int]'

    def test_infer_tuple_ellipsis_for_uniform(self):
        """Should infer tuple[type, ...] for uniform tuples"""
        code = '''
def get_values() -> tuple:
    return tuple(range(10))
'''
        params = infer_generic_parameters(code, 'tuple', 'get_values', 1)
        assert params == '[Any, ...]'

    def test_infer_callable_from_usage(self):
        """Should infer Callable parameters from usage"""
        code = '''
def register(callback: Callable) -> None:
    result = callback("test")
    print(result)
'''
        params = infer_generic_parameters(code, 'Callable', 'register', 1)
        assert params == '[..., Any]'  # Generic callable signature

    def test_cannot_infer_parameters(self):
        """Should return safe defaults when cannot infer"""
        code = '''
def mystery(data: dict) -> None:
    # No usage to infer from
    pass
'''
        params = infer_generic_parameters(code, 'dict', 'mystery', 1)
        assert params == '[Any, Any]'


class TestAddGenericTypeParameters:
    """Tests for adding generic type parameters"""

    def test_add_dict_parameters(self):
        """Should add parameters to bare dict types"""
        code = '''
def get_config() -> dict:
    return {}

def process(data: dict) -> None:
    pass
'''
        result = add_generic_type_parameters(code)
        assert 'def get_config() -> dict[Any, Any]:' in result
        assert 'def process(data: dict[Any, Any]) -> None:' in result

    def test_add_list_parameters(self):
        """Should add parameters to bare list types"""
        code = '''
numbers: list = [1, 2, 3]

def get_items() -> list:
    return []
'''
        result = add_generic_type_parameters(code)
        assert 'numbers: list[Any]' in result
        assert 'def get_items() -> list[Any]:' in result

    def test_add_tuple_parameters(self):
        """Should add parameters to bare tuple types"""
        code = '''
point: tuple = (0, 0)

def get_coords() -> tuple:
    return (10, 20)
'''
        result = add_generic_type_parameters(code)
        assert 'point: tuple[Any, ...]' in result
        assert any('-> tuple[' in line for line in result.split('\n'))

    def test_add_callable_parameters(self):
        """Should add parameters to bare Callable types"""
        code = '''
from typing import Callable

def register(func: Callable) -> None:
    pass
'''
        result = add_generic_type_parameters(code)
        assert 'func: Callable[..., Any]' in result

    def test_handle_union_types(self):
        """Should handle generic types within Union"""
        code = '''
from typing import Union

def process(data: Union[dict, None]) -> Union[list, str]:
    return []
'''
        result = add_generic_type_parameters(code)
        assert 'Union[dict[Any, Any], None]' in result
        assert 'Union[list[Any], str]' in result

    def test_handle_optional_types(self):
        """Should handle generic types within Optional"""
        code = '''
from typing import Optional

def get_data() -> Optional[dict]:
    return None
'''
        result = add_generic_type_parameters(code)
        assert 'Optional[dict[Any, Any]]' in result

    def test_preserve_existing_parameters(self):
        """Should not modify already parameterized types"""
        code = '''
from typing import Dict, List

def process(items: List[int], mapping: dict) -> Dict[str, int]:
    return {}
'''
        result = add_generic_type_parameters(code)
        assert 'items: List[int]' in result  # Unchanged
        assert 'mapping: dict[Any, Any]' in result  # Added
        assert '-> Dict[str, int]:' in result  # Unchanged

    def test_add_imports_if_needed(self):
        """Should add Any import if not present"""
        code = '''
def get_items() -> list:
    return []
'''
        result = add_generic_type_parameters(code)
        assert 'from typing import Any' in result
        assert '-> list[Any]:' in result


class TestFixGenericTypeParameters:
    """Tests for the main fix function"""

    def test_fix_multiple_generic_types(self):
        """Should fix all generic types in a file"""
        code = '''
from collections import deque
from queue import Queue

class DataProcessor:
    def __init__(self):
        self.items: list = []
        self.cache: dict = {}
        self.queue: Queue = Queue()

    def process(self, data: dict) -> tuple:
        return ("result", 42)

    def register(self, callback: Callable) -> None:
        self.callbacks.append(callback)
'''
        result = fix_generic_type_parameters(code)
        assert 'self.items: list[Any]' in result
        assert 'self.cache: dict[Any, Any]' in result
        assert 'self.queue: Queue[Any]' in result
        assert 'data: dict[Any, Any]' in result
        assert '-> tuple[' in result
        assert 'callback: Callable[' in result

    def test_handle_asyncio_types(self):
        """Should handle asyncio generic types"""
        code = '''
import asyncio
from asyncio import Task, Future

class AsyncManager:
    def __init__(self):
        self.tasks: list[Task] = []
        self.future: Future = None

    async def run(self) -> Task:
        return asyncio.create_task(self.work())
'''
        result = fix_generic_type_parameters(code)
        assert 'self.tasks: list[Task[Any]]' in result
        assert 'self.future: Future[Any]' in result
        assert '-> Task[Any]:' in result

    def test_preserve_module_structure(self):
        """Should preserve imports, docstrings, and formatting"""
        code = '''
"""Module docstring"""

import asyncio
from typing import Optional
from collections import deque

# Constants
MAX_SIZE = 100

def process_queue(q: deque) -> Optional[dict]:
    """Process items from queue."""
    if q:
        return q.popleft()
    return None
'''
        result = fix_generic_type_parameters(code)
        assert '"""Module docstring"""' in result
        assert '# Constants' in result
        assert 'MAX_SIZE = 100' in result
        assert '"""Process items from queue."""' in result
        assert 'q: deque[Any]' in result
        assert 'Optional[dict[Any, Any]]' in result