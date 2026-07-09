# Trend Signals v3 — Sizing Arm (Track A): Pre-Registration & Results

**Date:** 2026-07-09 · **Code:** PR #204 (`feature/backtest-sizing-modes`)
**Prior results:** `2026-07-trend-signals-v3-results.md` (conditional GO — return gate unreachable at ~8% exposure)
**Data:** identical to v3 — Binance daily klines 2019-01-01 → 2026-06-30 (2,738 bars/symbol), BTCUSDT + ETHUSDT
**Driver:** `scripts/dev/run_sizing_matrix.py` · **Configs:** `reports/backtest/strategies/sizing/*.yaml`

> **Pre-registration note.** Sections 1–3 below (matrix, gates, expectations)
> are committed BEFORE any run of this matrix is executed. The Results
> section is empty in the pre-registration commit and is filled by a
> follow-up commit. Commit ordering in this branch is the audit trail.

## 1. Pre-registered matrix (90 runs)

**Notional arm (72):** the six v3 daily families — tsmom28, sma20, sma65,
sma200, cross-10-40, donch-20-10 — with identical ex-ante parameters, at
`sizing_mode: notional`, `notional_pct` ∈ {0.25, 0.5, 1.0} × {taker 10bps,
maker 4bps} × {BTC, ETH}. Slippage 2bps, long/cash, 2×ATR(14) protective
stop retained (no longer the sizing input).

**Vol-target ladder (18):** the v3 passing set only — tsmom28, sma20, sma65 —
at `sizing_mode: vol_target`, `vol_target_annual_pct` ∈ {20, 30, 40}, taker
fees, both symbols. `vol_lookback_bars: 20` (≈1 month of realized daily vol;
practitioner range 20–60d) chosen ex-ante, single value, no tuning.

**Caps:** `max_position_notional_pct: 1.0`, `max_symbol_exposure_pct: 1.0`,
`max_total_exposure_leverage: 3`. The 1.0 notional cap doubles as the
no-leverage clamp for the vol-target arm: weight = min(target/realized, 1.0)
— long/cash spot semantics, no leverage.

## 2. Pre-registered gates (unchanged from the v3 plan — no goalpost-moving)

| #   | Gate                          | Applied to                                                                               |
| --- | ----------------------------- | ---------------------------------------------------------------------------------------- |
| 1   | Net Sharpe ≥ 0.9 × B&H Sharpe | every arm (Sharpe is leverage-invariant; must keep holding net of scaled fees)           |
| 2   | maxDD ≤ 0.8 × B&H maxDD       | **kept strict at 0.8×** — vol-targeting is the legitimate lever, not threshold softening |
| 3   | Net return ≥ 0.75 × B&H       | now meaningful at 100% notional; this is "the condition" of the conditional GO           |

**Decision rule (ex-ante):** the return condition of the conditional GO is
satisfied if, for each of BTC and ETH, at least one co-primary family
(tsmom28 or sma65) has an arm that passes gate 3 at 100% notional AND some
arm (100% notional or a vol-target rung) that passes gates 1+2+3 jointly,
net of taker fees. sma20 is watch-only (fee fragility). If gate 2 fails at
100% notional but passes on a vol-target rung that also passes gate 3, that
is a full pass via the vol-target mode. If full-notional DD lands at
0.8–0.85× B&H and no vol-target rung passes all three, the honest outcome is
a documented near-miss, not a GO.

## 3. Pre-registered expectations

1. **Return gate:** passable at 100% notional — the OOS literature template
   (walk-forward EMA cross, full notional) matched B&H returns.
2. **Fee drag at full notional:** taker round trip ≈ 26bps of equity
   (2×10bps fee + 2×3bps effective slippage). tsmom28 (~114 trades) ≈ ~30%
   cumulative ≈ ~3.9%/yr drag; sma65 (~63 trades) ≈ ~16% ≈ 2.2%/yr; maker
   roughly halves both. Expected Sharpe haircut ≈ 0.1 (drag ÷ ~40% vol) —
   survivable. sma20 (153 trades) is the fee-fragile one to watch.
3. **Gate 2 is the fight:** the best OOS template achieved 0.84× B&H maxDD,
   which would fail our 0.8×. Our rules were in-market only ~53% of days, so
   we may do better; the vol-target rungs are expected to be the likeliest
   joint gate-2+3 passers (30–40% target).
4. **Sharpe ≈ v3 values minus ≤0.15** across sizing arms (leverage
   invariance up to fee drag). A materially larger Sharpe drop would signal
   an implementation problem, not a market result.
5. **Monotonicity sanity check:** return and DD should scale roughly with
   notional_pct across 25→50→100%; a non-monotone pattern flags a sizing bug.

## 4. Results

_To be filled by the run commit. No results existed when sections 1–3 were
committed._

## 5. Gate evaluation

_To be filled by the run commit._
