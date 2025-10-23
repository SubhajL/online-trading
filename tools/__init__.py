"""Compatibility wrapper exposing engine tools at top-level package."""

from app.engine.tools.connection_fixer import (
    detect_connection_patterns,
    add_connection_type_hints,
    fix_connection_annotations,
    fix_file_connection_annotations,
)

__all__ = [
    "detect_connection_patterns",
    "add_connection_type_hints",
    "fix_connection_annotations",
    "fix_file_connection_annotations",
]
