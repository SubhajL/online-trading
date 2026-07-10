# Phase 3a — Live Daily Trend Co-Primaries → PaperBroker (Plan)

**Date:** 2026-07-10 · **Status:** approved design, implementation not started
**Provenance:** g-planning pass (Claude plan + independent Codex gpt-5.5 xhigh plan + Explore-agent pipeline map, synthesized)
**Prior:** `reports/backtest/2026-07-sizing-arm-results.md` (gates pass), `2026-07-statistical-hardening.md` (checklist 5/6 — bootstrap CI is the open item), `2026-07-robustness-track-c.md` + `2026-07-hmm-regime-study.md` (trailing/ADX/HMM all tested-and-rejected)

## 1. Goal

Run the v3 trend co-primaries — **tsmom-28d** and **price>SMA-65d**, daily,
long/cash, on BTCUSDT + ETHUSDT — as a LIVE signal source feeding the
existing **PaperBroker**, to start accruing genuine out-of-sample evidence.
Fresh OOS data is the only thing that can move the bootstrap-CI item of the
unconditional-GO checklist; a backtest cannot. Paper only: no live capital,
**no Go-router changes**, and the live SMC path stays byte-behavior-identical
when the feature is off.

## 2. Architecture decision (resolved fork)

**(B) Dedicated `trend_live` path calling PaperBroker directly in-process** —
NOT (A) emitting into the existing DecisionPublisher/RouterExecutionSubscriber
path. Reasons (both independent plans converged):

- `DecisionPublisher` consumes `EventType.RETEST_SIGNAL` only; the trend
  strategy produces desired-state targets, not retest signals.
- `RouterExecutionSubscriber` hard-filters
  `metadata["decision_source"] == "retest_decision_publisher"`
  (`execution/router_execution_subscriber.py:453-462`) and requires a TP;
  the co-primaries run `trend_tp_r=0` (no TP; exit on flip/stop).
- Template already exists: `paper/live_harness.py::_on_decision` builds a
  `PlaceBracketRequest` and calls `PaperBroker.place_bracket_order` directly.

**Three layers of isolation (the hard constraint):**

1. `TREND_LIVE_ENABLED=0` default — flag off ⇒ zero new behavior.
2. **Do NOT add `TimeFrame.D1` to the shared IngestService list**
   (`main.py:529` stays `[M5, M15, H1, H4]`) — daily candles would otherwise
   flow into FeatureService→SMCEngine→RetestEngine. The trend path owns a
   dedicated D1 REST poller instead (closed candles only; plumbing already
   supports "1d" end-to-end — WS/REST/ingest are interval-generic).
3. **No `TRADING_DECISION` events on the global bus** from the trend path in
   3a — direct in-process PaperBroker calls, so the router execution path can
   never see them. (Cost: no Telegram alerts in 3a; audit rows still written
   to `trading_decisions`. Alerts are a follow-up.)

## 3. Components

| Component                                               | Purpose                                                                                                                                             | Entry point                           | Registered in                          | DB tables                                        |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | -------------------------------------- | ------------------------------------------------ |
| `trend_live/config.py::load_trend_live_config_from_env` | flags + the two ex-ante `BacktestConfig`s (tsmom28 / sma65, `allow_short=False`, `trend_tp_r=0`)                                                    | `initialize_services`                 | `main.py` (flag-gated)                 | —                                                |
| `trend_live/daily_poller.py::TrendDailyCandlePoller`    | fetch closed D1 klines via `BinanceRestClient`, persist, feed the service                                                                           | own asyncio task                      | `main.py` under `TREND_LIVE_ENABLED=1` | `candles`                                        |
| `trend_live/decision_service.py::TrendDecisionService`  | warmup replay → `create_trend_engine` per (strategy × symbol) → desired-state diff (mirrors simulator `_apply_trend_target`) → sizing → PaperBroker | `on_daily_candle(candle)` from poller | `services["trend_decision_service"]`   | `trading_decisions`, `equity_samples`            |
| `PaperBroker` (extended)                                | zero-TP brackets (entry + 2×ATR STOP_MARKET only) + bracket-scoped `close_position(symbol, session_id)`                                             | direct calls                          | `services["trend_paper_broker"]`       | `paper_orders`, `paper_positions`, `paper_fills` |

Reuse, don't reimplement: `backtest/trend_signals.py::create_trend_engine`
(streaming engines), the simulator's desired-state/flip semantics
(`simulator.py::_apply_trend_target`), sizing
(`decision/sizing.py::size_with_exposure_caps` +
`backtest/position_sizing.py::notional_quantity`).

## 4. Correctness requirements

- **Bracket-scoped state.** 2 strategies × 2 symbols = 4 independent sleeves;
  the same symbol carries two positions (one per strategy). Close must be
  bracket-scoped — never `close_all_positions(symbol)`, or one strategy's
  flip flattens the other. PaperBroker positions are already keyed
  `(symbol, bracket_id)`.
- **Restart idempotence.** Deterministic `decision_id`/`client_order_id`
  derived from `(strategy_id, symbol, "1d", candle_open_time, action)`;
  warmup replays 28–65+ days of historical D1 candles through `on_bar`
  WITHOUT placing orders; open paper state is recovered from
  `paper_orders`/`paper_positions` before the first live diff.
- **Candle ordering per bar:** `PaperBroker.update_market_data(candle)` FIRST
  (fills resting stops), then engine `on_bar` + diff — mirrors the simulator.
- **Fail closed** when paper equity is missing/stale or stop distance
  invalid; a blocked entry self-heals on the next daily bar (desired-state
  re-diff).
- **SHORT degrades to FLAT** (long/cash, `allow_short=False`).

## 5. Decisions taken (defaults; revisit before PR3)

1. **Sizing:** `sizing_mode=notional`, **25% notional per sleeve** (4 sleeves
   ≈ 100% deployed when all long); caps as backstop.
2. **Direct-call, no bus emission** in 3a (no Telegram for trend paper
   signals yet; audit via `trading_decisions` rows).
3. **REST poller** for D1 (simple + robust for once-a-day bars), not a WS
   subscription.

## 6. PR breakdown (TDD; g-coding lifecycle each)

1. **PR1 — PaperBroker zero-TP + bracket-scoped close** (~0.5–1d).
   Tests: zero-TP bracket creates entry+stop only; `close_position` closes
   only the matching bracket; close cancels the resting stop first (no
   double exit fill).
2. **PR2 — `trend_live` pure logic** (~1–1.5d). Tests: warmup replays
   history without orders; LONG target places stop-only paper order; SHORT
   degrades to FLAT and closes the long; restart does not duplicate a
   client_order_id; two strategies keep separate bracket state; sizing
   fail-closed paths.
3. **PR3 — D1 poller + `main.py` default-off wiring** (~0.5–1d). Tests:
   poller ignores the open current-day candle; flag off ⇒ no wiring; flag on
   ⇒ shared ingest timeframes stay `[M5, M15, H1, H4]`.
4. **PR4 — integration smoke + runbook** (~0.5d). DB-backed BTC/ETH smoke,
   run commands, quality gates (`ruff check`, `ruff format --check`, `mypy`,
   `pytest`).

## 7. Risks / rollback

- Rollback = `TREND_LIVE_ENABLED=0`; open paper positions closable via the
  bracket-scoped close (or paper close-all if intentionally flattening).
- The no-TP/flip-exit modeling risk is contained in PR1's PaperBroker tests.
- Expectation setting: daily rules ≈ 8–15 trades/yr/symbol — 3a's near-term
  value is **engineering parity** (live desired-state logic matches the
  simulator), not fast CI shrinkage; the statistics accrue over years, and
  paper equity curves become the fresh-OOS input to the existing
  `run_bootstrap_ci.py`.

## 8. Relationship to Gap 1 / phase 3b

3a has **zero dependency on the Go router** and can merge while the 7-day
testnet soak (Gap 1 sign-off) runs. Phase 3b (testnet order flow through the
router) unlocks only after soak + C7 sign-off; note the C5/C6 runbook
finding that the BFF omits `client_order_ids`, so 3b's engine path must
supply them itself.
