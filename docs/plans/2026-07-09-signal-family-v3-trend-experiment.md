# Signal Family v3 — Trend-Continuation Experiment Plan

**Date:** 2026-07-09 (rev 2, post-research) · **Status:** PLANNED (not implemented)
**Branch (when implemented):** `exp/trend-signals-v3`
**Synthesis of:** Claude plan + independent architect counter-plan (verified mechanics against actual code; Codex quota-blocked) + crypto signal-family deep-research (`docs/reviews/2026-07-09-crypto-signal-families-research.md`, 20 claims verified 3-0).

---

## 1. Overview

Add a config-selectable **trend-following signal source** to the backtest engine beside the existing SMC retest signal. `signal_source` selects one of: `"smc_retest"` (default — **SMC stays as the control arm and remains fully selectable**), `"price_sma"`, `"tsmom"`, `"ema_cross"`, `"donchian"`. The trend engines are self-contained streaming state machines in a new `app/engine/backtest/trend_signals.py`; the simulator diffs each engine's _desired state_ against the open position (flip-close via reduce-only MARKET order, then reverse where allowed), while the entire existing gate/size/bracket chain (`_trend_allows` → min-stop floor → policies → `size_with_exposure_caps` → pretrade risk → cooldown → brackets) is reused untouched. Every run reports **buy-and-hold benchmark metrics + excess return**.

**Research-driven framing (rev 2):** the evidenced configuration is **long-only (long/cash), DAILY bars, multi-week lookbacks**. Its realistic payoff is _drawdown reduction at roughly buy-and-hold returns_ (OOS template: Sharpe 1.11 vs 1.13, maxDD 52% vs 62%), net Sharpe plausibly 0.5–1.0. The short side of crypto momentum loses in 19/20 studied combos pre-cost, so long/short runs are a **diagnostic, not the GO bar**. No verified evidence supports 15m-class trend rules; 1h has partial support only.

Why the pivot: the SMC retest arm has measured negative gross edge (−23%/2yr baseline; −5% with execution fixes; audit: strategy-not-code). Trend-following is the one family with top-journal, net-of-cost-surviving support on BTC/ETH (Liu & Tsyvinski RFS 2021; Hudson & Urquhart breakeven costs 57–66 bps vs our ~10 bps fees).

## 2. Key design decisions (with rationale)

1. **Desired-state, not edge-triggered**: engines emit `TrendTarget {desired: LONG|SHORT|FLAT, entry, stop_loss, ready}` **every bar**; the simulator diffs against the actual position. Self-healing when a risk gate blocks an entry.
2. **No fills.py changes** (verified by code trace): a reduce-only MARKET order already fills at next-bar open + slippage, takes the no-bracket fall-through in `_execute_fill`, and lands in side-agnostic `_close_position`.
3. **Cancel resting brackets at flip-submission time** — else a bar touching the old stop double-fills and charges a **phantom fee** (fee is unconditional at the top of `_execute_fill`). New `_cancel_position_brackets(symbol)`.
4. **Ordering invariant**: on flip-and-reverse, the close order must be appended **before** the reverse entry, or the entry hits the "netting unsupported" branch (fees charged, brackets orphaned). Regression-tested.
5. **Optional TP leg** (~6 lines): `_BracketSpec.take_profit: Decimal | None`; skip LIMIT leg + OCO registration when None. Default `trend_tp_r = 0` — let winners run.
6. **Own streaming state per engine** — bounded deques + O(1) Wilder ATR (parity-tested vs batch calculator). The shared 200-candle deque is too short and `_calculate_features`/SMCEngine are skipped on the trend path.
7. **Exits**: flip-close (`ExitReason.FLIP` via `_exit_reason_overrides` consulted in `_execute_fill`) + optional `max_hold_bars` timeout. Donchian uses turtle asymmetric entry/exit channels. **ATR trailing deferred to phase 2.**
8. **Regime gate reused**: existing `htf_ema_period`/`htf_ema_fast` EMA-stack gate applies for free. ADX/HMM deferred — zero verified claims survived for regime filters (open question, not disproof).
9. **Guard**: `invert_signals=True` + trend source → `ValueError` (SMC-only diagnostic; `tp1` may be None on trend arm).
10. **Ex-ante parameters from the verified literature** (no tuning): price-vs-SMA 20d/65d/200d; SMA/EMA cross 10/40d; TSMOM 28d; Donchian 20d/10d (turtle); 2×ATR stops. ±50% sensitivity is robustness _reporting_ only. Low turnover + maker fees explicitly favored (short lookbacks bleed the most Sharpe to costs).
11. **Inverse-vol sizing falls out free**: fixed-fractional risk + ATR stop ⇒ qty ∝ 1/ATR. (Vol-managed literature: helps in-sample, doesn't fix power-law tails — reported, not oversold.)

## 3. Config knobs (`BacktestConfig`, flat; defaults preserve SMC behavior; lookbacks in BARS, defaults oriented to the primary 1d arm — 1h configs must scale ×24)

```python
signal_source: str = "smc_retest"   # "smc_retest" | "price_sma" | "tsmom" | "ema_cross" | "donchian"
allow_short: bool = False           # long/cash is the evidenced form; long/short is a diagnostic
atr_period: int = 14
atr_stop_mult: Decimal = Decimal(2) # turtle 2N initial stop
sma_period: int = 200               # price-vs-SMA long/cash rule (20/65/200d menu)
tsmom_lookback: int = 28            # 28d TSM (Han et al. — flagged in-sample-optimal; report honestly)
tsmom_deadband_bps: Decimal = Decimal(0)  # hysteresis inside dead-band
ema_fast: int = 10                  # 10/40d cross (consistent gross performer)
ema_slow: int = 40
donchian_entry: int = 20            # 20d/10d turtle channels
donchian_exit: int = 10
max_hold_bars: int = 0              # 0 = off
trend_tp_r: Decimal = Decimal(0)    # 0 = no TP; let winners run
```

Plus `ExitReason.FLIP = "flip"`, and on `BacktestMetrics`: `benchmark_return_pct`, `benchmark_max_drawdown_pct`, `benchmark_sharpe_ratio`, `excess_return_pct` (defaulted → serializer-safe). `bars_per_year(D1)=365` already correct for 24/7 crypto.

## 4. Data prep (new step, research-driven)

- **Fetch ~7 years of daily klines** via the existing Binance downloader (`download.py`): `btcusdt_1d.csv`, `ethusdt_1d.csv`, 2019-01-01 → 2026-06-30. Rationale: resampling our 2-yr 1h data leaves only ~530 tradable daily bars after a 200d warmup and **contains no full bear market** — the drawdown-protection claim (the whole point of the family) is only testable across 2021–22.
- Keep existing 2-yr 1h CSVs for the secondary arm. 15m dropped (no supporting evidence at retail fees).

## 5. Files to change

| File                                                            | Change                                                                                                                                                                                                                                             |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/engine/backtest/trend_signals.py`                          | **NEW** — `TrendTarget`, `_StreamingAtr`, `PriceSmaEngine`, `TsmomEngine`, `EmaCrossEngine`, `DonchianEngine`, `create_trend_engine` (ValueError on unknown source)                                                                                |
| `app/engine/backtest/types.py`                                  | knobs above, `ExitReason.FLIP`, 4 benchmark metric fields                                                                                                                                                                                          |
| `app/engine/backtest/simulator.py`                              | trend branch in `process_candle` (SMC branch byte-identical), `_apply_trend_target`, `_build_trend_signal`, `_submit_position_close`, `_cancel_position_brackets`, `_check_max_hold`, optional-TP bracket, exit-reason override, constructor guard |
| `app/engine/backtest/metrics.py`                                | `MetricsCalculator.apply_benchmark(metrics, closes)`                                                                                                                                                                                               |
| `app/engine/backtest/runner.py`                                 | knob parsing, collect closes in `_run_simulation`, apply benchmark, serialize + log excess                                                                                                                                                         |
| `app/engine/tests/unit/backtest/test_trend_signal_engine.py`    | **NEW** — pure engine tests                                                                                                                                                                                                                        |
| `app/engine/tests/unit/backtest/test_simulator_trend_wiring.py` | **NEW** — simulator integration                                                                                                                                                                                                                    |
| `app/engine/tests/unit/backtest/test_metrics_benchmark.py`      | **NEW**                                                                                                                                                                                                                                            |
| `app/engine/tests/unit/backtest/test_runner_trend_config.py`    | **NEW**                                                                                                                                                                                                                                            |
| `reports/backtest/strategies/v3-*.yaml`                         | **NEW** ex-ante configs (see matrix)                                                                                                                                                                                                               |
| `scripts/analyze_strategy_runs.py`                              | read benchmark fields when present (same B&H convention)                                                                                                                                                                                           |

## 6. Functions

**trend_signals.py**

- `TrendTarget` — frozen dataclass: `desired`, `entry`, `stop_loss`, `ready`.
- `_StreamingAtr.update(candle) -> Decimal | None` — O(1) Wilder ATR, seeded with simple mean of first N TRs (parity with `TechnicalIndicatorsCalculator`).
- `PriceSmaEngine.on_bar(candle) -> TrendTarget` — rolling SMA over `sma_period` closes; desired LONG when close > SMA else FLAT (never SHORT — the evidenced long/cash rule).
- `TsmomEngine.on_bar` — trailing `tsmom_lookback`-bar return vs dead-band with hysteresis.
- `EmaCrossEngine.on_bar` — streaming fast/slow EMAs; LONG when fast>slow; ready after `ema_slow` bars.
- `DonchianEngine.on_bar` — entry/exit channels from bounded deques, current bar excluded; turtle asymmetric exits; SHORT states allowed (simulator enforces `allow_short`).
- `create_trend_engine(config)` — factory keyed on `signal_source`.

**simulator.py**

- `process_candle` — SMC branch verbatim when `signal_source == "smc_retest"`; else `_check_max_hold` → `engine.on_bar` → `_apply_trend_target` (SMCEngine + `analyze_retest` skipped).
- `_apply_trend_target(target, candle)` — SHORT degrades to FLAT when `allow_short=False`; side mismatch → `_submit_position_close(FLIP)`; then `_build_trend_signal` → existing `_execute_signal`.
- `_build_trend_signal(target, candle) -> dict` — retest-shaped dict; `zone_id=f"trend-{signal_source}"`; `tp1=None` when `trend_tp_r==0`.
- `_submit_position_close(symbol, reason, candle)` — duplicate-pending-close guard; `_cancel_position_brackets`; reduce-only MARKET sized to position; record exit-reason override.
- `_cancel_position_brackets(symbol)` — cancel resting STOP/LIMIT legs, clean `_oco_pairs`.
- `_check_max_hold(candle)` — timeout close from `position.opened_at` + `_BAR_MINUTES`.
- `_execute_fill` — `reason = self._exit_reason_overrides.pop(order.id, None) or _EXIT_REASONS.get(...)`.

**metrics.py / runner.py**

- `apply_benchmark(metrics, closes)` — B&H equity `initial × close_i/close_0`; sets 4 fields incl. `excess_return_pct`; same annualization factor as strategy Sharpe.
- Runner: collect `(close_time, close_price)` during `_run_simulation` (runner sees every raw candle; simulator stays pure), apply benchmark, serialize, log.

## 7. Test coverage (TDD — failing tests first)

**test_trend_signal_engine.py** (pure)

- `test_price_sma_long_when_close_above_sma` — long/cash rule fires
- `test_price_sma_flat_when_close_below_sma` — exits to cash, never SHORT
- `test_tsmom_goes_long_after_positive_trailing_return`
- `test_tsmom_deadband_holds_previous_state_in_chop` — hysteresis
- `test_tsmom_not_ready_before_lookback_filled` — warmup silence
- `test_ema_cross_flips_short_when_fast_crosses_below`
- `test_ema_cross_stop_is_k_atr_below_entry` — exact stop math
- `test_donchian_breaks_prior_n_bar_high_excluding_current`
- `test_donchian_exits_on_exit_channel_break_not_entry_channel` — turtle asymmetry
- `test_streaming_atr_matches_indicators_batch_atr` — parity invariant
- `test_engine_memory_stays_bounded_at_lookback`
- `test_factory_raises_on_unknown_signal_source`

**test_simulator_trend_wiring.py** (idioms from `test_simulator_strategy_knobs.py`)

- `test_trend_source_places_market_entry_with_stop_only_bracket`
- `test_trend_source_skips_smc_engine_and_analyze_retest`
- `test_flip_cancels_brackets_closes_then_reverses_next_bar` — ordering invariant
- `test_flip_close_records_exit_reason_flip`
- `test_allow_short_false_closes_long_without_reversing` — long/cash degrade
- `test_stale_stop_cannot_double_fill_after_flip_close` — phantom-fee regression
- `test_max_hold_bars_closes_position_with_timeout_reason`
- `test_trend_tp_r_positive_places_limit_tp_with_oco`
- `test_htf_gate_still_vetoes_counter_trend_entries`
- `test_default_config_still_runs_smc_retest_path` — SMC regression guard
- `test_invert_signals_with_trend_source_raises`

**test_metrics_benchmark.py**

- `test_benchmark_return_matches_first_to_last_close` · `test_benchmark_max_drawdown_from_peak` · `test_benchmark_sharpe_uses_timeframe_annualization` · `test_excess_return_is_strategy_minus_benchmark`

**test_runner_trend_config.py**

- `test_yaml_loads_trend_knobs_into_config` · `test_missing_trend_keys_default_to_smc_path` · `test_report_json_includes_benchmark_and_signal_source`

## 8. Wiring verification

| New export                                             | Imported by                                                                  | Called from (runtime)                                      |
| ------------------------------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `create_trend_engine`                                  | `simulator.py`                                                               | `__init__` when `signal_source != "smc_retest"`            |
| `*Engine.on_bar`                                       | via factory                                                                  | `process_candle` trend branch, every closed bar            |
| `TrendTarget`                                          | `simulator.py`, tests                                                        | consumed by `_apply_trend_target`                          |
| `_apply_trend_target` / `_build_trend_signal`          | internal                                                                     | `process_candle` → existing `_execute_signal`              |
| `_submit_position_close` / `_cancel_position_brackets` | internal                                                                     | flip + `_check_max_hold`                                   |
| `ExitReason.FLIP`                                      | `simulator.py`                                                               | override dict → `_execute_fill` → trades.csv `exit_reason` |
| `_BracketSpec.take_profit: Decimal \| None`            | internal                                                                     | `_place_bracket_orders` skips TP leg                       |
| `apply_benchmark`                                      | `runner.py`                                                                  | `run_backtest` after `calculate_metrics`                   |
| benchmark fields                                       | `runner.py`, `serializers.py` (attr-by-name, additive-safe), analysis script | JSON report + CLI log                                      |
| new knobs                                              | `runner.py` `_load_config` → constructors                                    | engines/branches                                           |

Dead-end check: every new export has a runtime caller; `trail_*` fields deliberately stay dead (phase 2).

## 9. Experiment matrix + GO/NO-GO (rev 2 — research-aligned)

**Primary arm — daily bars, long/cash (`allow_short: false`), 2019→2026 (covers the 2021–22 bear):**

| Config         | Rule                  | Lookback                                |
| -------------- | --------------------- | --------------------------------------- |
| v3-sma200      | price > SMA else cash | 200d                                    |
| v3-sma65       | 〃                    | 65d                                     |
| v3-sma20       | 〃                    | 20d (cost-fragile — expected worst net) |
| v3-cross-10-40 | EMA cross             | 10/40d                                  |
| v3-tsmom28     | trailing-return sign  | 28d                                     |
| v3-donch-20-10 | turtle channels       | 20d/10d                                 |

× {BTCUSDT, ETHUSDT} × costs {taker 10 bps, maker 4 bps} → 24 runs (fast: ~2.7k daily bars each).

**Diagnostic arm:** best daily config with `allow_short: true` — literature predicts the short leg _loses_; if it profits, suspect an implementation bug before celebrating.
**Secondary arm:** best 2 configs on 1h (2024→2026, lookbacks ×24) — partial evidence only (Borgards, ≤2019).
**Control arm:** rerun s3/s4 SMC configs over the identical windows.
**Sensitivity:** ±50% primary lookback per family — robustness reporting only, never selection.

**GO** (per symbol, primary arm): net Sharpe ≥ 0.9 × B&H Sharpe **AND** maxDD ≤ 0.8 × B&H maxDD **AND** net total return ≥ 0.75 × B&H **AND** result does not flip sign across ±50% sensitivity. Report trade count N prominently (daily trend rules trade rarely; expect wide CIs).
**NO-GO**: fails the above on either symbol, or only the cost-fragile short lookbacks pass (cost artifact), or the 2021–22 bear segment shows no drawdown protection (the family's entire value proposition).
**Expectation set ex-ante** (so we can't move goalposts): net Sharpe 0.5–1.0, return ≈ B&H, maxDD materially lower, ≥1 losing year, decay risk — no verified academic sample extends past Aug 2023, so our 2024–26 segment is novel evidence either way.

## 10. Risks + rollback

1. **Stale-bracket double fill / phantom fee** — brackets cancelled synchronously at flip submission; regression test.
2. **Flip ordering** — close before reverse entry; regression test.
3. **Re-entry churn after stop-out** — desired-state re-enters next bar if the engine still says LONG; honest but fee-heavy in chop; dead-band + fee reporting surface it; no tuning knob added ex-ante.
4. **Lookback/timeframe confusion** — knobs in bars, defaults for 1d; 1h configs must scale ×24 (YAML comments; absurd trade counts caught in report sanity checks).
5. **SMC default regression** — SMC branch byte-identical; 65 existing tests + explicit default-path test.
6. **Data risk** — 1d download needs Binance history depth (BTC/ETH fine from 2019); verify row counts + gap scan before running.
7. **Uncommitted main work** — strategy-knob work is load-bearing; branch `exp/trend-signals-v3`, commit those knobs first on the branch.
8. **Rollback** — dark-launch (`signal_source` unset = SMC); no schema/DB changes; JSON additions additive; revert = drop branch.

## 11. Estimate & phases

~2–2.5 focused days: types/config 1h · data download/validation 1–2h · trend_signals + engine tests 4–5h (5 engines) · simulator wiring + tests 4–5h · metrics/runner + tests 2h · quality gates 1h · ~30 runs + report 3–4h.
**Phase 2 (only if GO):** ATR trailing (`trail_atr_mult`), regime-filter study (ADX/HMM — open question in the literature), walk-forward via existing `wfo.py`, funding-carry/on-chain research if desired.

## 12. SMC status

SMC retest remains the default `signal_source` and the experiment's control arm. Nothing is removed. The separately-documented SMC cleanups (dead CHOCH-OB code, `candles[-2]` OB pick, smoke-test pin) stay optional hygiene PRs — audited as not affecting profitability.
