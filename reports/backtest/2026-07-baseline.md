# Backtest Baseline Report — 2026-07-05

First real-data backtest of the strategy pipeline in this project's history. Prior to
PR #181 the backtester optimized a hardcoded mock; prior to PR #185 the runner could not
actually load downloaded data (naive/aware datetime mismatch silently yielded zero candles,
and the shell wrapper's import path never worked). Both are fixed; these are the first
honest numbers.

## Verdict: NO-GO for mainnet (confirmed by the corrected v2 re-run below)

The strategy, as configured with engine defaults, loses on 2 years of real data in every
run. The initial (v1) run also exposed simulator bookkeeping defects; those were fixed in
PR #191 and the v2 re-run below is the trustworthy measurement. The structural conclusion
survives the fixes: cost drag (fees + slippage) of roughly 0.5–1R per trade against tight
SMC stops makes the current configuration unprofitable at any hit rate it achieves.

## v2 re-run — corrected bookkeeping + live-parity caps (code SHA `1a4fb5f`, 2026-07-05)

Same data, same `baseline-config.yaml` (config hash unchanged **by design** — the
results-changing modifications live in code, not config: PR #191 fixed trade size/R/slippage
bookkeeping and set the simulator's risk caps to the live defaults — notional 10% of equity
(was 100%), symbol exposure 25%, max 5 open positions).

| Run         | Trades | Hit rate | Net PnL | PnL %   | PF    | Sharpe | Max DD | Fees  | Slippage | avg R | avg win R | avg loss R |
| ----------- | ------ | -------- | ------- | ------- | ----- | ------ | ------ | ----- | -------- | ----- | --------- | ---------- |
| BTCUSDT 15m | 3,484  | 25.9%    | −7,861  | −78.61% | 0.292 | −19.1  | 78.66% | 5,665 | 1,442    | −1.61 | +0.95     | −2.50      |
| BTCUSDT 1h  | 691    | 32.1%    | −2,635  | −26.35% | 0.583 | −3.9   | 27.07% | 2,012 | 509      | −0.58 | +1.22     | −1.43      |
| ETHUSDT 15m | 3,185  | 31.5%    | −7,501  | −75.01% | 0.411 | −12.4  | 75.03% | 5,280 | 1,332    | −0.85 | +1.15     | −1.77      |
| ETHUSDT 1h  | 765    | 34.0%    | −2,625  | −26.25% | 0.688 | −2.7   | 26.91% | 2,010 | 505      | −0.30 | +1.57     | −1.26      |

What the corrected numbers say:

- **R metrics are now sane and damning**: average loss runs −1.3R to −2.5R instead of the
  theoretical −1R — the excess is cost drag, now honestly measured (slippage alone ~0.2R/trade
  on 15m; fees larger). Average win sits near +1R–1.6R against a 1.5R first target.
- **The notional cap matters enormously**: capping positions at 10% of equity (live parity)
  cut the 1h drawdowns from ~82%/73% to ~27%. v1's 100%-notional sizing amplified the burn.
- **Timeframe gradient is consistent**: 1h is much less bad than 15m (fewer trades, less
  fee churn). Still negative everywhere.
- v2 raw outputs: `*_v2.report.json` beside this file; artifacts in `artifacts/backtest-v2/`.

The original v1 run and its defect analysis are preserved below for the record.

## Provenance

|             |                                                                                                                                     |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Data        | Binance mainnet spot klines via `python -m app.engine.backtest.download` (keyless REST), fetched 2026-07-05                         |
| Range       | 2024-07-01 → 2026-06-30 (2 years; 70,080 bars @15m, 17,520 @1h per symbol)                                                          |
| Code        | git SHA `1c2d6a2` (post PR #185)                                                                                                    |
| Config      | `reports/backtest/baseline-config.yaml` (engine defaults, explicit), hash `ef4c3b988d99a00b`                                        |
| Balance     | 10,000 USDT, spot, 0.5% fixed-fractional risk per trade                                                                             |
| Raw outputs | `artifacts/backtest/*_20240701_20260630/` (report.json copies committed beside this file; trades.csv and candle CSVs not committed) |

## Headline results (as run)

| Run         | Trades | Hit rate | Net PnL | PnL %   | Profit factor | Sharpe (tf-aware) | Max DD | Fees paid |
| ----------- | ------ | -------- | ------- | ------- | ------------- | ----------------- | ------ | --------- |
| BTCUSDT 15m | 3,136  | 28.1%    | −9,997  | −99.97% | 0.357         | −19.4             | 99.97% | 7,858     |
| BTCUSDT 1h  | 689    | 32.1%    | −8,168  | −81.68% | 0.486         | −5.3              | 81.99% | 5,780     |
| ETHUSDT 15m | 2,915  | 31.5%    | −9,995  | −99.95% | 0.349         | −14.5             | 99.95% | 7,248     |
| ETHUSDT 1h  | 724    | 36.6%    | −7,242  | −72.42% | 0.636         | −3.4              | 73.49% | 5,651     |

Exposure reads 100% in all runs (known TODO in metrics — always-in-market assumption).

## Why it loses: the structural finding

**Fees are approximately equal to the entire risked amount per trade.** Example
(first BTC 15m trade): entry 62,874.98, stop 122 points away (~0.19%). Fixed-fractional
sizing on that tight stop produced 0.159 BTC ≈ **$10,000 notional — 100% of equity — on a
$19 risk**. Round-trip spot taker fees at 10 bps ≈ $20 ≥ the risked $19. Every trade
starts ~−1R down on costs; SL exits realize −2.4R instead of −1R. With a ~30% hit rate
that structure cannot be profitable at any parameter setting — TP wins are eaten too.

Implications (strategy-level, beyond this campaign's plumbing scope):

- Tight SMC stops + fixed-fractional sizing needs a **fee-aware minimum stop distance**
  (or maker entries, or a notional-relative-to-stop cap). The live path shares this
  sizing (`decision/sizing.py`), so this finding applies to live trading too.
- The notional exposure cap did not bind at 100% of equity — verify
  `RiskParameters` defaults used by the backtest (`backtest/types.py`).

## Simulator defects exposed by this run (tracked follow-up)

1. **Trade size/PnL bookkeeping inconsistency**: trades exist with `size=1e-28` yet
   `net_pnl=−232` and `fees=116`; others with `size=2.7e-5` yet `net_pnl=+54`. PnL is
   computed on a different quantity than the recorded size (bracket/partial-exit trade
   assembly in `simulator.py`).
2. **R metrics poisoned**: `avg_r`, `avg_win_r`, `avg_loss_r` at ±1e27 — near-zero risk
   denominators (209 trades with |R| > 1000 in BTC 15m alone). Needs a guard and a
   correct risk basis.
3. **`total_slippage = 0.0`** in all runs despite slippage being applied inside fill
   prices — cost applied but never accumulated into reporting.

## Model caveats (by design, disclose when quoting numbers)

- 10 bps taker fee both sides; no maker fills; slippage 2 bps (1.5× on market/stop)
- Market entries fill at next-bar open; stop-first on same-bar TP+SL double-touch
- No funding, no partial fills, no order-book depth
- WFO sweeps only 7 parameters; `tp_ladder` and deep SMC/retest knobs are not sweepable
- Sharpe/Sortino annualized on the 365-day crypto calendar per bar timeframe (PR #185)

## Recommended next steps (in order)

1. ~~Fix the three simulator bookkeeping defects; re-run and update this report.~~
   Done — PR #191 + the v2 section above.
2. ~~Investigate the notional cap defaults in the backtest risk parameters.~~
   Done — caps now mirror live (10%/25%/5); the v2 numbers reflect them.
3. Strategy work: fee-aware stop-distance floor or maker-entry variant; re-baseline.
   The v2 loss-R excess (−1.3R…−2.5R vs theoretical −1R) quantifies the cost drag any
   variant must clear.
4. Only after a profitable, trustworthy baseline: revisit the mainnet-unlock question.
   Order-safety hardening (router C1–C7) proceeds regardless — it gates testnet soak,
   not strategy viability.
