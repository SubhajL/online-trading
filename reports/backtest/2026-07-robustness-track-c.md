# Trend Signals v3 — Robustness Studies (Track C) & Final GO Synthesis

**Date:** 2026-07-09 · **Code:** this branch (trail_atr_mult implementation)
**Prior:** `2026-07-sizing-arm-results.md` (Track A — return condition satisfied) · `2026-07-statistical-hardening.md` (Track B — 5/6 checklist)
**Drivers:** `scripts/dev/run_trailing.py`, `run_regime_study.py`

## 1. ATR trailing stop (`trail_atr_mult`) — implemented, tested, **not adopted**

The previously dead `trail_price`/`trail_offset` fields are now live: for
trend sources, each bar the resting STOP_MARKET ratchets to
close −/+ `trail_atr_mult`×ATR (ATR recovered from the engine's per-bar
target), tightening only, never loosening. TDD: ratchet-up, never-lower,
short mirror, disabled-default, smc-retest validation. Ex-ante ladder
{1.5, 2, 3}×ATR at the decision arm (100% notional, taker), vs the no-trail
baseline:

| Run              | Ret%    | DD%      | Sharpe | N   | Baseline (no trail)         |
| ---------------- | ------- | -------- | ------ | --- | --------------------------- |
| tsmom28 BTC 1.5x | +2490.0 | 55.3     | 1.22   | 211 | +2858.1 / 51.6 / 1.24 / 114 |
| tsmom28 BTC 2x   | +2177.6 | **47.5** | 1.17   | 168 | ”                           |
| tsmom28 BTC 3x   | +1821.9 | 55.9     | 1.10   | 134 | ”                           |
| tsmom28 ETH 1.5x | +757.7  | 61.5     | 0.78   | 222 | +1505.8 / 59.1 / 0.92 / 120 |
| tsmom28 ETH 2x   | +867.7  | 65.4     | 0.81   | 180 | ”                           |
| tsmom28 ETH 3x   | +769.2  | 56.6     | 0.78   | 149 | ”                           |
| sma65 BTC 1.5x   | +1580.0 | 51.1     | 1.09   | 167 | +2469.7 / 58.6 / 1.21 / 63  |
| sma65 BTC 2x     | +1792.8 | **50.9** | 1.12   | 124 | ”                           |
| sma65 BTC 3x     | +1238.2 | 58.0     | 1.00   | 90  | ”                           |
| sma65 ETH 1.5x   | +1278.7 | 52.5     | 0.90   | 172 | +2867.6 / 55.3 / 1.08 / 60  |
| sma65 ETH 2x     | +1650.6 | 60.9     | 0.96   | 127 | ”                           |
| sma65 ETH 3x     | +1128.2 | 53.3     | 0.87   | 90  | ”                           |

**Verdict: negative result, documented.** DD improves meaningfully in 2 of
12 cells (both BTC, 2×) at a consistent cost of 0.07–0.12 Sharpe and
25–70% of total return; every ETH cell is worse. Mechanically the ratchet
converts trend rides into stop-out → next-bar re-entry churn (N doubles to
triples, e.g. sma65 63→124 trades), exactly the fee-cadence the co-primaries
were chosen to avoid. Gate 2 no longer needs the help (Track A passed it at
0.67–0.77× B&H). **Recommendation: keep `trail_atr_mult: 0` for the
co-primaries; the knob stays available.**

## 2. Regime-filter study (ADX) — open question tested, **not adopted**

Vectorized study (`run_regime_study.py`): Wilder ADX(14) gate on the
co-primaries, thresholds {15, 20, 25, 30}, next-bar execution, 13bps/side —
gated and ungated arms share the approximation, so deltas are
apples-to-apples (ungated levels track the event engine: tsmom28 BTC 1.30 /
53.0 / +3439% vs the engine's 1.24 / 51.6 / +2858%). Ex-ante adoption bar:
gated Sharpe ≥ ungated + 0.1 on BOTH symbols at one threshold, DD no worse.

Key rows (full table in the run log):

| Family / symbol | Ungated     | Best gate           | ADX≥25         | Verdict vs bar    |
| --------------- | ----------- | ------------------- | -------------- | ----------------- |
| tsmom28 BTC     | 1.30 / 53.0 | ADX≥25: 1.31 / 33.1 | +0.01 Sharpe   | fails +0.1 bar    |
| tsmom28 ETH     | 0.92 / 66.2 | ADX≥15: 0.89 / 61.5 | 0.63 / 60.3    | all gates degrade |
| sma65 BTC       | 1.21 / 59.6 | ADX≥25: 1.35 / 28.6 | +0.14 Sharpe ✓ | BTC-only          |
| sma65 ETH       | 1.05 / 57.5 | ADX≥15: 1.01 / 56.1 | 0.79 / 60.0    | all gates degrade |

**Verdict: fails the pre-registered bar at every threshold** — no gate helps
both symbols. The BTC ADX≥25 cell is genuinely striking (sma65 DD 59.6→28.6
with higher Sharpe) but it is symbol-inconsistent, threshold-fragile
(15/20/30 all hurt BTC — a single sweet spot is the classic overfit shape),
and the falsification arm (hold only when ADX<25) shows ADX separates
regimes on BTC (Sharpe 0.15–0.33) but not on ETH (0.66–0.68 ≈ the gated
arms). Consistent with the research pass in which zero regime claims
survived verification. **Not adopted; single-symbol regime gating flagged as
future research only.**

- **HMM regimes:** deferred — no `hmmlearn` in the environment and a
  defensible HMM study needs its own pre-registered design (states,
  features, refit cadence). Open question, unprejudged.
- **Funding-carry / on-chain overlays:** deferred research, unchanged
  status.

## 3. Final unconditional-GO checklist (Tracks A + B + C)

| Item                                      | Status           | Evidence                                                  |
| ----------------------------------------- | ---------------- | --------------------------------------------------------- |
| Sizing-mode knob + caps                   | ✅               | PR #204                                                   |
| Full-notional & vol-target pass gates 2+3 | ✅               | sizing-arm report: both co-primaries, both symbols, taker |
| Fee stress holds (maker + taker)          | ✅               | Sharpe haircut 0.03–0.04                                  |
| Breadth ≥ 6 symbols                       | ✅               | 6/8 both co-primaries (fails: LTC, XRP)                   |
| Bootstrap CI excludes zero                | ❌               | EW-8 tsmom28 [−0.01, +0.73] — misses by 0.01              |
| WFO stable                                | ✅               | fixed ≥ adaptive OOS, 4/4 arms                            |
| (C) Trailing stop                         | tested, rejected | negative result documented above                          |
| (C) Regime filter                         | tested, rejected | fails both-symbol bar; BTC-only effect noted              |

**Final label: GO — qualified by statistical power, not by any failed
mechanism.** Every gate the signal or the engine controls passes; both
phase-2 robustness levers were tested and honestly rejected (the base rules
stand as specified); the one open item is that 7.5y × 8 correlated assets
cannot statistically separate the Sharpe gap from zero at 95% two-sided —
and no amount of backtesting fixes that. Per the v3 plan, phase 3 (paper
trading tsmom28 + sma65, daily, long/cash on BTC + ETH) is the correct next
step: it is the only source of genuinely new evidence.
