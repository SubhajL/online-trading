"""
Tests for live_paper_vs_captain.py comparison script.

Tests cover the pure logic functions without spawning real processes.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBuildArgumentParser:
    """Tests for argument parser construction."""

    def test_parser_has_source_argument(self) -> None:
        """Parser includes --source argument."""
        from scripts.live_paper_vs_captain import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args(["--source", "test_source"])

        assert args.source == "test_source"

    def test_source_defaults_to_captain(self) -> None:
        """--source defaults to 'captain' when not provided."""
        from scripts.live_paper_vs_captain import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args([])

        assert args.source == "captain"

    def test_parser_has_poll_interval_argument(self) -> None:
        """Parser includes --poll-interval argument."""
        from scripts.live_paper_vs_captain import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args(["--poll-interval", "30"])

        assert args.poll_interval == 30

    def test_poll_interval_defaults_to_60(self) -> None:
        """--poll-interval defaults to 60 seconds."""
        from scripts.live_paper_vs_captain import build_argument_parser

        parser = build_argument_parser()
        args = parser.parse_args([])

        assert args.poll_interval == 60


class TestBuildComparisonCommand:
    """Tests for captain listener command construction."""

    def test_builds_command_with_source(self) -> None:
        """Builds command with --listen and --source flags."""
        from scripts.live_paper_vs_captain import build_captain_listener_command

        cmd = build_captain_listener_command(source="test_source")

        assert "--listen" in cmd
        assert "--source" in cmd
        assert "test_source" in cmd


class TestFormatComparisonMetrics:
    """Tests for metrics formatting."""

    def test_formats_timing_delta(self) -> None:
        """Formats timing_delta_seconds correctly."""
        from scripts.live_paper_vs_captain import format_comparison_metrics

        metrics = {
            "timing_delta_seconds": 2.5,
            "captain_count": 10,
            "internal_count": 8,
            "matched_count": 7,
        }

        output = format_comparison_metrics(metrics)

        assert "2.5" in output or "2.50" in output
        assert "timing" in output.lower()

    def test_formats_counts(self) -> None:
        """Formats signal counts correctly."""
        from scripts.live_paper_vs_captain import format_comparison_metrics

        metrics = {
            "timing_delta_seconds": 1.0,
            "captain_count": 10,
            "internal_count": 8,
            "matched_count": 7,
        }

        output = format_comparison_metrics(metrics)

        assert "10" in output
        assert "8" in output
        assert "7" in output
