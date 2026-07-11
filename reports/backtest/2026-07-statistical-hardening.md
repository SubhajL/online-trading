# Trend Signals v3 — Statistical Hardening (Track B)

**Date:** 2026-07-09 · **Code:** PR #204 (sizing modes) + this branch (bootstrap module, WFO trend params)
**Prior:** `2026-07-trend-signals-v3-results.md` (conditional GO) → `2026-07-sizing-arm-results.md` (return condition satisfied)
**Drivers:** `scripts/dev/run_breadth.py`, `run_bootstrap_ci.py`, `run_wfo_trend.py` · artifacts under `artifacts/strategy-runs/breadth/`, `artifacts/wfo/trend/`

Three pre-registered hardening arms, all at the Track-A decision arm (100%
notional, taker fees, long/cash, ex-ante parameters, no per-symbol tuning).

## 1. Breadth — 8 symbols (BTC, ETH + BNB, XRP, LTC, ADA, SOL, DOGE)

Daily klines to 2026-06-30 (BNB/XRP/LTC/ADA from 2019-01-01, DOGE from
2019-07, SOL from 2020-08). Gate 1 = Sharpe ≥ 0.9×B&H, the cross-asset claim
under test.

| Family        | G1 passes | Failures                                   | Notes                                                          |
| ------------- | --------- | ------------------------------------------ | -------------------------------------------------------------- |
| tsmom28       | **6/8**   | LTC (0.25 vs 0.49 B&H), XRP (0.48 vs 0.62) | G3 return also passes 6/8; SOL Sharpe 1.51, BNB 1.24           |
| sma65         | **6/8**   | LTC (0.39), XRP (0.20)                     | G3 passes 6/8                                                  |
| sma20 (watch) | 8/8       | —                                          | several passes merely match weak benchmarks (LTC 0.49 vs 0.49) |

Full 24-run table:

| Config  | Symbol | Ret%     | DD%  | Sharpe | N   | B&H Ret% | B&H DD% | B&H Shp | G1  |
| ------- | ------ | -------- | ---- | ------ | --- | -------- | ------- | ------- | --- |
| tsmom28 | BTC    | +2858.1  | 51.6 | 1.24   | 114 | +1443.9  | 76.6    | 0.90    | P   |
| tsmom28 | ETH    | +1505.8  | 59.1 | 0.92   | 120 | +1030.1  | 79.3    | 0.81    | P   |
| tsmom28 | BNB    | +9844.0  | 61.5 | 1.24   | 122 | +9022.4  | 76.1    | 1.13    | P   |
| tsmom28 | XRP    | +103.7   | 81.0 | 0.48   | 117 | +188.3   | 83.2    | 0.62    | f   |
| tsmom28 | LTC    | −32.0    | 93.9 | 0.25   | 140 | +33.2    | 89.4    | 0.49    | f   |
| tsmom28 | ADA    | +1742.6  | 78.8 | 0.89   | 106 | +244.0   | 95.2    | 0.65    | P   |
| tsmom28 | SOL    | +20879.1 | 63.7 | 1.51   | 76  | +2133.4  | 96.3    | 1.03    | P   |
| tsmom28 | DOGE   | +19138.2 | 76.7 | 0.86   | 92  | +1762.5  | 92.3    | 0.74    | P   |
| sma65   | BTC    | +2469.7  | 58.6 | 1.21   | 63  | +1443.9  | 76.6    | 0.90    | P   |
| sma65   | ETH    | +2867.6  | 55.3 | 1.08   | 60  | +1030.1  | 79.3    | 0.81    | P   |
| sma65   | BNB    | +4443.0  | 64.2 | 1.09   | 66  | +9022.4  | 76.1    | 1.13    | P   |
| sma65   | XRP    | −58.7    | 93.7 | 0.20   | 96  | +188.3   | 83.2    | 0.62    | f   |
| sma65   | LTC    | +32.2    | 89.3 | 0.39   | 83  | +33.2    | 89.4    | 0.49    | f   |
| sma65   | ADA    | +1640.0  | 78.6 | 0.89   | 75  | +244.0   | 95.2    | 0.65    | P   |
| sma65   | SOL    | +5954.4  | 71.9 | 1.25   | 52  | +2133.4  | 96.3    | 1.03    | P   |
| sma65   | DOGE   | +5585.5  | 89.5 | 0.76   | 76  | +1762.5  | 92.3    | 0.74    | P   |
| sma20   | BTC    | +640.6   | 70.5 | 0.84   | 153 | +1443.9  | 76.6    | 0.90    | P   |
| sma20   | ETH    | +1789.5  | 51.3 | 0.97   | 141 | +1030.1  | 79.3    | 0.81    | P   |
| sma20   | BNB    | +6116.6  | 53.7 | 1.15   | 145 | +9022.4  | 76.1    | 1.13    | P   |
| sma20   | XRP    | +296.4   | 83.5 | 0.60   | 158 | +188.3   | 83.2    | 0.62    | P   |
| sma20   | LTC    | +140.1   | 85.5 | 0.49   | 160 | +33.2    | 89.4    | 0.49    | P   |
| sma20   | ADA    | +1899.3  | 84.3 | 0.92   | 147 | +244.0   | 95.2    | 0.65    | P   |
| sma20   | SOL    | +3614.9  | 80.1 | 1.16   | 115 | +2133.4  | 96.3    | 1.03    | P   |
| sma20   | DOGE   | +5889.3  | 82.7 | 1.02   | 129 | +1762.5  | 92.3    | 0.74    | P   |

**Verdict: breadth ≥6 symbols — MET** (6/8 for both co-primaries). Honest
notes: (a) the two failures, LTC and XRP, are the two structurally weakest
majors (B&H +33% and +188% over 7.5y) — trend-following found little trend
to follow; (b) full-notional maxDD on the breadth alts is 61–94%, mostly
above the 0.8×B&H bar — a single-asset alt sleeve at 100% notional is not
deployable on the DD gate; the vol-target mode or a portfolio construction
is required there (BTC/ETH, the deployment targets, pass as shown in the
sizing-arm report).

## 2. Stationary-bootstrap 95% CI on the Sharpe gap

`app/engine/backtest/bootstrap.py` (Politis-Romano stationary bootstrap,
paired resampling of strategy and benchmark returns, mean block 20 daily
bars, 2,000 replicates, fixed seed 7; unit-tested incl. a
constructed-alpha case whose CI must exclude zero).

| Config  | Symbol             | Gap (point) | 95% CI             | CI > 0           |
| ------- | ------------------ | ----------- | ------------------ | ---------------- |
| tsmom28 | BTC                | +0.34       | [−0.15, +0.83]     | no               |
| tsmom28 | ETH                | +0.11       | [−0.40, +0.61]     | no               |
| tsmom28 | BNB                | +0.11       | [−0.36, +0.54]     | no               |
| tsmom28 | XRP                | −0.14       | [−0.66, +0.29]     | no               |
| tsmom28 | LTC                | −0.24       | [−0.71, +0.17]     | no               |
| tsmom28 | ADA                | +0.24       | [−0.25, +0.70]     | no               |
| tsmom28 | SOL                | +0.49       | [−0.09, +1.02]     | no               |
| tsmom28 | DOGE               | +0.12       | [−0.07, +0.55]     | no               |
| tsmom28 | **EW-8 portfolio** | **+0.37**   | **[−0.01, +0.73]** | **no — by 0.01** |
| sma65   | BTC                | +0.31       | [−0.18, +0.81]     | no               |
| sma65   | ETH                | +0.27       | [−0.25, +0.77]     | no               |
| sma65   | BNB                | −0.04       | [−0.51, +0.37]     | no               |
| sma65   | XRP                | −0.41       | [−0.97, +0.09]     | no               |
| sma65   | LTC                | −0.10       | [−0.58, +0.36]     | no               |
| sma65   | ADA                | +0.24       | [−0.28, +0.70]     | no               |
| sma65   | SOL                | +0.22       | [−0.40, +0.79]     | no               |
| sma65   | DOGE               | +0.02       | [−0.21, +0.36]     | no               |
| sma65   | **EW-8 portfolio** | +0.23       | [−0.20, +0.65]     | no               |

(EW-8 = equal-weight daily-rebalanced portfolio of the eight single-symbol
sleeves vs the same-weight buy-&-hold basket — the literature's actual
cross-asset construction, with the aggregation gain the per-symbol tests
lack.)

**Verdict: "bootstrap CI excludes zero" — NOT MET.** Per-symbol CIs are
±0.5 wide — exactly the ex-ante standard-error arithmetic (SE of an
annualized Sharpe ≈ 0.4–0.5 on 7.5y). The tsmom28 EW-8 aggregate misses by
0.01 Sharpe (lower bound −0.01): the gap is positive point-wise nearly
everywhere but 7.5 years × 8 correlated crypto assets cannot separate
Sharpe-parity-vs-B&H from Sharpe-superiority at 95% two-sided. We report
this as failed rather than switching to a one-sided or 90% criterion
post-hoc. Note the bar's severity: the strategy is in cash roughly half the
time yet is being tested against full-exposure B&H Sharpe; equality of
Sharpe with 20–30pp lower drawdown would already justify the strategy — but
that is not the pre-registered test, so it does not pass it.

## 3. Walk-forward over the lookback (wfo.py, trend params now mappable)

365d train / 182d test / 182d step, 13 windows per symbol-family,
2019→2026. In each window the lookback is chosen on train data only
(existing composite score, unmodified) and validated OOS; the same window is
also run with the fixed ex-ante lookback. Grids: tsmom {14,21,28,42,56},
sma {10,20,30,45,65,98}.

| Family / symbol | Chosen-lookback histogram        | Stability | Mean OOS ret: adaptive vs fixed | Positive windows |
| --------------- | -------------------------------- | --------- | ------------------------------- | ---------------- |
| tsmom BTC       | 14×2 · 28×4 · 42×3 · 56×4        | 0.72      | +19.9% vs **+24.9%**            | 7 vs 8 /13       |
| tsmom ETH       | 14×4 · 21×1 · 42×2 · 56×6        | 0.67      | +10.3% vs **+14.7%**            | 8 vs 8 /13       |
| sma BTC         | 20×1 · 30×2 · 45×6 · 65×2 · 98×2 | 0.69      | +12.3% vs **+18.6%**            | 6 vs 7 /13       |
| sma ETH         | 10×3 · 20×1 · 30×4 · 45×3 · 65×2 | 0.65      | +2.2% vs **+2.5%**              | 4 vs 7 /13       |

(Per-window tables in `artifacts/wfo/trend/*.json` and the run log.)

**Verdict: WFO stability — MET, in the meaningful sense.** The fixed
ex-ante lookback beats train-time optimization out-of-sample in all four
arms. If 28d/65d were lucky in-sample artifacts, adaptive selection should
have found consistently better neighbors; instead selection noise costs
2–6pp per window and chosen values scatter across the whole grid. The edge
is a property of the family, not of the number — the strongest available
answer to the tsmom28-provenance concern flagged in v3. (Windowed OOS
returns are handicapped by per-window warmup, uniformly across arms.)

## 4. Unconditional-GO checklist status (after Tracks A + B)

| Item                                             | Status                                                                           |
| ------------------------------------------------ | -------------------------------------------------------------------------------- |
| Sizing-mode knob + caps                          | ✅ PR #204                                                                       |
| Full-notional & vol-target reruns pass gates 2+3 | ✅ both co-primaries, both symbols, taker fees (`2026-07-sizing-arm-results.md`) |
| Fee stress holds (maker and taker)               | ✅ Sharpe haircut ≈ 0.03–0.04                                                    |
| Breadth ≥ 6 symbols                              | ✅ 6/8 both co-primaries                                                         |
| Bootstrap CI excludes zero                       | ❌ EW-8 tsmom28 misses by 0.01 (95% two-sided)                                   |
| WFO stable                                       | ✅ fixed ≥ adaptive OOS in 4/4 arms                                              |

**5 of 6 hold. Per the pre-registered rule, GO remains _qualified_, not
unconditional** — the single miss is statistical power, not a discovered
defect, and the deployment-relevant risk profile (B&H-class Sharpe, 0.67–0.77×
maxDD at full notional, ~0.5× at 40% vol-target) passed everything it was
asked. Recommended next step remains the v3 plan's phase 3: paper-trade
tsmom28 + sma65 on daily bars (fresh out-of-sample evidence is the only
thing that shrinks the CI), with Track C robustness work below.
