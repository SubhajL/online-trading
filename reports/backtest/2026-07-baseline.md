# Backtest Baseline Report — 2026-07-05

First real-data backtest of the strategy pipeline in this project's history. Prior to
PR #181 the backtester optimized a hardcoded mock; prior to PR #185 the runner could not
actually load downloaded data (naive/aware datetime mismatch silently yielded zero candles,
and the shell wrapper's import path never worked). Both are fixed; these are the first
honest numbers.

## Verdict: NO-GO for mainnet — and the numbers themselves are not yet trustworthy

The strategy, as configured with engine defaults, loses catastrophically on 2 years of
real data. But the run also exposed simulator bookkeeping defects (below) that distort
per-trade accounting, so treat these numbers as "definitely not good", not as a precise
measurement. Fix the bookkeeping (tracked follow-up), re-run, then judge the strategy.

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

1. Fix the three simulator bookkeeping defects; re-run this exact baseline (config hash
   must match) and update this report.
2. Investigate the notional cap defaults in the backtest risk parameters.
3. Strategy work: fee-aware stop-distance floor or maker-entry variant; re-baseline.
4. Only after a profitable, trustworthy baseline: revisit the mainnet-unlock question.
   Order-safety hardening (router C1–C7) proceeds regardless — it gates testnet soak,
   not strategy viability.
