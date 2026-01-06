import pytest

from app.engine.execution.router_execution_subscriber import (
    ExecutionMode,
    execution_mode_from_env,
)


class TestExecutionModeFromEnv:
    def test_defaults_to_disabled(self) -> None:
        assert execution_mode_from_env({}) == ExecutionMode.DISABLED

    def test_rejects_unknown_value(self) -> None:
        with pytest.raises(RuntimeError, match="Unknown EXECUTION_MODE"):
            execution_mode_from_env({"EXECUTION_MODE": "nope"})

    def test_requires_ack_for_mainnet(self) -> None:
        with pytest.raises(RuntimeError, match="I_UNDERSTAND_LIVE_TRADING"):
            execution_mode_from_env({"EXECUTION_MODE": "futures_mainnet"})
