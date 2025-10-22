import numpy as np
import pytest


def _ref_true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """Reference (non-vectorized) TR for testing.

    Uses common TR definition with first element as high-low.
    """
    n = len(close)
    tr = np.zeros(n, dtype=float)
    if n == 0:
        return tr
    tr[0] = float(high[0] - low[0])
    for i in range(1, n):
        hl = float(high[i] - low[i])
        hc = abs(float(high[i] - close[i - 1]))
        lc = abs(float(low[i] - close[i - 1]))
        tr[i] = max(hl, hc, lc)
    return tr


def _ref_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr = _ref_true_range(high, low, close)
    if len(tr) == 0:
        return tr
    if period <= 0:
        raise ValueError("period must be positive")
    # Simple moving average ATR
    kernel = np.ones(period, dtype=float) / period
    valid = np.convolve(tr, kernel, mode="valid")
    out = np.zeros_like(tr)
    out[period - 1 :] = valid
    return out


class TestATRVectorized:
    def test_true_range_vectorized_shape_and_nan_free(self):
        from app.engine.smc.atr import true_range

        high = np.array([11, 12, 13, 12.5, 14], dtype=float)
        low = np.array([10, 10.5, 11.5, 12.0, 13.6], dtype=float)
        close = np.array([10.5, 11.2, 12.2, 12.2, 13.8], dtype=float)

        tr = true_range(high, low, close)
        assert tr.shape == close.shape
        assert np.all(np.isfinite(tr))

        ref = _ref_true_range(high, low, close)
        np.testing.assert_allclose(tr, ref, rtol=1e-9, atol=1e-12)

    def test_atr_vectorized_matches_reference(self):
        from app.engine.smc.atr import atr

        period = 3
        # small synthetic series
        high = np.array([11, 12, 13, 12.5, 14, 14.2, 14.1], dtype=float)
        low = np.array([10, 10.5, 11.5, 12.0, 13.6, 13.7, 13.9], dtype=float)
        close = np.array([10.5, 11.2, 12.2, 12.2, 13.8, 14.0, 14.0], dtype=float)

        got = atr(high, low, close, period=period)
        ref = _ref_atr(high, low, close, period=period)

        np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-12)
