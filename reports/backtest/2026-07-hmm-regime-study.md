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

All 36 rows from `run_hmm_regime_study.py` (2 families × 2 symbols ×
{ungated, 2-state, 3-state} × {in-sample, causal} × {gated, inverted}). The
**causal** arm is the only one the verdict rests on.

### 4.1 Causal arm vs ungated — the adoption test

| Family  | Symbol | Ungated Sharpe | HMM-2 causal           | ΔSharpe   | HMM-3 causal           | ΔSharpe   |
| ------- | ------ | -------------- | ---------------------- | --------- | ---------------------- | --------- |
| tsmom28 | BTC    | 1.30           | 1.22 (dd 46.5, +1858%) | **−0.08** | 1.10 (dd 45.5, +1184%) | **−0.20** |
| tsmom28 | ETH    | 0.92           | 0.94 (dd 46.3, +1277%) | +0.02     | 1.00 (dd 45.0, +1252%) | +0.08     |
| sma65   | BTC    | 1.21           | 1.03 (dd 57.5, +1021%) | **−0.18** | 0.84 (dd 59.6, +515%)  | **−0.37** |
| sma65   | ETH    | 1.05           | 1.07 (dd 45.6, +1994%) | +0.02     | 1.14 (dd 51.0, +1910%) | +0.09     |

No `n_components` setting clears the pre-registered **+0.10 Sharpe on both
symbols**. The gate consistently _hurts_ BTC (the cleaner trender — the
causal regime lags the trend and cuts good bars) and helps ETH only
marginally (max +0.09, short of +0.10). Best joint outcome (3-state) is
BTC −0.20/−0.37 vs ETH +0.08/+0.09 — a wash-to-negative.

### 4.2 In-sample (lookahead) upper bound

Even _with_ full-sample lookahead the improvements are modest and not joint:
tsmom28 BTC HMM-3 1.37 (+0.07), sma65 ETH HMM-2 1.22 (+0.17), but the same
configs leave the other symbol flat or down. Notably the 2-state in-sample
model on **BTC labels both states trend-on** (both fitted mean-returns ≥ 0 —
BTC's drift is strong enough that a 2-state full-sample fit finds no
negative-drift regime), so its gate is a no-op (gated = ungated = 1.30/1.21)
and its inverted arm is empty (0/0/0). There is little extractable regime
information to begin with; the causal arm cannot realize even that little.

### 4.3 Falsification (inverted gate)

Inverted causal arms are clearly worse in 7 of 8 cells (Sharpe 0.22–0.67 vs
gated 0.84–1.22) — but **sma65 BTC 3-state inverts**: the "trend-off" gate
scores 0.93 > the "trend-on" 0.84. When holding the _off_ regime beats the
_on_ regime, the state labeling is capturing noise, not a real regime — an
outright falsification in that cell, reinforcing NO-GO rather than a
borderline miss.

## 5. Verdict — **NO-GO** (regime gate not adopted)

The causal HMM gate fails the pre-registered adoption bar for every
configuration: it never delivers +0.10 Sharpe on both symbols, it degrades
the stronger BTC arm in all four settings, the lookahead upper bound shows
only thin regime information, and one falsification cell inverts. This
matches the ADX result (`2026-07-robustness-track-c.md` §2) and the research
pass in which zero regime claims survived verification.

**Honest counter-observation (does not change the verdict):** the causal
gate _does_ cut drawdown in several cells — tsmom28 ETH 66.2→45–46%, BTC
53→45–47% — at a large return cost (tsmom28 BTC +3439%→+1184–1858%). A
drawdown-first operator could find that trade-off interesting, but the
pre-registered bar is Sharpe-first and both-symbols, and on that bar this is
a clean NO-GO. No threshold or criterion was moved to rescue it.

With this, the deferred HMM leg of Track C is **closed as tested-and-rejected**,
alongside ADX. Both regime levers were given a fair, pre-registered,
causal test; neither is adopted. The phase-2 robustness column now reads:
trailing stop tested/rejected, ADX tested/rejected, HMM tested/rejected —
the base tsmom28 + sma65 long/cash rules stand as specified. Funding-carry /
on-chain overlays remain deferred research (unchanged).
