"""
Helpers to load per-endpoint circuit breaker configurations from environment.
"""

from __future__ import annotations

import json
import os

from app.engine.resilience.thread_safe_circuit_breaker import CircuitBreakerConfig


def _parse_breakers_json(env_value: str) -> dict[str, CircuitBreakerConfig]:
    try:
        raw = json.loads(env_value)
        if not isinstance(raw, dict):
            raise ValueError("breaker JSON must be an object")
        result: dict[str, CircuitBreakerConfig] = {}
        for key, cfg in raw.items():
            if not isinstance(key, str) or ":" not in key:
                raise ValueError(f"invalid breaker key: {key!r}")
            if not isinstance(cfg, dict):
                raise ValueError(f"invalid breaker config for {key}")
            ft = cfg.get("failure_threshold")
            st = cfg.get("success_threshold")
            to = cfg.get("timeout_seconds")
            if ft is None or st is None or to is None:
                raise ValueError(f"missing fields in breaker config for {key}")
            result[key] = CircuitBreakerConfig(
                failure_threshold=int(ft),
                success_threshold=int(st),
                timeout_seconds=float(to),
            )
        return result
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid breaker JSON: {e}")


def router_breaker_config_from_env() -> dict[str, CircuitBreakerConfig]:
    """Load Router per-endpoint breaker configs from ROUTER_BREAKERS_JSON env."""
    val = os.getenv("ROUTER_BREAKERS_JSON")
    if not val:
        return {}
    return _parse_breakers_json(val)


def binance_breaker_config_from_env() -> dict[str, CircuitBreakerConfig]:
    """Load Binance per-endpoint breaker configs from BINANCE_BREAKERS_JSON env."""
    val = os.getenv("BINANCE_BREAKERS_JSON")
    if not val:
        return {}
    return _parse_breakers_json(val)
