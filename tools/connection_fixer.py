"""Compatibility wrapper exposing engine tools under simple test-oriented API.

This adapts detect_connection_patterns to return a list of (line, var)
tuples for connection_variable patterns, as expected by simpler tests.
Other functions are forwarded as-is.
"""

from typing import Any, List, Tuple

from app.engine.tools.connection_fixer import (  # type: ignore
    add_connection_type_hints as _engine_add_connection_type_hints,
    detect_connection_patterns as _engine_detect_connection_patterns,
    fix_connection_annotations,
    fix_file_connection_annotations,
)


def detect_connection_patterns(code: str) -> List[Tuple[int, str]]:
    patterns = _engine_detect_connection_patterns(code)
    result: List[Tuple[int, str]] = []
    for p in patterns:
        if p.get('type') == 'connection_variable':
            result.append((p.get('line', 0), p.get('variable', '')))
    return result


def add_connection_type_hints(arg: Any):  # proxy to engine
    return _engine_add_connection_type_hints(arg)
