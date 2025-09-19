# Parallel Branch Plan (Prompts #2–#10)

## Roles (assign real names)
- **QE** = Quant Engineer (indicators/SMC/retest/decision)
- **DE** = Data Engineer (ingestor, DAL, migrations)
- **RE** = Router Engineer (Go/Node order router)
- **FE** = Front-end Engineer (Next.js UI)
- **BE** = Backend Engineer (BFF/NestJS, alerting)
- **DO** = DevOps (CI/CD, observability)

All branches target main; squash-merge with green CI only.

---

## Wave A (run in parallel after Prompt #1 is merged)

### A1 — Contracts & Schema Pack (Prompt #2)
- **Branch**: `feature/contracts-schema`
- **Owner**: QE (backup: BE)
- **Scope**: `/contracts/**`, `/contracts/gen/**`, `/scripts/codegen_contracts.py`, `/tests/contracts/**`, append CI job
- **CI Gate**: `contracts-validate`
- ✅ JSONSchema validation (sample payloads)
- ✅ make contracts generates Python/TS/Go types
- **Definition of Done (DoD)**:
  - Schemas for candles.v1, features.v1, smc_events.v1, zones.v1, signals_raw.v1, regime.v1, news_window.v1, funding_window.v1, decision.v1, order_update.v1
  - Generated types imported in a tiny demo file in engine/BFF/router
- **Merge order**: Merge after A2 (#3) or in any order; low conflict risk

### A2 — DB Migrations & DAL (Prompt #3)
- **Branch**: `feature/db-migrations`
- **Owner**: DE
- **Scope**: `/db/migrations/**`, `/app/engine/adapters/db/**`, `/tests/db/**`, append CI job
- **CI Gate**: `db-migrate`
- ✅ Migrations apply in Compose (Timescale)
- ✅ Idempotent upserts for candles
- **DoD**:
  - Tables & PKs exactly per PRD (candles, indicators, swings, smc_events, zones, orders, positions)
  - Timescale hypertable on candles(open_time); key indexes present
- **Merge order**: Merge first in Wave A

### A3 — Order Router (Go) + Testnet (Prompt #9)
- **Branch**: `svc/router`
- **Owner**: RE (backup: DO)
- **Scope**: `/app/router/**` (+ Makefile/Dockerfile), append CI job
- **CI Gate**: `router-smoke`
- ✅ Healthz/Readyz pass
- ✅ /place_bracket against Binance Spot testnet returns ACK (keys pulled from CI secrets)
- **DoD**:
  - Spot: simulate bracket via multi-limit TPs + stop-limit SL
  - USD-M: ReduceOnly TPs; STOP_MARKET SL; leverage & positionMode
  - Idempotent newClientOrderId; order_update.v1 emitted
- **Merge order**: After A2; independent of A1

---

## Wave B (start after Wave A merges; B3 can start early with mocks)

### B1 — WS Ingestor (Spot & Futures) + REST backfill (Prompt #4)
- **Branch**: `svc/ingestor`
- **Owner**: DE
- **Scope**: `/app/engine/ingest/**`, types.py, config.yaml, `/tests/ingest/**`
- **CI Gate**: included in `ingestor-tests` (add if desired)
- ✅ Closed-candle (k.x==true) logic unit tests
- ✅ Gap backfill test with fixtures
- **Integration Gate**: candles rows grow in DB; tail log shows "CLOSED candle"
- **Merge order**: First in Wave B

### B2 — Indicator Math & Feature Engine (Prompt #5)
- **Branch**: `svc/features`
- **Owner**: QE
- **Scope**: `/app/engine/shared/math/**`, `/app/engine/features/**`, `/tests/golden/**`
- **CI Gate**: `features-golden`
- ✅ Golden vectors (EMA/RSI/MACD/ATR/BB/VWAP) match fixtures byte-for-byte
- **Integration Gate**: indicators written to DB; features.v1 events visible
- **Merge order**: After B1

### B3 — BFF (NestJS) + Next.js UI + Alerts (Prompt #10)
- **Branch**: `ui/bff`
- **Owner**: FE (backup: BE)
- **Scope**: `/app/bff/**`, `/app/ui/**`, `/app/engine/alert/**`
- **CI Gate**: `ui-bff-build`
- ✅ BFF compiles + lint; UI builds
- **Integration Gate**: UI renders live candles; overlays toggle; PB panel hits mocked endpoint (then real Router after C3)
- **Merge order**: After B1/B2 (or earlier using mocks with UI_USE_MOCKS=true)

---

## Wave C (staged; depends on A & B)

### C1 — SMC Engine (pivots, CHOCH/BOS, OB/FVG) (Prompt #6)
- **Branch**: `svc/smc`
- **Owner**: QE
- **Scope**: `/app/engine/smc/**`, `/tests/smc/**`
- **CI Gate**: `smc-tests`
- ✅ CHOCH/BOS sequence tests
- ✅ FVG/OB detection tests
- **Integration Gate**: smc_events.v1 + zones.v1 populate; overlays show HH/HL/LH/LL, CHOCH/BOS, OB/FVG

### C2 — Retest Analyzer + Regime/News/Funding Guards (Prompt #7)
- **Branch**: `svc/retest-guards`
- **Owner**: QE (backup: BE for calendar)
- **Scope**: `/app/engine/retest/**`, `/app/engine/regime_vol/**`, `/app/engine/news_funding_guards/**`
- **CI Gate**: `retest-guards-tests`
- ✅ "Good retest" unit tests pass
- ✅ Guards flip SAFE/BLOCK on synthetic schedules
- **Integration Gate**: signals_raw.v1 begins emitting; guard state visible in UI badges

### C3 — Decision Engine & Risk (Spot + Futures-aware) (Prompt #8)
- **Branch**: `svc/decision`
- **Owner**: QE + BE
- **Scope**: `/app/engine/decision/**`, `/app/engine/adapters/router_client/**`, `/tests/decision/**`
- **CI Gate**: `decision-tests`
- ✅ Position sizing in R; RR ladder math; BE at TP1; ATR trail (optional)
- ✅ Rounding uses exchangeInfo filters; unit tests cover LOT_SIZE/PRICE_FILTER
- **Integration Gate**: decisions flow → Router testnet places bracket; order_update.v1 updates UI blotter

---

## Optional (Bonus) — Backtester + Paper Broker + WFO

(Can start once #5 is merged; no dependency on #9 Router)
- **Branch**: `svc/backtest-paper-wfo`
- **Owner**: QE (backup: DO)
- **CI Gate**: `backtest-smoke`
- ✅ 2-week BTCUSDT 15m backtest completes; report.json keys present
- ✅ Paper broker API parity tests pass

---

## Merge Order Summary
1. **Wave A**: `feature/db-migrations` → `feature/contracts-schema` → `svc/router`
2. **Wave B**: `svc/ingestor` → `svc/features` → `ui/bff`
3. **Wave C**: `svc/smc` → `svc/retest-guards` → `svc/decision`
4. **Bonus**: `svc/backtest-paper-wfo` can merge after #5

---

## CI Matrix (jobs to appear in /.github/workflows/ci.yml)
- `contracts-validate` (Prompt #2)
- `db-migrate` (Prompt #3)
- `router-smoke` (Prompt #9)
- `features-golden` (Prompt #5)
- `smc-tests` (Prompt #6)
- `retest-guards-tests` (Prompt #7)
- `decision-tests` (Prompt #8)
- `ui-bff-build` (Prompt #10)
- `backtest-smoke` (Bonus)

**Rule**: append new jobs; do not modify or remove existing jobs.

---

## Guardrails & Rollback
- **Secrets**: Only the Router job reads Binance keys; all other jobs use mocks/fixtures.
- **Feature flags**: `PAPER_MODE`, `FUTURES_ENABLED`, `UI_USE_MOCKS`.
- **Rollback**: revert PR; flip feature flags off; Router supports CloseAll(ReduceOnly) for perps.
- **Observability**: ensure each branch adds metrics/logs for its new components.

---

## Quick Start Timeline (aggressive)
- **Day 0**: Merge Prompt #1 (scaffold)
- **Days 1–2**: Wave A branches open; CI jobs added
- **Days 3–5**: Merge Wave A; open Wave B
- **Days 6–10**: Merge B1/B2; UI swaps from mocks to live; open Wave C
- **Days 11–15**: Merge C1/C2; testnet end-to-end
- **Days 16–20**: Merge C3; live-small readiness