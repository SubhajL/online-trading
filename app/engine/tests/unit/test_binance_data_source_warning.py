"""
Unit tests for the BINANCE_DATA_SOURCE thin-data warning.
"""

from __future__ import annotations

import logging

import pytest

from app.engine.main import _binance_data_testnet_from_env


def test_testnet_data_source_logs_thin_data_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("BINANCE_DATA_SOURCE", "testnet")

    with caplog.at_level(logging.WARNING):
        result = _binance_data_testnet_from_env()

    assert (result, "thin" in caplog.text) == (True, True)


def test_mainnet_data_source_logs_no_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("BINANCE_DATA_SOURCE", "mainnet")

    with caplog.at_level(logging.WARNING):
        result = _binance_data_testnet_from_env()

    assert (result, caplog.text) == (False, "")
