"""
Tests for live_paper_vs_captain.py comparison script.

Tests cover the pure logic functions without spawning real processes.
"""

from __future__ import annotations

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


class TestDrainStream:
    """Tests for async stream draining."""

    @pytest.mark.asyncio
    async def test_drain_stream_reads_all_lines(self) -> None:
        """_drain_stream reads all lines from stream and logs them."""
        from scripts.live_paper_vs_captain import _drain_stream

        # Create mock stream with test data
        test_lines = [b"line 1\n", b"line 2\n", b"line 3\n"]

        class MockStream:
            def __init__(self, lines: list[bytes]) -> None:
                self._lines = iter(lines)

            async def readline(self) -> bytes:
                try:
                    return next(self._lines)
                except StopIteration:
                    return b""

        mock_stream = MockStream(test_lines)
        collected: list[str] = []

        async def collect_lines() -> None:
            async for line in _drain_stream(mock_stream, "TEST"):  # type: ignore[arg-type]
                collected.append(line)

        await collect_lines()

        assert len(collected) == 3
        assert collected[0] == "line 1"
        assert collected[1] == "line 2"
        assert collected[2] == "line 3"

    @pytest.mark.asyncio
    async def test_drain_stream_handles_empty_stream(self) -> None:
        """_drain_stream handles empty stream gracefully."""
        from scripts.live_paper_vs_captain import _drain_stream

        class MockEmptyStream:
            async def readline(self) -> bytes:
                return b""

        mock_stream = MockEmptyStream()
        collected: list[str] = []

        async for line in _drain_stream(mock_stream, "TEST"):  # type: ignore[arg-type]
            collected.append(line)

        assert len(collected) == 0

    @pytest.mark.asyncio
    async def test_drain_stream_strips_newlines(self) -> None:
        """_drain_stream strips trailing newlines from lines."""
        from scripts.live_paper_vs_captain import _drain_stream

        class MockStream:
            def __init__(self) -> None:
                self._called = False

            async def readline(self) -> bytes:
                if not self._called:
                    self._called = True
                    return b"test line\r\n"
                return b""

        mock_stream = MockStream()
        collected: list[str] = []

        async for line in _drain_stream(mock_stream, "TEST"):  # type: ignore[arg-type]
            collected.append(line)

        assert collected[0] == "test line"


class TestStartCaptainListenerAsync:
    """Tests for async subprocess spawning with drain tasks."""

    @pytest.mark.asyncio
    async def test_start_captain_listener_returns_process_and_tasks(self) -> None:
        """start_captain_listener_async returns (process, drain_tasks) tuple."""
        import asyncio

        from scripts.live_paper_vs_captain import start_captain_listener_async

        # Use a simple command that exits immediately
        process, drain_tasks = await start_captain_listener_async(
            source="test",
            command=["echo", "hello"],
        )

        try:
            # Should return process and list of drain tasks
            assert process is not None
            assert hasattr(process, "pid")
            assert isinstance(drain_tasks, list)
            assert len(drain_tasks) == 2  # stdout and stderr drain tasks

            # Wait for completion
            await process.wait()
            for task in drain_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if process.returncode is None:
                process.terminate()

    @pytest.mark.asyncio
    async def test_captain_listener_no_deadlock_on_large_output(self) -> None:
        """Process doesn't deadlock when generating >64KB output."""
        import asyncio

        from scripts.live_paper_vs_captain import start_captain_listener_async

        # Generate large output (>64KB pipe buffer)
        # Each line is ~80 chars, need ~1000 lines to exceed 64KB
        script = (
            "for i in $(seq 1 1500); do "
            "echo 'test output line number $i with some padding to make it longer'; "
            "done"
        )
        command = ["sh", "-c", script]

        process, drain_tasks = await start_captain_listener_async(
            source="test",
            command=command,
        )

        try:
            # Wait with timeout - should NOT deadlock
            await asyncio.wait_for(process.wait(), timeout=5.0)
            assert process.returncode == 0

            # Let drain tasks complete
            for task in drain_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        except asyncio.TimeoutError:
            pytest.fail("Process deadlocked - pipe buffer filled")
        finally:
            if process.returncode is None:
                process.terminate()

    @pytest.mark.asyncio
    async def test_start_captain_listener_spawns_drain_tasks(self) -> None:
        """Drain tasks actively consume stdout/stderr."""
        import asyncio

        from scripts.live_paper_vs_captain import start_captain_listener_async

        # Command that outputs to both stdout and stderr
        command = ["sh", "-c", "echo stdout_line; echo stderr_line >&2"]

        process, drain_tasks = await start_captain_listener_async(
            source="test",
            command=command,
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)

            # Drain tasks should be Task objects
            assert all(isinstance(t, asyncio.Task) for t in drain_tasks)

            # Cancel tasks after process completes
            for task in drain_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if process.returncode is None:
                process.terminate()
