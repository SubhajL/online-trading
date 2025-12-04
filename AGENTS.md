# AGENTS.md — Online Trading Platform Playbook

## Purpose
Guidelines for AI-assisted programming in this repository to ensure maintainability, safety, and delivery speed.
Architecture reference: `CONTEXT.md`.

## AI-Assisted Programming Guidelines (Sabrina Ramonov)
- **BP-1 (MUST)** Ask clarifying questions before coding.  
- **BP-2 (SHOULD)** Confirm an approach for complex work.  
- **BP-3 (SHOULD)** List pros/cons when multiple approaches exist.  
- **C-1 (MUST)** Follow TDD: stub → failing test → implement.  
- **C-2 (MUST)** Use domain vocabulary for names.  
- **C-3 (SHOULD NOT)** Add classes when small functions suffice.  
- **C-4 (SHOULD)** Keep functions simple, composable, testable.  
- **C-5 (MUST)** Prefer branded `type`s for IDs.  
- **C-6 (MUST)** Use `import type { … }` for type-only imports.  
- **C-7 (SHOULD NOT)** Add comments except for critical caveats.  
- **C-8 (SHOULD)** Default to `type`; use `interface` only when clearer.  
- **C-9 (SHOULD NOT)** Extract new functions unless reused, required for testing, or to untangle opaque logic.  
- **T-1 (MUST)** Colocate unit tests for simple functions in `*.spec.ts`.  
- **T-2 (MUST)** For API changes, extend `packages/api/test/*.spec.ts`.  
- **T-3 (MUST)** Separate pure-logic unit tests from DB integration tests.  
- **T-4 (SHOULD)** Prefer integration tests over heavy mocking.  
- **T-5 (SHOULD)** Thoroughly test complex algorithms.  
- **T-6 (SHOULD)** Assert full structures in one assertion when possible.  
- **D-1 (MUST)** Type DB helpers as `KyselyDatabase | Transaction<Database>`.  
- **D-2 (SHOULD)** Fix bad generated DB types in `packages/shared/src/db-types.override.ts`.  
- **O-1 (MUST)** Put code in `packages/shared` only when used by ≥2 packages.  
- **G-1 (MUST)** `prettier --check` passes.  
- **G-2 (MUST)** `turbo typecheck lint` passes.  
- **GH-1 (MUST)** Use Conventional Commits.  
- **GH-2 (SHOULD NOT)** Mention OpenAI or Codex in commits.

### Writing Functions Checklist
1) Readability is immediate.  
2) Avoid high cyclomatic complexity.  
3) Prefer standard data structures/algorithms when they simplify logic.  
4) No unused parameters.  
5) Move type casts to arguments when possible.  
6) Testable without mocking core systems; otherwise use integration tests.  
7) Expose meaningful dependencies via arguments.  
8) Consider better names consistent with domain vocabulary.  
Only refactor out a new function if reused, required for testing, or to clarify opaque logic.

### Writing Tests Checklist
1) Parameterize inputs; avoid unexplained literals.  
2) Only add tests that can fail on real defects.  
3) Test names must match the final assertion.  
4) Compare to independent expectations, not recycled outputs.  
5) Follow prod standards (prettier, ESLint, strict types).  
6) Prefer properties/invariants (use `fast-check` when helpful).  
7) Group under `describe(functionName, ...)`.  
8) Use `expect.any(...)` for unconstrained parameters.  
9) Prefer strong assertions (e.g., `toEqual`).  
10) Cover edge cases, realistic/odd inputs, boundaries.  
11) Skip conditions enforced by the type system.

## Repository & Product Context
- **Key docs**: `PRD - Online Trading.md` (product spec), `CONTEXT.md` (architecture/contracts), `PROJECT_PLAN.md`, `README.md`.  
- **Three planes**: Data (WS ingest → features → SMC → decision → router → exchange), Control (backtester, parameter store, risk limits, calendars/funding, A/B/reporting), Experience (Next.js UI, BFF API/WS, Telegram/LINE alerts).  
- **Modules & dirs**: `app/engine` (Python FastAPI core; async event bus; ingest, features, smc, retest, regime_vol, news_funding_guards, decision, paper, backtest, plugins), `app/router` (Go order router/gateway), `app/bff` and `app/ui` (NestJS BFF, Next.js UI), `infra` (Docker/Compose, Prometheus/Grafana, DB assets), root automation (`Makefile`, `.editorconfig`, `pyproject.toml`, `pnpm-workspace.yaml`).  
- **Service responsibilities (PRD)**:  
  - WS ingestors (spot/futures Binance): dedup on symbol/tf/open_time; emit only closed candles; REST backfill; publish `candles.v1` and upsert DB.  
  - Feature Engine: EMA20/50/200, RSI14, MACD(12/26/9), ATR14, BB(20,2), VWAP/VWMA; emits `features.v1`, writes `indicators`.  
  - SMC Engine: pivots (ATR-scaled ZigZag or N-bar), HH/HL vs LH/LL, CHOCH/BOS, FVG, OB; emits `swings.v1`, `smc_events.v1`, `zones.v1`.  
  - Retest Analyzer: waits up to N bars for OB/FVG retest (0.25×ATR tolerance) with MACD hist uptick and RSI 40–55 bounce; emits `signals_raw.v1` (entry/SL/TP skeleton, score, TTL).  
  - Regime/Vol Bot: trend vs range classifier → `regime.v1`.  
  - News/Funding Guards: calendar + funding scheduler; guard helpers `news_guard`, `funding_guard`, `vol_guard`.  
  - Decision Engine: gates on guards; requires structure (CHOCH→BOS) plus retest or indicator confluence; builds bracket (entry/SL + TP ladder); fixed-fractional 0.5% sizing with ATR scaling, leverage ≤3×, ReduceOnly TPs, STOP_MARKET SL; emits `decision.v1`.  
  - Order Router (Go/Node): rounding via exchangeInfo filters, idempotent `newClientOrderId`, reconcile fills to orders/positions, publish `order_update.v1`, kill-switch on errors/DD/guards.  
  - Backtester: vectorized + event-driven intrabar fill model, shared SMC/feature libs, fees/slippage, walk-forward.  
  - Paper broker: mimics router, fills from market data with slippage, separate `paper_*` schema.  
  - BFF API/WS + UI: REST/WS for symbols/candles/indicators/zones/signals/decisions/orders; JWT + RBAC; charts/overlays (HH/HL/LH/LL, CHOCH/BOS, OB/FVG; EMA/RSI/MACD toggles), PB panel, alerts, backtest runner, blotter, error console.
- **Data model (TimescaleDB)**:  
  - `candles` PK (venue, symbol, tf, open_time); close_time, OHLCV, trades, taker_buy_vol, quote_vol; hypertable on open_time.  
  - `indicators` PK (venue, symbol, tf, ts): ema20/50/200, rsi14, macd, macd_signal, macd_hist, atr14, bb_upper/bb_lower, vwap.  
  - `swings` PK (venue, symbol, tf, ts, kind HIGH/LOW) with pivot width; `smc_events` PK (venue, symbol, tf, ts, kind CHOCH_UP/DN, BOS_UP/DN) with `ref_ts`; `zones` PK (venue, symbol, tf, kind OB/FVG, created_ts) with side LONG/SHORT, price_lo/hi, expiry_bars.  
  - `signals_raw`, `decisions`, `orders`, `positions` store trading pipeline artifacts (orders include ext ids, entry/stop/tp ladder, status; positions track avg price, qty, unrealized PnL).  
  - Indexes: candles(symbol, tf, open_time DESC); indicators(symbol, tf, ts DESC); smc_events(symbol, tf, ts DESC); orders(symbol, created_ts DESC).
- **Contracts/events**: `candles.v1`, `features.v1`, `smc_events.v1`, `zones.v1`, `signals_raw.v1` (score, TTL, feature flags), `decision.v1` (side, size, entry/SL/TP ladder, risk JSON), `order_update.v1` (ACK/PARTIAL/FILLED/CANCELED/REJECTED with exchange IDs).  
- **Performance budgets**: WS close → features/SMC ≤500 ms p95; decision → router POST ≤200–300 ms p95; REST backfill <5 s; UI candle redraw <150 ms; monolith E2E target ≤700–900 ms p95.  
- **Security & compliance**: split spot vs futures keys; no withdrawal scope; IP allow-lists; rotate keys 60–90 days; secrets via Vault/KMS (never in env files); strict idempotency; audit logs retained 2 years; kill-switch on DD breach/error bursts/WS outage/exchange incidents.  
- **Resilience & observability**: exponential backoff + REST backfill on WS disconnect; retry with jitter for router errors; switch to ReduceOnly exits on repeated errors; clock drift alarms; metrics (latency per stage, queue lag, reconnect count, ACK latency, fill ratio, slippage, DD/exposure gauges), structured JSON logs with trace_id, distributed traces; dashboards for equity/PnL, trade heatmap, alert health, guards timeline.  
- **Environments & deploy**: Dev via Docker Compose (TimescaleDB, Redis, NATS/Kafka, MinIO, services); Staging on K8s with testnet keys + chaos tests; Prod on K8s with HPA/rolling deploy via GitHub Actions; Terraform modules for VPC/K8s/DB/secrets/monitoring.  
- **Build order (6-week plan)**: Wk1-2 ingestors + TSDB + features + UI chart; Wk3 SMC + retest + guards; Wk4 decision + spot router + alerts/PB panel; Wk5 backtester + paper broker + risk caps/reports; Wk6 futures router + funding scheduler + staging soak.  
- **Modular monolith option**: single Python core process (ingest → features → smc → retest → decision → alert) with in-proc async event bus; separate router process; separate BFF/UI process for lowest latency and fast iteration.

## Project Structure & Module Organization
- `app/engine`: Python FastAPI services, trading domain logic, configs in `config.yaml`; tests in `app/engine/tests`.
- `app/router`: Go API gateway/order router (`cmd/server`, `internal/*`) for REST/WS and exchange adapters.
- `app/bff` & `app/ui`: pnpm workspaces for NestJS BFF and Next.js client; shared scripts in root `package.json`.
- `infra`: Docker, Prometheus, Grafana, DB assets referenced by `docker-compose*.yml`.
- Root automation: `Makefile`, `.editorconfig`, `pyproject.toml`, `pnpm-workspace.yaml`.

## Build, Test, and Development Commands
- `make setup` installs Python, Node, and Go dependencies.  
- `make dev` or `make dev-engine|router|bff|ui` starts the stack or a single service.  
- `make build` / `make build-<component>` builds artifacts; `pnpm build:<workspace>` for targeted JS builds.  
- `make test`, `make test-<component>`, `pnpm --filter=<workspace> run test` execute suites.  
- `make lint`, `make lint-fix`, `make format`, `make typecheck` run Ruff/ESLint/Prettier/gofmt/TS checks.  
- `make ci` runs the full gate; `make test-coverage` emits aggregate coverage (htmlcov for Python, workspace folders for Node).  
- Security gates: `make security-check`, `make deps-audit`.

## Coding Style & Naming Conventions
- `.editorconfig` enforces LF endings, 4-space Python, 2-space JS/TS, tab-indented Go—do not override.  
- Python: snake_case filenames; Ruff formatting (88 cols); MyPy typing; prefer `Decimal` for money.  
- Go: run `gofmt` and `golangci-lint`; exported identifiers use PascalCase; package names match dirs; use contexts.  
- TypeScript (NestJS/Next.js): PascalCase components/services, camelCase functions/variables; branded types for IDs; discriminated unions; const assertions.  
- Frontend design: keep existing patterns; when designing new UI, avoid generic purple/white defaults, define CSS variables, use intentional typography/colors, ensure desktop/mobile work, favor meaningful motion.  
- Comments: only for critical caveats; prefer self-explanatory code.

## Testing Guidelines
- Engine: `make test-engine` (pytest, ≥80% coverage); tests under `app/engine/tests` as `test_*.py`.  
- Router: `make test-router` or `go test ./...`; keep `_test.go` next to code in `app/router/internal`.  
- Web: Jest/Testing Library via `pnpm --filter=ui|bff run test`; add `*.spec.ts` beside features.  
- Separate pure logic from DB/integration; prefer integration tests over heavy mocking; use property-based tests when valuable.

## Commit & Pull Request Guidelines
- Conventional Commits required (e.g., `feat(engine): add circuit breaker metrics`, <=100 chars).  
- Rebase onto `main`; run `make ci`; fix lint/test failures before pushing.  
- PRs should summarize scope, reference issues, and include evidence for UI/API updates; document config/infra changes and note follow-ups.

## Environment & Security Tips
- Derive env files from `.env.example`; never commit secrets or local certs.  
- Align local services with `docker-compose.dev.yml`; update `infra/` assets alongside service changes.  
- Prefer Vault/KMS/doppler/1Password CLI for secrets; enforce IP allow-lists and least privilege.

## Remember Shortcuts
- **QNEW**  
  Understand all best practices in this file. Follow architecture in `CONTEXT.md`.
- **QPLAN**  
  Check similar parts of the codebase; ensure the plan is consistent, minimal, and reuses existing code.
- **QCODE**  
  Implement the plan; run tests; run `prettier` on new files; run `turbo typecheck lint`.
- **QCHECK**  
  As a skeptical senior engineer, analyze major changes against: Writing Functions, Writing Tests, Implementation Best Practices.
- **QCHECKF**  
  Analyze each major function change against Writing Functions Best Practices.
- **QCHECKT**  
  Analyze each major test change against Writing Tests Best Practices.
- **QUX**  
  List UX test scenarios to validate the implemented feature (highest priority first).
- **QGIT**  
  Stage all changes, commit, push. Commit message must follow Conventional Commits and never mention OpenAI/Codex.
