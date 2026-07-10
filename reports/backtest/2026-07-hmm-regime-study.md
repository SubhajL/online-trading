# Trend Signals v3 — HMM Regime-Filter Study (deferred Track-C item)

**Date:** 2026-07-10 · **Code:** this branch (`feature/hmm-regime-study`)
**Closes:** the HMM leg deferred in `2026-07-robustness-track-c.md` §2 (no `hmmlearn` in the env at the time; needed its own pre-registration)
**Driver:** `scripts/dev/run_hmm_regime_study.py` · **Tested logic:** `app/engine/backtest/regime.py`
**Dependency:** `hmmlearn>=0.3.3` (added as the optional `research` extra; not a live-engine dependency)

> **Pre-registration note.** Sections 1–3 (design, arms, adoption bar) are
> committed BEFORE any HMM run of this study is executed. Section 4 (results)
> and Section 5 (verdict) are empty in the pre-registration commit and filled
> by a follow-up commit. Commit ordering is the audit trail — same discipline
> as the sizing arm and the ADX study.

## 1. Design (pre-registered)

Question: does a Gaussian-HMM market-regime gate improve the daily trend
co-primaries (tsmom28, sma65) over holding them ungated? This is the open
question the research pass flagged — the only regime evidence that ever beat
cost in the literature used GMM/HMM classification — tested, **not** assumed
to help.

- **Model:** `GaussianHMM(covariance_type="diag")`, `n_components ∈ {2, 3}`
  (bull/bear; bull/chop/bear). Fitted per symbol. Seeded
  (`random_state=42`, `n_iter=100`) for reproducibility.
- **Features (per bar):** `[log_return, trailing realized vol]`, realized vol
  = trailing std of log returns over 20 bars. Standard drift+vol regime
  features. First 20 bars are warmup (undefined vol) and excluded from fit
  and gating.
- **Trend-on labeling:** a state is "trend-on" iff its fitted mean log-return
  (`means_[:, 0]`) is ≥ 0. The long/cash co-primaries should hold only in
  positive-drift regimes. Labeling uses the FITTED model's means only — never
  future data.
- **Gate:** hold the co-primary's position only on bars whose current regime
  is trend-on; else flat. Applied to the same next-bar-execution vectorized
  arm as the ADX study (signal at close t → position over bar t+1, 13 bps per
  side), so HMM-vs-ungated deltas are apples-to-apples with the ADX table.

## 2. Arms (pre-registered)

- **A — Causal walk-forward (THE adoption test).** Min train 365 bars; refit
  the HMM every 63 bars (~quarter) on data up to the refit point; between
  refits the regime at bar t is the last state of `predict(X[:t+1])` under
  the most recent fitted model (Viterbi on past-only data → causal). Trend-on
  labels come from that same past-only fit. No future information enters the
  gate at any bar. This is the only arm the verdict is judged on.
- **B — In-sample (DIAGNOSTIC upper bound, lookahead — not tradeable).** Fit
  once on the full sample, label, gate. Reported only to bound how much
  regime information exists at all; a large A-vs-B gap means the regime signal
  is not usable causally. Explicitly excluded from the adoption decision.
- **Falsification:** for each arm, also run the INVERTED gate (hold only in
  trend-off regimes). A working regime signal must make the inverted arm
  clearly worse; if inverted ≈ gated, the "regime" is noise.

## 3. Adoption bar (pre-registered — identical to the ADX study)

**Adopt only if:** the causal HMM-gated net Sharpe ≥ ungated + 0.10 on BOTH
BTC and ETH, for at least one `n_components` setting, with maxDD no worse
than ungated, AND the inverted-gate falsification arm is clearly worse.
Anything less is NO-GO (documented, not adopted). No post-hoc threshold or
criterion changes.

## 4. Results

_To be filled by the run commit. No results existed when sections 1–3 were
committed._

## 5. Verdict

_To be filled by the run commit._
