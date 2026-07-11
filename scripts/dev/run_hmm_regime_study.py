#!/usr/bin/env python3
"""HMM regime-filter study — closes the Track-C deferred item.

Pre-registration: reports/backtest/2026-07-hmm-regime-study.md. Tests the
adoption bar there: a Gaussian-HMM regime gate on the daily co-primaries
(tsmom28, sma65), judged ONLY on the causal walk-forward arm; the in-sample
arm is a labeled lookahead upper bound; an inverted gate is the falsification
check.

Deterministic pieces (features, labeling, gating, metrics) live in and are
unit-tested via app/engine/backtest/regime.py; only the seeded hmmlearn fit
is here.

Usage (repo root, research extra installed): python scripts/dev/run_hmm_regime_study.py
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
import sys
import warnings

import numpy as np

# hmmlearn's ConvergenceMonitor logs a line whenever EM oscillates at the
# optimum (tiny negative deltas); silence it — the fits are effectively
# converged and the study is judged on realized metrics, not log-likelihood.
logging.getLogger("hmmlearn").setLevel(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA_DIR = ROOT / "data" / "backtest"

from app.engine.backtest.regime import (  # noqa: E402
    apply_regime_gate,
    label_trend_on_states,
    regime_features,
    sma_positions,
    strategy_net_metrics,
    tsmom_positions,
)

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
FAMILIES = {"tsmom28": (tsmom_positions, 28), "sma65": (sma_positions, 65)}
N_STATES = [2, 3]
VOL_WINDOW = 20
COST_PER_SIDE = 0.0013
BARS_PER_YEAR = 365.0
RANDOM_STATE = 42
N_ITER = 100
MIN_TRAIN = 365
REFIT_EVERY = 63


def _load_closes(symbol: str) -> np.ndarray:
    rows = list(csv.DictReader(open(DATA_DIR / f"{symbol.lower()}_1d.csv")))
    return np.array([float(r["close"]) for r in rows])


def _fit_hmm(features: np.ndarray, n_states: int):
    from hmmlearn.hmm import GaussianHMM

    model = GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=N_ITER,
        random_state=RANDOM_STATE,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(features)
    return model


def _in_sample_regime(features: np.ndarray, n_states: int) -> np.ndarray:
    """Lookahead upper bound: fit once on all features, label, mark trend-on."""
    model = _fit_hmm(features, n_states)
    states = model.predict(features)
    trend_on = label_trend_on_states(model.means_)
    return np.array([s in trend_on for s in states])


def _causal_regime(features: np.ndarray, n_states: int) -> np.ndarray:
    """Walk-forward: at each bar the regime uses only past+present features,
    under a model refit on trailing data every REFIT_EVERY bars."""
    n = len(features)
    in_regime = np.zeros(n, dtype=bool)
    model = None
    trend_on: set[int] = set()
    for t in range(n):
        if t < MIN_TRAIN:
            continue
        if model is None or (t - MIN_TRAIN) % REFIT_EVERY == 0:
            model = _fit_hmm(features[:t], n_states)
            trend_on = label_trend_on_states(model.means_)
        state_now = int(model.predict(features[: t + 1])[-1])
        in_regime[t] = state_now in trend_on
    return in_regime


def _metrics(closes: np.ndarray, positions: np.ndarray) -> tuple[float, float, float]:
    return strategy_net_metrics(closes, positions, COST_PER_SIDE, BARS_PER_YEAR)


def main() -> None:
    print("| Family | Symbol | Arm | Sharpe | maxDD% | Ret% |")
    print("|---|---|---|---|---|---|")
    for family, (signal_fn, lookback) in FAMILIES.items():
        for symbol in SYMBOLS:
            closes = _load_closes(symbol)
            base_pos = signal_fn(closes, lookback)

            # Features are aligned to close index i+1; the first bar has no
            # return, so map a length-(N-1) regime array back onto closes by
            # left-padding one flat bar and the warmup nans as not-in-regime.
            feats = regime_features(closes, VOL_WINDOW)
            valid = ~np.isnan(feats[:, 1])
            fit_feats = feats[valid]
            # index into closes for each valid feature row (row i -> close i+1)
            close_idx = (np.nonzero(valid)[0] + 1)

            sharpe0, dd0, ret0 = _metrics(closes, base_pos)
            print(
                f"| {family} | {symbol} | ungated | {sharpe0:.2f} | {dd0:.1f} | {ret0:+.1f} |",
            )

            for n_states in N_STATES:
                for arm_name, regime_fn in (
                    ("in-sample", _in_sample_regime),
                    ("causal", _causal_regime),
                ):
                    valid_regime = regime_fn(fit_feats, n_states)
                    for label, mask in (
                        (f"HMM-{n_states} {arm_name}", valid_regime),
                        (f"HMM-{n_states} {arm_name} inv", ~valid_regime),
                    ):
                        full = np.zeros(len(closes), dtype=bool)
                        full[close_idx] = mask
                        gated = apply_regime_gate(base_pos, full)
                        s, dd, ret = _metrics(closes, gated)
                        print(
                            f"| {family} | {symbol} | {label} "
                            f"| {s:.2f} | {dd:.1f} | {ret:+.1f} |",
                            flush=True,
                        )


if __name__ == "__main__":
    main()
