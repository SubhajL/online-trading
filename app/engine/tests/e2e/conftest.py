"""E2E test configuration.

Tests in this directory require the full stack: BFF, Telegram, Binance testnet, etc.
Run with: pytest -m e2e
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "e2e: mark test as end-to-end requiring full stack (BFF, Telegram, Binance)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    for item in items:
        existing = {m.name for m in item.iter_markers()}
        if "e2e" not in existing:
            item.add_marker(pytest.mark.e2e)
