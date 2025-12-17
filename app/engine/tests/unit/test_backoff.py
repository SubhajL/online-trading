"""
Unit tests for exponential backoff strategy.
TDD: Written first, implementation follows.
"""
# ruff: noqa: PLR2004

from unittest.mock import MagicMock, patch

import pytest

from app.engine.resilience.backoff import BackoffConfig, ExponentialBackoff


class TestBackoffConfigValidation:
    """Tests for BackoffConfig input validation."""

    def test_rejects_zero_base_delay(self) -> None:
        with pytest.raises(ValueError, match="base_delay_s must be positive"):
            BackoffConfig(base_delay_s=0)

    def test_rejects_negative_base_delay(self) -> None:
        with pytest.raises(ValueError, match="base_delay_s must be positive"):
            BackoffConfig(base_delay_s=-5.0)

    def test_rejects_zero_max_delay(self) -> None:
        with pytest.raises(ValueError, match="max_delay_s must be positive"):
            BackoffConfig(max_delay_s=0)

    def test_rejects_negative_max_delay(self) -> None:
        with pytest.raises(ValueError, match="max_delay_s must be positive"):
            BackoffConfig(max_delay_s=-10.0)

    def test_rejects_zero_multiplier(self) -> None:
        with pytest.raises(ValueError, match="multiplier must be positive"):
            BackoffConfig(multiplier=0)

    def test_rejects_negative_multiplier(self) -> None:
        with pytest.raises(ValueError, match="multiplier must be positive"):
            BackoffConfig(multiplier=-2.0)

    def test_rejects_negative_jitter(self) -> None:
        with pytest.raises(ValueError, match=r"jitter_pct must be in \[0, 1\]"):
            BackoffConfig(jitter_pct=-0.1)

    def test_rejects_jitter_above_one(self) -> None:
        with pytest.raises(ValueError, match=r"jitter_pct must be in \[0, 1\]"):
            BackoffConfig(jitter_pct=1.5)

    def test_accepts_zero_jitter(self) -> None:
        config = BackoffConfig(jitter_pct=0.0)
        assert config.jitter_pct == 0.0

    def test_accepts_max_jitter(self) -> None:
        config = BackoffConfig(jitter_pct=1.0)
        assert config.jitter_pct == 1.0


class TestBackoffConfig:
    def test_default_values(self) -> None:
        config = BackoffConfig()

        assert config.base_delay_s == 5.0
        assert config.max_delay_s == 300.0
        assert config.multiplier == 2.0
        assert config.jitter_pct == 0.1

    def test_custom_values(self) -> None:
        config = BackoffConfig(
            base_delay_s=10.0,
            max_delay_s=600.0,
            multiplier=3.0,
            jitter_pct=0.2,
        )

        assert config.base_delay_s == 10.0
        assert config.max_delay_s == 600.0
        assert config.multiplier == 3.0
        assert config.jitter_pct == 0.2


class TestExponentialBackoff:
    def test_initial_delay_equals_base(self) -> None:
        config = BackoffConfig(base_delay_s=5.0, jitter_pct=0.0)
        backoff = ExponentialBackoff(config)

        delay = backoff.next_delay()

        assert delay == 5.0

    def test_delay_grows_exponentially(self) -> None:
        config = BackoffConfig(base_delay_s=5.0, multiplier=2.0, jitter_pct=0.0)
        backoff = ExponentialBackoff(config)

        delays = [backoff.next_delay() for _ in range(4)]

        assert delays == [5.0, 10.0, 20.0, 40.0]

    def test_delay_capped_at_max(self) -> None:
        config = BackoffConfig(
            base_delay_s=5.0,
            max_delay_s=30.0,
            multiplier=2.0,
            jitter_pct=0.0,
        )
        backoff = ExponentialBackoff(config)

        delays = [backoff.next_delay() for _ in range(10)]

        # 5, 10, 20, 30, 30, 30, ...
        assert delays[3:] == [30.0] * 7

    def test_reset_restores_initial_delay(self) -> None:
        config = BackoffConfig(base_delay_s=5.0, jitter_pct=0.0)
        backoff = ExponentialBackoff(config)

        backoff.next_delay()  # 5
        backoff.next_delay()  # 10
        backoff.next_delay()  # 20

        backoff.reset()

        assert backoff.next_delay() == 5.0
        assert backoff.current_attempt == 1

    def test_current_attempt_increments(self) -> None:
        config = BackoffConfig()
        backoff = ExponentialBackoff(config)

        assert backoff.current_attempt == 0

        backoff.next_delay()
        assert backoff.current_attempt == 1

        backoff.next_delay()
        assert backoff.current_attempt == 2

    def test_jitter_varies_delay_within_bounds(self) -> None:
        config = BackoffConfig(base_delay_s=100.0, jitter_pct=0.1)
        backoff = ExponentialBackoff(config)

        # With 10% jitter on 100s base, delay should be in [90, 110]
        delays = [backoff.reset() or backoff.next_delay() for _ in range(50)]

        assert all(90.0 <= d <= 110.0 for d in delays)
        # Verify there's actual variation (not all the same)
        assert len(set(delays)) > 1

    def test_zero_jitter_gives_deterministic_values(self) -> None:
        config = BackoffConfig(base_delay_s=5.0, jitter_pct=0.0)

        backoff1 = ExponentialBackoff(config)
        backoff2 = ExponentialBackoff(config)

        delays1 = [backoff1.next_delay() for _ in range(5)]
        delays2 = [backoff2.next_delay() for _ in range(5)]

        assert delays1 == delays2

    @patch("app.engine.resilience.backoff.random.uniform")
    def test_jitter_applies_symmetric_variation(self, mock_uniform: MagicMock) -> None:
        mock_uniform.return_value = 0.95  # -5% jitter
        config = BackoffConfig(base_delay_s=100.0, jitter_pct=0.1)
        backoff = ExponentialBackoff(config)

        delay = backoff.next_delay()

        # Base 100 * 0.95 = 95
        assert delay == 95.0
        mock_uniform.assert_called_once_with(0.9, 1.1)
