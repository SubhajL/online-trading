"""Integration tests for LINE alert adapter.

LINE integration is not yet implemented. These tests are skipped.
TODO: Implement LINE alert adapter and enable these tests.
"""

import pytest


@pytest.mark.skip(reason="LINE alert adapter not yet implemented")
class TestLineRealIntegration:
    """Real integration tests for LINE - currently skipped."""

    @pytest.mark.asyncio
    async def test_placeholder(self) -> None:
        """Placeholder test - LINE not implemented."""
        pass
