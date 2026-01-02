"""Telegram signal validation package.

This package includes optional integrations (e.g. Telethon). Importing the
package should not require optional dependencies unless those integrations are
actually used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = [
    "SignalParser",
    "TelegramSignal",
    "TelegramSignalValidator",
    "ValidationResult",
]

if TYPE_CHECKING:
    from .telegram_signal_validator import (
        SignalParser,
        TelegramSignal,
        TelegramSignalValidator,
        ValidationResult,
    )


def __getattr__(name: str) -> object:
    if name not in __all__:
        raise AttributeError(name)

    module = import_module(".telegram_signal_validator", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
