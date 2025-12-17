"""
Exponential backoff strategy for resilient reconnection.
"""

from dataclasses import dataclass
import random


@dataclass
class BackoffConfig:
    """Configuration for exponential backoff."""

    base_delay_s: float = 5.0
    max_delay_s: float = 300.0
    multiplier: float = 2.0
    jitter_pct: float = 0.1

    def __post_init__(self) -> None:
        """Validate config values are positive."""
        if self.base_delay_s <= 0:
            msg = f"base_delay_s must be positive, got {self.base_delay_s}"
            raise ValueError(msg)
        if self.max_delay_s <= 0:
            msg = f"max_delay_s must be positive, got {self.max_delay_s}"
            raise ValueError(msg)
        if self.multiplier <= 0:
            msg = f"multiplier must be positive, got {self.multiplier}"
            raise ValueError(msg)
        if self.jitter_pct < 0 or self.jitter_pct > 1:
            msg = f"jitter_pct must be in [0, 1], got {self.jitter_pct}"
            raise ValueError(msg)


class ExponentialBackoff:
    """
    Exponential backoff with jitter for reconnection delays.

    Computes delay as: min(base * multiplier^attempts, max) * jitter_factor
    where jitter_factor is uniform random in [1 - jitter_pct, 1 + jitter_pct].
    """

    def __init__(self, config: BackoffConfig | None = None) -> None:
        self._config = config or BackoffConfig()
        self._attempts = 0

    def next_delay(self) -> float:
        """
        Compute next delay with exponential growth and optional jitter.

        Increments attempt counter after computing delay.
        """
        base = self._config.base_delay_s
        multiplier = self._config.multiplier
        max_delay = self._config.max_delay_s
        jitter_pct = self._config.jitter_pct

        # Exponential growth: base * multiplier^attempts
        raw_delay = base * (multiplier ** self._attempts)

        # Cap at maximum
        capped_delay = min(raw_delay, max_delay)

        # Apply jitter
        if jitter_pct > 0:
            jitter_factor = random.uniform(1 - jitter_pct, 1 + jitter_pct)  # noqa: S311
            final_delay = capped_delay * jitter_factor
        else:
            final_delay = capped_delay

        self._attempts += 1
        return final_delay

    def reset(self) -> None:
        """Reset attempt counter to zero for use after successful connection."""
        self._attempts = 0

    @property
    def current_attempt(self) -> int:
        """Return current attempt count for logging and health checks."""
        return self._attempts
