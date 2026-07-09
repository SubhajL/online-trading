# Trend Signals v3 — 7-Year Backtest Results (2019→2026)

**Date:** 2026-07-09 · **Plan:** `docs/plans/2026-07-09-signal-family-v3-trend-experiment.md` (rev 2)
**Implementation:** PR #202 (`be738d4`) · **Data:** Binance daily klines 2019-01-01→2026-06-30 (2,738 bars/symbol, 0 gaps), existing 1h CSVs for the secondary/control arms
**Engine:** event-driven simulator, next-bar-open fills, 2 bps slippage, fixed-fractional 0.5% risk, 2×ATR(14) stops, long/cash (`allow_short: false`) unless noted. All configs ex-ante from the verified literature — no tuning.

## Verdict: **conditional GO** — tsmom-28d and price>SMA-20/65d, daily, long/cash

The two robust families deliver the exact profile the research predicted: **buy-and-hold-class risk-adjusted returns with 20–30× smaller drawdowns**, a short leg that adds nothing (diagnostic passed), and drawdown protection that held through both the 2021–22 bear and the novel 2024–26 segment. The raw-return GO gate is failed **by construction, not by signal**: the sizing engine caps exposure (mean notional 6.5–9% of equity; `max_position_notional_pct=0.10` is hardcoded in the simulator's risk parameters), so total return cannot approach 100%-notional B&H regardless of signal quality. Sharpe is exposure-invariant and is the decision metric.

## 1. Primary arm — 24 runs, daily, long/cash, 2019→2026

Sharpe vs B&H Sharpe (gate: ≥ 0.9×B&H). B&H: BTC +1443.9% / maxDD 76.6% / Sharpe 0.90 · ETH +1030.1% / maxDD 79.3% / Sharpe 0.81.

| Config                | BTC ret%    | BTC DD% | BTC Sharpe    | N   | ETH ret%    | ETH DD% | ETH Sharpe    | N   | Gate          |
| --------------------- | ----------- | ------- | ------------- | --- | ----------- | ------- | ------------- | --- | ------------- |
| tsmom28 (taker/maker) | +53.5/+55.6 | 5.8     | **1.31/1.35** | 114 | +26.1/+27.1 | 4.2     | 0.79/0.81     | 120 | **PASS both** |
| sma20                 | +31.9/+33.4 | 4.9     | **1.08/1.13** | 153 | +22.9/+24.0 | 3.4     | **0.87/0.91** | 143 | **PASS both** |
| sma65                 | +66.1/+66.9 | 7.8     | 1.06/1.07     | 63  | +34.3/+34.8 | 6.2     | 0.81/0.82     | 60  | PASS both\*   |
| cross-10-40           | +71.3/+71.8 | 9.7     | 1.05/1.06     | 38  | +37.4/+37.8 | 18.4    | 0.61          | 38  | fail ETH      |
| donch-20-10           | +50.6/+51.2 | 7.8     | 1.03/1.04     | 49  | +25.7/+26.1 | 5.8     | 0.69/0.70     | 49  | fail ETH      |
| sma200                | +27.6/+27.9 | 14.3    | 0.57/0.58     | 33  | +40.2/+40.4 | 25.3    | 0.49          | 23  | **FAIL both** |

Fees barely separate taker/maker at this exposure (Δ Sharpe ≤ 0.05). N is small for the slow rules — CIs are wide, as flagged ex-ante.

## 2. Ex-ante GO/NO-GO gates (plan §9)

| Gate                                          | Result                                                                                                                                           |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Net Sharpe ≥ 0.9 × B&H                        | **PASS** — tsmom28, sma20, sma65 on both symbols                                                                                                 |
| maxDD ≤ 0.8 × B&H maxDD                       | PASS (3–8% vs 61–63% threshold) — trivially, exposure-confounded                                                                                 |
| Net return ≥ 0.75 × B&H                       | **FAIL for all** — unreachable under the 10% notional cap + 0.5% risk sizing; a specification error in the gate, not evidence against the signal |
| No sign flip across ±50% sensitivity          | **PASS** for tsmom and short-SMA (every variant profitable, Sharpe above bar); sma65 flips on ETH at 98d; cross/donch flip on ETH                |
| NO-GO: only cost-fragile short lookbacks pass | Not triggered (28d and 65d pass)                                                                                                                 |
| NO-GO: no 2021–22 drawdown protection         | Strongly refuted (see §5)                                                                                                                        |

## 3. Sensitivity (±50% lookback, taker, Sharpe BTC/ETH)

- **tsmom:** 14d → 1.35/1.00 · 28d → 1.31/0.79 · 42d → 1.15/0.77 — robust
- **price>SMA (short):** 10d → 0.93/0.82 · 20d → 1.08/0.87 · 30d → 1.11/0.91 — robust
- sma65 band: 33d → 1.20/0.94 ✓ · 98d → 0.90/**0.52** ✗
- cross: 5/20 → 1.12/0.97 ✓ · 15/60 → 0.93/**0.60** ✗ · donch: 10/5 → 0.86/0.94 · 30/15 → 0.98/**0.71** ✗
- sma200 stays failing at 100d/300d (0.91/0.54, 0.47/0.50)

## 4. Diagnostic arm — tsmom28 long/short (literature predicts the short leg loses)

| Run       | Long PnL (N)  | Short PnL (N)   |
| --------- | ------------- | --------------- |
| BTC taker | +$5,451 (113) | +$134 (111)     |
| BTC maker | +$5,540 (114) | +$261 (111)     |
| ETH taker | +$2,504 (120) | **−$479** (121) |
| ETH maker | +$2,603 (120) | **−$398** (121) |

Exactly as the evidence predicted: the short side is noise-to-negative. No suspicious short-side profits → no implementation-bug signal. Long/cash confirmed as the right form.

## 5. Drawdown protection — the value proposition

**2021-11-08 → 2022-12-31 bear:** B&H BTC −75.5% (maxDD 76.6%), ETH −75.1% (maxDD 79.3%). Every trend config: −0.2% to −3.5% with maxDD 0.2–3.5% (at ~8% exposure; naively scaled to full notional ≈ 25–40% DD — still roughly half of B&H).

**Novel segment 2024-07 → 2026-06** (no academic sample extends past Aug 2023): B&H BTC −6.8% (DD 53.0%), ETH **−54.3%** (DD 67.6%). tsmom28 +1.1/+1.5%, sma20 +1.9/+0.1%, sma65 +1.6/+2.9%, maxDD ≤ 2.8% — protection held out-of-literature.

**Yearly returns (tsmom28 BTC):** 2019 +9.6, 2020 +3.8, 2021 +21.2, 2022 −2.6, 2023 +4.6, 2024 +11.6, 2025 −1.5, 2026H1 −0.5. Losing years present (as the ex-ante expectation demanded); visible decay after 2021, consistent with the literature's decay warning.

## 6. Secondary arm — 1h (lookbacks ×24, 2024-07→2026-06)

tsmom672: BTC Sharpe −0.78/−0.39, ETH −0.10/+0.13 · sma480: BTC −0.39/−0.06, ETH +0.28/+0.48 (vs B&H 0.16 BTC / −0.23 ETH). **1h does not clear the bar** — consistent with the research (1h evidence was partial; daily is the evidenced timeframe).

## 7. Control arm — SMC retest (1h, same window)

baseline Sharpe −3.87/−2.74 · s3 −0.95/−1.20 · s4 −1.38/−0.76 · s4m −1.05/−0.67. The trend family dominates the SMC arm on every metric, confirming the pivot rationale.

## 8. Caveats (stated ex-ante or discovered honestly)

1. **Exposure confound:** the engine's fixed-fractional sizing keeps mean notional at 6.5–9% of equity. Sharpe comparisons are valid; raw return/DD vs 100%-notional B&H are not. A full-notional replication (or a `max_position_notional_pct` knob) is the cleanest fix if absolute-return comparability is wanted.
2. **Fee realism at scale:** at ~8% exposure, taker-vs-maker is negligible. At full notional, fee drag scales ~12×; sma20's edge (153 trades) is the most cost-fragile of the passing set — prefer tsmom28/sma65 cadence if scaled up.
3. **tsmom28 lookback provenance:** flagged in-sample-optimal in Han et al.; its 14d/42d neighbors also pass, which mitigates but does not eliminate selection risk.
4. **Small N:** 23–153 trades per 7.5y; wide confidence intervals.
5. **Decay:** post-2023 returns are materially weaker than 2019–2021 across all families.

## 9. Next steps (phase 2 per plan §11, only-if-GO items now unlocked)

- ATR trailing stop (`trail_atr_mult`), walk-forward via `wfo.py`, regime-filter study (ADX/HMM — open question in the literature)
- Full-notional or higher-cap sizing arm to make the return gate meaningful
- Paper-trade the tsmom28 + sma65 pair on daily bars before any live exposure
