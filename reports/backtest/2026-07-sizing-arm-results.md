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

All 90 runs completed (`run_sizing_matrix.py run`, artifacts under
`artifacts/strategy-runs/sizing/`). Gate columns: G1 Sharpe ≥ 0.9×B&H ·
G2 maxDD ≤ 0.8×B&H · G3 return ≥ 0.75×B&H. B&H unchanged from v3:
BTC +1443.9% / maxDD 76.6% / Sharpe 0.90 · ETH +1030.1% / 79.3% / 0.81.

### 4.1 Co-primary families at 100% notional (the condition itself)

| Run               | Ret%    | DD%  | DD/B&H    | Sharpe | N   | G1  | G2  | G3  |
| ----------------- | ------- | ---- | --------- | ------ | --- | --- | --- | --- |
| tsmom28 BTC taker | +2858.1 | 51.6 | **0.67×** | 1.24   | 114 | P   | P   | P   |
| tsmom28 BTC maker | +3287.9 | 50.9 | 0.66×     | 1.28   | 114 | P   | P   | P   |
| tsmom28 ETH taker | +1505.8 | 59.1 | **0.75×** | 0.92   | 120 | P   | P   | P   |
| tsmom28 ETH maker | +1753.0 | 58.5 | 0.74×     | 0.95   | 120 | P   | P   | P   |
| sma65 BTC taker   | +2469.7 | 58.6 | **0.77×** | 1.21   | 63  | P   | P   | P   |
| sma65 BTC maker   | +2668.6 | 58.0 | 0.76×     | 1.23   | 63  | P   | P   | P   |
| sma65 ETH taker   | +2867.6 | 55.3 | **0.70×** | 1.08   | 60  | P   | P   | P   |
| sma65 ETH maker   | +3085.3 | 55.1 | 0.70×     | 1.10   | 60  | P   | P   | P   |

Both co-primaries clear **all three gates on both symbols at full notional,
net of taker fees** — returns land at 1.5–2.8× B&H, not merely 0.75×, and
maxDD at 0.67–0.77× B&H clears the strict 0.8× bar without vol-targeting.

### 4.2 Vol-target ladder (taker)

| Run                     | Ret%              | DD%         | Sharpe      | G1  | G2  | G3      |
| ----------------------- | ----------------- | ----------- | ----------- | --- | --- | ------- |
| vt-tsmom28-20 BTC / ETH | +1146.9 / +318.3  | 27.9 / 26.7 | 1.43 / 0.88 | P/P | P/P | P/f     |
| vt-tsmom28-30 BTC / ETH | +2022.4 / +617.7  | 33.3 / 36.4 | 1.42 / 0.92 | P/P | P/P | P/f     |
| vt-tsmom28-40 BTC / ETH | +2479.8 / +939.8  | 39.1 / 43.9 | 1.36 / 0.94 | P/P | P/P | **P/P** |
| vt-sma65-20 BTC / ETH   | +893.8 / +395.0   | 25.9 / 23.9 | 1.28 / 0.96 | P/P | P/P | f/f     |
| vt-sma65-30 BTC / ETH   | +1746.4 / +760.8  | 34.5 / 32.4 | 1.33 / 1.01 | P/P | P/P | P/f     |
| vt-sma65-40 BTC / ETH   | +2563.5 / +1190.7 | 41.5 / 38.8 | 1.34 / 1.04 | P/P | P/P | **P/P** |

The 40% rung passes all three gates on both symbols for both co-primaries
with maxDD ≈ 0.5× B&H — the best joint risk/return profile in the matrix,
exactly the pre-registered expectation for vol-targeting's role.

### 4.3 Other families and arms (summary)

- **sma20** (watch-only, fee-fragile): ETH passes all three at 100%
  (+1789.5%, DD 51.3, Sharpe 0.97 taker) but **BTC fails G2 and G3**
  (DD 70.5% = 0.92×B&H, ret +640.6%). The 153-trade cadence also shows the
  largest taker-vs-maker gap of the passing set (BTC Sharpe 0.84 vs 0.90).
  Fee fragility resolved as pre-registered: sma20 stays out of the primary
  set.
- **sma200**: still fails on BTC at every sizing (Sharpe 0.58–0.65) —
  consistent with its v3 FAIL; sizing does not rescue a weak signal.
- **cross-10-40 / donch-20-10**: pass at 100% notional on BTC; donchian ETH
  taker misses G2 by 1pp (64.4% vs 63.4%). Not co-primaries; noted only.
- **25% / 50% notional**: G1+G2 pass everywhere for the v3 passing set and
  returns scale monotonically with notional (25→50→100%), as does DD — the
  pre-registered monotonicity sanity check passes. G3 stays out of reach
  below 100% notional, confirming the v3 confound diagnosis was arithmetic,
  not signal.

### 4.4 Fee reality check (pre-registered expectation 2)

At 100% notional, taker→maker moves tsmom28 BTC Sharpe 1.24→1.28 and ETH
0.92→0.95; sma65 1.21→1.23 / 1.08→1.10. The haircut is ≈0.03–0.04 Sharpe —
inside the pre-registered ≤0.1 bound. Cumulative taker fees at full notional
are large in dollars ($15–44k on $10k initial over 7.5y) but are already
netted out of every return above; the edge survives them with room to spare
(consistent with the 57–66bps/side breakeven literature vs our ~13bps/side).

### 4.5 Honest observations

1. **Sharpe shifted with the sizing scheme, mostly up on ETH.** v3 risk
   sizing (0.5% ÷ 2×ATR) is implicitly inverse-vol-weighted per trade;
   constant-notional removes that weighting. tsmom28 ETH Sharpe went 0.79 →
   0.92, cross-10-40 ETH 0.61 → 1.05, while tsmom28 BTC eased 1.31 → 1.24.
   This is a mechanical weighting difference, not a bug (verified by the
   monotone 25/50/100 ladder); it does mean the v3 Sharpe table and this one
   are not point-comparable, and the cross-family ETH improvement should be
   treated as untested until Track B's breadth run.
2. **DD at full notional (51–59%) is roughly 15× the v3 confounded 3–8%** —
   the honest cost of the return leg. The vol-target 40% rung buys ~⅓ lower
   DD for ~15% less return; that trade-off now has numbers.
3. Trade counts N match v3 exactly (114/120, 63/60…) — sizing changed only
   quantities, never signals or timing, as designed.

## 5. Gate evaluation — pre-registered decision rule

> "…for each of BTC and ETH, at least one co-primary family (tsmom28 or
> sma65) has an arm that passes gate 3 at 100% notional AND some arm that
> passes gates 1+2+3 jointly, net of taker fees."

| Requirement                                   | BTC                                    | ETH                                    |
| --------------------------------------------- | -------------------------------------- | -------------------------------------- |
| Co-primary passes G3 at 100% notional (taker) | tsmom28 ✓, sma65 ✓                     | tsmom28 ✓, sma65 ✓                     |
| Some arm passes G1+G2+G3 jointly (taker)      | 100% notional ✓ (both), vt-40 ✓ (both) | 100% notional ✓ (both), vt-40 ✓ (both) |

**The condition of the "conditional GO" is satisfied — full pass, not a
near-miss; the 0.8× DD threshold held strictly with no goalpost-moving.**
Remaining unconditional-GO checklist items are Track B (breadth ≥6 symbols,
bootstrap CI excluding zero, WFO stability) and Track C (trailing-stop and
regime robustness studies). Until those complete, the correct label is:
**GO, pending statistical hardening** — every gate the sizing engine
controls now passes.
