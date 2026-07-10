# Trend Live Paper Trading — Runbook (Phase 3a)

**Scope:** run the v3 daily trend co-primaries — **tsmom-28d** and
**price>SMA-65d**, long/cash, BTCUSDT + ETHUSDT — as live signal sources
feeding a dedicated **PaperBroker**, to accrue genuine out-of-sample evidence.
Paper only: no live capital, no Go-router involvement.
Plan: `docs/plans/2026-07-10-phase-3a-trend-paper.md` · PRs #210 #211 #212 (+ this).

## Isolation guarantees

- `TREND_LIVE_ENABLED` unset/`0` (default) ⇒ **zero new behavior** — the
  wiring returns an empty dict; nothing is constructed.
- The shared ingest timeframes stay `[M5, M15, H1, H4]`; the trend path owns
  a dedicated D1 REST poller (mainnet public klines — the OOS evidence must
  match the backtest's data source, regardless of execution testnet mode).
- No `TRADING_DECISION` bus events: PaperBroker is called in-process, so the
  router execution path can never see trend decisions. (Consequence: no
  Telegram alerts in 3a; audit lives in `trading_decisions` rows.)

## Enable

```bash
# .env (engine process)
TREND_LIVE_ENABLED=1
# optional overrides (defaults shown)
TREND_LIVE_SYMBOLS=BTCUSDT,ETHUSDT
TREND_LIVE_NOTIONAL_PCT=0.25          # per sleeve; 4 sleeves ≈ 100% deployed
TREND_LIVE_STARTING_BALANCE=10000
TREND_LIVE_POLL_INTERVAL_SECONDS=300
TREND_LIVE_WARMUP_DAYS=90
```

```bash
make db-up && make db-migrate   # postgres + redis + schema
make dev-engine                 # or the full stack: make dev
```

Startup log lines to expect (flag on):

```
Trend live services initialized (paper-only, symbols=BTCUSDT,ETHUSDT, notional_pct=0.25)
Warmed up BTCUSDT with N daily candles
Recovered K open trend sleeves
TrendDailyCandlePoller started (symbols=BTCUSDT,ETHUSDT, interval=300s)
Started trend_daily_poller
```

## Verify

Daily bars close at 00:00 UTC; the poller picks the new bar up within one
poll interval. Expect **8–15 trades/yr/symbol** — most days nothing happens;
that is correct behavior, not a fault.

```sql
-- audit rows (deterministic uuid5 decision ids)
SELECT decision_id, symbol, action, quantity, stop_loss, reasoning, timestamp
FROM trading_decisions WHERE reasoning LIKE 'trend_live%' ORDER BY timestamp DESC LIMIT 20;

-- orders: entry = trend-{strategy}-{symbol}-1d-{yyyymmdd}-long, stop = …-long-sl, close = …-close
SELECT client_order_id, status, type, quantity, stop_price, paper_session_id
FROM paper_orders WHERE client_order_id LIKE 'trend-%' ORDER BY order_time DESC LIMIT 20;

-- open sleeves (one per strategy × symbol, at most 4)
SELECT p.symbol, p.side, p.quantity, p.entry_price, p.paper_session_id
FROM paper_positions p WHERE p.quantity > 0;
```

Semantics to know when reading state:

- **Sleeves are bracket-scoped.** The same symbol carries up to two positions
  (one per strategy), keyed `(symbol, paper_session_id)`. A strategy flip
  closes only its own bracket (`close_position`), and cancels that bracket's
  resting stop first — one candle can never double-exit a sleeve.
- **Restart is idempotent.** Client order ids derive from
  `(strategy, symbol, 1d, candle open, action)`; warmup replays history
  without trading and open sleeves are recovered from `paper_orders` ⋈
  `paper_positions` before the first live diff. Replayed candles are no-ops.
- **Fail closed, self-heal.** Missing/err equity, invalid stop, REST or DB
  outage ⇒ the action is skipped and the desired-state diff retries on the
  next daily bar.

## Rollback

1. Set `TREND_LIVE_ENABLED=0` and restart the engine — the path vanishes.
2. Open paper positions can simply be left (they are paper rows). To flatten
   them explicitly, start the standalone paper broker server against the same
   database (`python -m app.engine.paper.server --config <paper.yaml>`; it
   recovers state from `paper_orders`/`paper_positions`) and call the
   bracket-scoped close once per open `paper_session_id`:
   `POST /close_position {"symbol": "...", "paper_session_id": "..."}`.
   The in-engine trend broker does not expose HTTP.

## Quality gates / smoke

```bash
cd app/engine && source .venv/bin/activate
ruff check . && ruff format --check . && mypy . && pytest tests/unit/ -v

# DB-backed BTC/ETH smoke (any TimescaleDB works; throwaway container shown)
docker run -d --name trend-smoke-timescale -p 5433:5432 \
  -e POSTGRES_USER=trading_user -e POSTGRES_PASSWORD=your_secure_password_here \
  timescale/timescaledb:latest-pg16
TEST_DATABASE_URL="postgresql://trading_user:your_secure_password_here@localhost:5433/trading_platform_test" \
  pytest tests/integration/test_trend_live_smoke.py -m integration -v
docker rm -f trend-smoke-timescale
```

## Caveats

- The equity provider aggregates **all** `paper_positions` rows plus
  `TREND_LIVE_STARTING_BALANCE`. If the SMC live-paper harness writes to the
  same paper tables, point one of them at a separate database (the trend
  sleeves themselves stay isolated either way — only sizing input mixes).
- Ex-ante configs are frozen to the backtested v3 daily taker arm
  (`reports/backtest/strategies/v3-{tsmom28,sma65}-taker.yaml`). Changing a
  knob in `trend_live/config.py` silently invalidates the accruing evidence —
  don't, without pre-registering a new arm.
- Paper equity curves feed `run_bootstrap_ci.py` as fresh OOS input; the
  statistics accrue over months-to-years. 3a's near-term value is engineering
  parity with the simulator, not fast CI shrinkage.
