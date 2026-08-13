# Coding Log: Seven-Day Soak Remediation

**Created:** 2026-08-13 15:02:07 +07  
**Type:** DREP / planning only  
**Repository:** `/Users/subhajlimanond/dev/online trader`  
**Evidence baseline:** `coding-logs/2026-03-01-10-40-03 Coding Log (risk-clamp-alert-gating-reload).md`, review beginning at line 333  
**Current reviewed branch:** `main` at `ed13749`; the failed soak artifact itself did not record a source SHA or image digest

## Status and scope lock

The system remains **NO-GO** for another seven-day acceptance soak and for live-small activation. The prior run elapsed all 604,800 seconds but failed 20 checks: 19 order-smoke cycles and the monitor window. Passing focused tests do not override the missing failure-path contracts.

This plan remediates execution correctness, durable control, persistence/delivery, reconciliation/readiness, market-data recovery, configuration/authentication, acceptance coverage, forensics, monitoring, and documentation. It preserves the existing SMC/retest decision path and the isolated daily trend-paper path. It does not alter signal definitions, parameters, portfolio construction, or research conclusions.

### Goal

Make order execution and emergency control fail closed, make cross-plane state recoverable and replayable, and make a future seven-day result an acceptance-grade proof of the exact release images, representative trading path, cleanup, alerts, data freshness, reconciliation, and SLOs.

### Non-goals

- No SMC or trend-signal redesign.
- No Python-engine decomposition into more network services.
- No mainnet or testnet mutation during this planning phase.
- No automatic liquidation on every safety halt; protective exits remain unless an explicit flatten operation/policy is invoked.
- No claim that the previous failed-run source SHA, current testnet balances, or current exchange orders are known.
- No compatibility fallback that permits live placement without durable IDs, persistence, control-state access, or a safe reconcile result.

### Success criteria

1. Every non-2xx, circuit-open, timeout, malformed, partial, or semantically inconsistent router result produces zero placement-success side effects.
2. Every placement caller supplies stable client IDs before the first POST; same intent/same payload replays one bracket, while same key/different payload is rejected.
3. New exchange submission requires a durable engine intent, durable router reservation, readable durable execution-control state, a configured exchange client, and safe router readiness.
4. A persisted halt survives restarts and, after acknowledgment, prevents every later exchange submission until an explicitly authorized resume.
5. Emergency `ALL` discovers exchange state, cancels entries, flattens futures and sellable spot holdings, preserves protection until flattening succeeds, and reports all residual dust/open orders truthfully.
6. Every router order transition is stored transactionally in an outbox and consumed idempotently by an engine inbox; network or process failures lose no updates.
7. Kline-only death repairs subscriptions and backfills to parity without duplicate or out-of-order strategy effects.
8. A versioned acceptance profile cannot pass without 604,800 seconds, representative engine-path probes, error-budget compliance, alerts, monitoring, cleanup, provenance, shutdown verification, and final cross-plane convergence.
9. A complete fault-injection → 2-hour → 24-hour → seven-day ladder passes on the exact images proposed for live-small.

## Confirmed-gap disposition matrix

| Confirmed gap | Primary remediation | Acceptance proof |
|---|---|---|
| Router 4xx/5xx treated as success | Slice U1 typed result and semantic validator | Historical 400 regression: no persistence/event/success log |
| BFF-local emergency stop | Slice U4 durable router-owned execution control | Halt race/restart tests and denied post-halt placement |
| BFF retry lacks stable IDs | Slice U2 mandatory idempotency | Lost-response replay creates one exchange entry |
| Soak brittle and shallow | Slice U11 versioned profiles and error budgets | Required deep probes and duration/sample floors |
| Direct smoke bypasses representative path | Slice U11 engine acceptance probe | Intent → router → outbox/inbox → BFF → cleanup trace |
| Filled smoke leaves assets/orders | Slices U5/U11 cleanup state machine | Zero above-dust asset delta and zero owned open orders |
| Readiness green after unsafe reconcile | Slice U7 component readiness | 503 until errors/unrepaired/stale claims clear |
| Reservation and engine persistence fail open | Slice U3 durable intent/reservation | DB faults cause zero new exchange calls |
| Order-update delivery best effort | Slice U6 outbox/inbox | Engine outage and replay converge without loss |
| Emergency close cannot flatten spot | Slice U5 exchange-authoritative cleanup | Seeded unknown spot asset is sold or reported as dust |
| Risk config semantics/Compose drift | Slice U8 typed config | Rendered Compose and range-validation gates |
| 167 alert 401s / 366 snapshot warnings | Slice U9 token contract and canaries | BFF snapshot and Telegram API acknowledgments |
| Kline-only death not repaired | Slice U10 subscription-specific recovery | Ticker-live/kline-dead fault returns to parity |
| Failed volumes deleted | Slice U12 retention policy | Failure/interruption preserves volumes and recovery commands |
| Shutdown excluded from verdict | Slice U12 lifecycle ordering | Shutdown failure changes final status |
| Seven-day logs buffered in memory | Slice U12 streaming/rotation | Bounded-memory long-log test |
| Monitoring/SLO stack excluded | Slice U13 soak Compose and assertions | Prometheus targets/metrics plus SLO evaluation |
| BFF liveness/readiness shallow | Slices U7/U13 | Real DB/Redis/router-ready checks |
| WS handler completion can reorder | Slice U10 keyed queues | Per-symbol/timeframe ordering test |
| REST seed failure suppresses retry | Slice U10 success-based cooldown | Prompt retry after transient failure |
| Permissive WS CORS | Slice U13 shared allowlist | Cross-origin rejection E2E |
| Alert timestamps lack timezone | Slice U13 migration 036 | Known UTC conversion test |
| Contract/config/documentation drift | Slice U13 generated contracts/runbooks | Contract parity and doc lint/checklist |
| UI availability unqualified | Slices U11/U13 operator E2E | Halt/readiness/canary/residual UI assertions |
| Artifact lacks SHA/images/config | Slice U12 provenance manifest | Exact SHA, digest, migration and config hashes |

# Plan Draft A — Safety-first incremental hardening

## A1. Overview

Draft A lands narrow cross-plane changes in strict dependency order. It first removes false success and duplicate-placement paths, then establishes durable execution state/control/delivery, and only afterward rebuilds the acceptance harness and runs qualification. This minimizes unsafe intermediate states and keeps the current service boundaries.

## A2. Files to change

### Engine

- `app/engine/adapters/router_client/http_client.py` — typed transport/HTTP/protocol results.
- `app/engine/execution/router_execution_subscriber.py` — fail-closed semantic validation, prepared intents, halt/readiness gate, success-side-effect ordering.
- `app/engine/execution/execution_intent_repository.py` — new execution-intent persistence component.
- `app/engine/execution/execution_safety_coordinator.py` — new safety-halt coordinator.
- `app/engine/execution/order_update_inbox.py` — new idempotent order-update consumer state.
- `app/engine/adapters/db/timescale_adapter.py` — intent/control/inbox adapter methods.
- `app/engine/main.py` — component wiring, internal update acknowledgment, deep readiness/effective config.
- `app/engine/adapters/alert/bff_api_client.py` — canonical token/route and typed delivery result.
- `app/engine/ingest/binance_ws.py` — kline-specific repair and keyed ordering.
- `app/engine/ingest/live_rest_fallback.py` — success-based seed cooldown and parity backfill.
- `app/engine/monitoring/pipeline_health_service.py` — repair-stage telemetry and safety halt trigger.

### Router

- `app/router/internal/orders/types.go` — versioned placement/update/control/emergency contracts.
- `app/router/internal/orders/manager.go` — mandatory IDs/store/client/control checks and spot flattening.
- `app/router/internal/orders/events.go` — outbox dispatcher transport; retire one-shot authority.
- `app/router/internal/orders/startup_reconciler.go` — readiness-blocking summary and outbox-aware state changes.
- `app/router/internal/orders/outbox_dispatcher.go` — new durable retry dispatcher.
- `app/router/internal/storage/bracket_repo.go` — request hash and transactional state/outbox writes.
- `app/router/internal/storage/execution_control_repo.go` — new durable halt/resume and lock protocol.
- `app/router/internal/storage/order_update_outbox_repo.go` — new outbox repository.
- `app/router/internal/api/handlers.go` — typed HTTP status mapping and new control/emergency responses.
- `app/router/internal/api/router.go` — register execution-control and deep-readiness routes if this is the existing route owner.
- `app/router/internal/config/config.go` — active-execution/client/persistence validation.
- `app/router/cmd/router/main.go` — repositories, dispatcher, readiness and graceful-shutdown wiring.

### BFF/UI

- `app/bff/src/router-client/router-client.service.ts` — stable placement IDs, control APIs and structured readiness.
- `app/bff/src/trading/trading.controller.ts` — REST idempotency-header contract.
- `app/bff/src/trading/trading.gateway.ts` — WS idempotency-field contract and shared CORS policy.
- `app/bff/src/trading/commands/handlers/place-order.handler.ts` — pass the locked request identity.
- `app/bff/src/trading/trading.service.ts` — durable manual-order identity; deprecate local flag as kill switch.
- `app/bff/src/trading/emergency-close.service.ts` — halt-first exchange-authoritative workflow.
- `app/bff/src/trading/dto/emergency-close.dto.ts` — truthful halt/residual fields.
- `app/bff/src/auth/guards/internal-api.guard.ts` — fail-start token configuration and constant-time comparison.
- `app/bff/src/alerts/internal-alerts.controller.ts` — canonical canary/alert route.
- `app/bff/src/health/health.controller.ts` — real DB, Redis and router readiness.
- `app/bff/src/alerts/alerts.gateway.ts`, `app/bff/src/market-data/market-data.gateway.ts`, `app/bff/src/websockets/websocket.gateway.ts` — shared explicit origin allowlist.
- Existing UI status components discovered during implementation — show halt generation, reconcile state, delivery lag, residuals and canary status.

### Schema, acceptance and operations

- `db/migrations/034_execution_safety.sql` — bracket request identity, execution intents and execution control.
- `db/migrations/035_order_update_delivery.sql` — router outbox and engine inbox.
- `db/migrations/036_bff_alert_timestamptz.sql` — explicit UTC conversion.
- `scripts/testnet_soak_manifest.py` — versioned fixed qualification profiles.
- `scripts/run_testnet_soak.py` — representative probes, budgets, cleanup, provenance and lifecycle.
- `tests/test_run_testnet_soak.py` — harness contract tests.
- `docker-compose.soak.yml` — no-watch acceptance services, monitoring and bounded logs.
- `.env.example`, `docker-compose.dev.yml`, `docker-compose.yml` — typed configuration and canonical tokens.
- `contracts/jsonschema/*` and generated bindings — update only the existing owners for placement, update, readiness, control and emergency contracts.
- `docs/runbooks/testnet-acceptance.md` and `docs/runbooks/execution-emergency.md` — qualification and halt/flatten/rollback procedures.
- `CONTEXT.md`, `README.md`, `PROJECT_PLAN.md` — actual routes, router responsibility and verified-vs-intended deployment wording.

Applied migrations 030–033 are never edited.

## A3. Implementation steps

Every slice follows the same mandatory TDD loop:

1. Add/stub the contract test.
2. Run it and confirm RED for the intended missing behavior.
3. Implement the smallest production change.
4. Refactor only where needed to make state boundaries explicit.
5. Run scoped formatter, lint/typecheck and tests before advancing.

### A-1: typed router placement result

- Add `RouterTransportError`, `RouterHTTPError`, `RouterCircuitOpenError`, `RouterProtocolError`, and immutable `BracketPlacementResult` in `http_client.py`.
- `_make_request()` raises on circuit-open and every non-2xx; it accepts valid 2xx, bounds/redacts bodies, and never internally retries a bracket POST.
- `place_bracket_order()` parses required fields and returns the typed result.
- Replace `_check_router_response()` with `validate_bracket_placement()` in the subscriber. Require bracket ID, exact submitted client IDs, symbol/side, expected TP count, no partial failure/errors, and correct deferred-leg state.
- `_place_bracket_with_retries()` owns ambiguity-safe retry: transport ambiguity, retryable 5xx and bounded 429 only. Ordinary 4xx, protocol errors and partial placement do not retry.
- No order persistence, snapshot, `OrderPlacedEvent`, cooldown consumption or success log may occur before typed validation.

### A-2: mandatory caller-owned idempotency

- Make `client_order_ids` and `idempotency_key` mandatory in the active `/place_bracket` contract.
- Retain `_build_client_order_ids()` for engine decisions. REST BFF requests require `X-Idempotency-Key`; WebSocket requests require `idempotencyKey`. Derive Binance-safe main/TP/SL IDs once and reuse the exact body across retries.
- The soak uses `run_id + cycle_id` to derive stable IDs.
- Router `validateBracketRequest()` rejects missing/invalid ID sets before client selection.
- `BracketRepo.Reserve()` stores `idempotency_key` and a canonical request hash. Equal replay returns the original state; divergent replay returns 409 without exchange access.
- Roll out `ROUTER_REQUIRE_CLIENT_ORDER_IDS` as warning-only for one compatibility deployment, update every repository caller, enforce in testnet, and remove the false mode before live-small.

### A-3: durable execution intent and fail-closed reservation

- Add `execution_intents` with `PREPARED`, `SUBMITTING`, `ACKNOWLEDGED`, `REJECTED`, and `AMBIGUOUS` states.
- `RouterExecutionSubscriber._execute_decision()` commits the normalized payload/hash before the router call, resumes identical prior intents, and rejects divergent ones.
- Router active execution requires a DB-backed `BracketStore`; reservation failure produces 503 and zero Binance calls. Remove the in-memory-only/synchronous-leg fallback.
- ACK plus engine order projections must commit before success events/snapshots. ACK persistence failure is `AMBIGUOUS`, blocks a fresh intent, and is repairable only through same-key replay/reconciliation.

### A-4: durable authoritative execution control

- Add `execution_control(scope,state,generation,reason,requested_by,idempotency_key,timestamps)`.
- Add authenticated router endpoints `POST /internal/execution-control/halt`, `POST /internal/execution-control/resume`, and `GET /internal/execution-control`.
- Placement takes a shared PostgreSQL advisory lock, reads the control row and stays inside the lock through its first exchange submission and durable result. Halt takes the exclusive lock, drains in-flight submissions, commits HALTED, then acknowledges.
- DB/lock/control lookup failure blocks placement.
- BFF emergency stop reports success only after halt acknowledgment and confirming GET. `TradingService.autoTrading` remains UI preference only and is renamed/deprecated accordingly.
- Resume requires safe readiness, reconciliation, outbox and explicit operator authorization; deployments start halted.

### A-5: exchange-authoritative emergency cleanup

- Change router emergency scope `ALL` to enumerate exchange open orders, futures positions and spot balances; BFF in-memory symbols are optional filters only.
- Sequence: halt → cancel entries → flatten exposure → cancel orphaned exits → exchange requery → residual verdict.
- Implement spot base-asset discovery through exchange metadata, quantity/filter rounding and market sell. Quote/protected assets are excluded. Below-minimum balances are returned as dust.
- Add `EMERGENCY_SPOT_QUOTE_ASSETS`, `EMERGENCY_PROTECTED_ASSETS`, `EMERGENCY_DUST_MAX_USDT`, and `EMERGENCY_FILL_TIMEOUT_SECONDS` with validated acceptance values.
- A partial failure remains halted. `fully_flattened=true` is impossible with above-threshold exposure or targeted open orders.

### A-6: transactional outbox and idempotent inbox

- Add `router_order_update_outbox` with event UUID, aggregate/sequence, versioned payload, retry state, next attempt and delivery timestamps.
- Add `engine_order_update_inbox` keyed by event UUID with payload hash and processing state.
- `BracketRepo` methods update bracket/leg state and enqueue the corresponding event in one transaction.
- `OutboxDispatcher.Run()` claims with `FOR UPDATE SKIP LOCKED`, preserves per-aggregate sequence, retries with jitter and stops gracefully. Dead letters degrade readiness.
- Engine `/internal/order_update` authenticates, validates, inserts inbox, treats same-hash duplicate as success, conflicting hash as 409/critical, prevents terminal-state regression and parks sequence gaps.
- Rollout order: engine inbox → router shadow dual delivery → count/latency comparison → outbox authoritative → direct emitter disabled. Acceptance requires outbox on and direct emit off.

### A-7: strict readiness and reconciliation

- Replace unconditional deferred `SetReady(true)` with readiness components: DB/migrations, configured clients, readable execution control, completed safe reconciliation, and healthy outbox.
- Reconciliation is unsafe when `errors`, `unrepaired_legs`, or unresolved stale reservations are nonzero. Router stays live but `/readyz` returns 503 and placement is rejected.
- Add `ROUTER_ACTIVE_EXECUTION`. Active mode requires explicit `spot`, `futures`, or `spot,futures`, matching clients/credentials, DB and internal auth. `paper`, empty or nil clients cannot be trading-ready.
- BFF readiness calls router `/readyz` and performs real DB/Redis checks. Soak continuously evaluates structured readiness, not just liveness.

### A-8: typed risk/configuration and automatic safety halt

- Introduce one typed engine config schema: `MAX_DAILY_LOSS_RATIO`, `MAX_DRAWDOWN_RATIO`, `MAX_POSITION_NOTIONAL_USD`, `MAX_LEVERAGE`, error-burst count/window and `AUTO_HALT_FLATTEN`.
- Values use documented units and validated ranges. Ambiguous `MAX_DAILY_LOSS=1000` is rejected unless a temporary explicit migration flag is present; never silently reinterpret it.
- Compose passes every safety setting explicitly. Startup exposes a redacted effective-config document containing schema version, values/units, setting source and token fingerprints.
- Drawdown, error burst and prolonged market-data failure request `HALTED_SAFETY`, cancel unfilled entries and preserve exits by default.

### A-9: internal authentication and real canaries

- Canonicalize `ROUTER_API_KEY`, `ENGINE_INTERNAL_API_TOKEN`, and `BFF_INTERNAL_API_TOKEN`. Allow `INTERNAL_ALERTS_TOKEN` only as a one-release alias with matching fingerprint and warning.
- `InternalApiGuard` uses constant-time comparison and application startup fails if required internal tokens are blank.
- Canonicalize engine → BFF alert route to `POST /api/internal/alerts/signal`; retain one guarded compatibility alias if current external callers require it.
- Acceptance canary sends a unique signal through production alert code, observes BFF acceptance, completed/retrievable snapshot and Telegram API `message_id`. Human receipt is not claimed.

### A-10: kline-specific self-repair and ordering

- Watch generic message freshness and kline freshness independently.
- On kline-only staleness: replay subscriptions using monotonic request IDs, await correlated ACK, require time-to-first-kline, reconnect if repair fails, then backfill every fully closed missing candle to parity.
- Shard dispatch by `symbol/timeframe` so each key is FIFO while different keys remain parallel.
- Deduplicate WS and REST candles by venue/symbol/timeframe/open-time before stateful consumers.
- REST fallback records cooldown/watermark only after successful fetch/publish and retries transient failures below the normal seed interval.
- Prolonged repair failure invokes safety halt.

### A-11: acceptance harness redesign

- Add immutable `fault-injection`, `2h`, `24h`, and `seven-day` profiles. `seven-day` enforces at least 604,800 seconds, 168 hourly representative cycles and every mandatory check; CLI may lengthen but not shorten it.
- Add a testnet-only authenticated engine acceptance-probe endpoint enabled by `ACCEPTANCE_PROBES_ENABLED=true` and rejected in mainnet modes. It injects a tagged decision after signal generation but before the normal risk/readiness/intent/subscriber path; it may not bypass those stages.
- The representative probe verifies intent, durable reservation, deferred legs, outbox/inbox, BFF projection, cancel/flatten and convergence. Direct router smoke remains a secondary API-boundary test only.
- Track each cycle as `PREPARED → PLACED → CANCELING → VERIFYING → CLEAN|QUARANTINED`. An unresolved ambiguous placement or cleanup quarantines and fails immediately.
- Use error budgets for transient probes while retaining zero tolerance for false success, duplicates, unprotected exposure, unsafe readiness, unresolved ambiguity, lost updates or residual above threshold.

### A-12: forensics and lifecycle-correct verdict

- Stream service logs directly to files; use Docker rotation `max-size:50m`, `max-file:10`; never capture a seven-day log in process memory.
- Capture Git SHA/branch/dirty diff hash, image IDs/digests, resolved Compose hash, migration versions/checksums, dependency lock hashes, redacted config/token fingerprints, clock data and initial/final exchange/DB/reconcile/outbox/inbox snapshots.
- Final verdict occurs after final snapshots, artifact hashing, shutdown and shutdown verification. Shutdown failure changes status.
- Failure/interruption retains volumes. `--destroy-volumes-on-pass` is explicit and runs only after artifacts verify. Acceptance profiles do not permit `--keep-running`.

### A-13: monitoring/security/contracts/docs

- Add `docker-compose.soak.yml` with reload/watch disabled, Prometheus/Grafana enabled, resource limits and bounded logs.
- Require scrape target health and metrics for placement latency/outcome, reconnect/repair, readiness, reconcile, outbox/inbox, alerts, resource use, restarts, risk and residual exposure.
- Apply the HTTP origin allowlist to all four credentialed WebSocket gateways and add negative-origin E2E tests.
- Convert migration-033 alert timestamps to `TIMESTAMPTZ` using explicit `AT TIME ZONE 'UTC'`.
- Update versioned JSON schemas/generated bindings and remove stale `/api/v1/order`, router/load-balancer, and unverified K8s/Vault/HPA claims or clearly label them as targets.
- Add operator UI/E2E checks for readiness, halt generation, delivery backlog, alert canary and emergency residuals.

### A-14: qualification ladder

- Focused and full CI on the exact release commit.
- Complete fault-injection matrix.
- Clean 2-hour testnet qualification.
- Clean 24-hour qualification with controlled engine/router/BFF restarts.
- Fresh uninterrupted seven-day acceptance on exact release images.
- Each failure restarts that stage; elapsed time is never combined.

## A4. Test coverage

### Engine

- `test_http_400_raises_router_http_error` — maps non-2xx to typed failure.
- `test_circuit_open_never_returns_success_payload` — circuit state cannot masquerade as result.
- `test_malformed_2xx_raises_protocol_error` — requires valid placement fields.
- `test_router_failure_has_no_success_side_effects` — blocks DB snapshot event and log.
- `test_retry_reuses_exact_client_ids` — retries only identical logical intent.
- `test_prepare_failure_prevents_router_submission` — fails closed before exchange boundary.
- `test_ack_persistence_failure_marks_ambiguous` — never emits placement success.
- `test_duplicate_order_update_is_effectively_once` — inbox suppresses duplicate effects.
- `test_conflicting_duplicate_order_update_returns_conflict` — detects event corruption.
- `test_sequence_gap_parks_later_update` — preserves aggregate state order.
- `test_kline_stale_with_live_tickers_repairs_subscription` — repairs stream-specific failure.
- `test_rest_seed_failure_retries_before_cooldown` — cooldown begins after success.
- `test_same_symbol_candles_complete_in_order` — keyed workers preserve state order.

### Router

- `TestPlaceBracketRequiresClientOrderIDs` — rejects before exchange call.
- `TestLostResponseReplayPlacesEntryOnce` — same request adopts one bracket.
- `TestIdempotencyKeyPayloadConflict` — divergent reuse returns 409.
- `TestReservationFailureDoesNotCallExchange` — durable store is mandatory.
- `TestPlacementWhileHaltedDoesNotCallExchange` — final control gate blocks submission.
- `TestHaltRacingPlacementDrainsBeforeAck` — acknowledgment defines safe boundary.
- `TestHaltSurvivesRouterRestart` — control state is durable.
- `TestEmergencyAllFlattensUnknownSpotBalance` — exchange discovery beats BFF cache.
- `TestEmergencyResidualAboveThresholdFails` — response remains truthful.
- `TestStateAndOutboxCommitAtomically` — no update without replay event.
- `TestOutboxRetriesAfterEngineOutage` — eventual delivery survives downtime.
- `TestUnsafeReconcileKeepsReadinessFalse` — no deferred fail-open ready state.
- `TestActiveExecutionRejectsMissingClient` — healthy-but-nontrading config blocked.

### BFF/UI

- `placeOrder reuses stable body across retries` — eliminates ambiguous duplicate POST.
- `placeOrder requires idempotency identity` — REST and WS contracts reject blanks.
- `emergency close halts before canceling` — authoritative stop precedes cleanup.
- `emergency close stays halted after partial failure` — no unsafe auto-resume.
- `local autoTrading flag is not stop acknowledgment` — removes false success.
- `readiness fails when router unready or database down` — checks real dependencies.
- `internal token mismatch rejects canary` — catches historical 401 class.
- `credentialed websocket rejects unlisted origin` — shared origin policy enforced.
- UI E2E: `operator sees halt generation and residuals` — exposes safety state.

### Soak/operations

- `test_seven_day_profile_rejects_short_duration` — acceptance duration is immutable.
- `test_seven_day_profile_requires_every_probe` — skipped mandatory checks fail.
- `test_transient_probe_uses_error_budget` — one blip is not permanent failure.
- `test_false_success_is_zero_tolerance` — safety violation fails immediately.
- `test_representative_probe_cannot_be_replaced_by_direct_smoke` — validates real path.
- `test_filled_probe_flattens_or_quarantines` — never leaks untracked assets.
- `test_shutdown_failure_changes_final_verdict` — lifecycle included in outcome.
- `test_failed_run_retains_volumes` — preserves forensic state.
- `test_logs_stream_without_unbounded_capture` — bounded memory behavior.
- `test_provenance_manifest_contains_release_identity` — exact artifact attribution.
- `test_prometheus_targets_and_required_metrics_exist` — monitoring is mandatory.

## A5. Decision completeness

### Public interfaces

- `POST/GET /internal/execution-control/*` are authenticated internal APIs.
- `/place_bracket` requires stable IDs/idempotency identity in active mode and returns versioned typed placement fields.
- `/internal/order_update` requires `event_id`, `sequence`, `event_version` and idempotent acknowledgment.
- `/readyz` becomes component-structured and returns 503 when execution-unsafe.
- Emergency responses include starting/final exchange state, residuals, `fully_flattened`, control generation and per-step failures.
- REST manual order requires `X-Idempotency-Key`; WS manual order requires `idempotencyKey`.
- Migrations 034–036 are additive; applied 030–033 remain immutable.

### Top failure modes and policy

| Failure | Policy |
|---|---|
| Router transport/HTTP/protocol error | Fail closed; same-key retry only when ambiguity-safe |
| Engine intent DB unavailable | Fail closed before router call |
| Router reservation/control DB unavailable | Fail closed before exchange call |
| Exchange accepted, engine ACK persistence unavailable | Ambiguous, no success event, same-key recovery only |
| Halt service unavailable | Local engine latch blocks; placement router gate remains authoritative |
| Emergency partial failure | Remain halted; report residuals; no auto-resume |
| Order-update receiver unavailable | Outbox retry; readiness degrades on age/dead-letter |
| Reconciliation error | Live but not ready; no new placement |
| Kline-only outage | Repair, reconnect, backfill; halt on prolonged non-parity |
| Alert canary failure | Acceptance failure; not a trading-success warning |
| Transient liveness miss | Count against budget; fail on duration/availability threshold |
| Unresolved order/exposure ambiguity | Immediate quarantine and acceptance failure |

### Rollout and backout

- Deploy idempotent inbox before outbox dual delivery.
- Deploy ID warning telemetry before enforcing IDs; live-small requires enforcement.
- Deploy control state with router starting halted. Any rollback leaves it halted.
- Additive migrations are retained on rollback; disable new readers/dispatchers rather than dropping durable rows.
- Outbox shadow mode compares direct/outbox event count and latency; authority changes only after parity.
- Configuration aliases last one release and are forbidden by live-small profile.
- No re-soak until the complete fault-injection stage passes.

### Acceptance checks

- Python: scoped unit/integration suites, then `make test-engine`, Ruff, MyPy.
- Go: scoped packages, then `go test ./...`, `gofmt` check and configured linter.
- TypeScript: scoped Jest, then repository Prettier, `turbo typecheck lint`, BFF/UI tests.
- Migration: clean apply, upgrade from 033 fixture, schema/constraint inspection and known-UTC timestamp check.
- Compose: render dev/base/soak profiles and validate required env pass-through without secrets.
- Faults: run every matrix item in A-11 with durable evidence.
- Qualification: 2h → 24h → 604800s; exact images and final convergence required.

## A6. Dependencies

- A dedicated Binance testnet account or approved isolated symbol/account baseline.
- PostgreSQL advisory locks and migrations on the shared Timescale/Postgres database.
- Telegram bot/chat authorized for API-delivery canaries.
- Prometheus/Grafana images available before qualification; cache them if offline reproducibility is required.
- Operator authorization for account baseline cleanup and later live-small resume; neither is implied by this plan.

## A7. Validation

Validation proceeds at contract, integration, chaos, short qualification and full acceptance levels. Test doubles establish deterministic RED/GREEN contracts, but release qualification uses real containers, the actual DB, Binance testnet, internal HTTP boundaries, Telegram API and operator UI. Every stage stores checksummed artifacts.

## A8. Wiring verification

| Component | Entry point | Registration location | Schema/table |
|---|---|---|---|
| Typed router result | `RouterHTTPClient.place_bracket_order()` | subscriber client construction in `app/engine/main.py` | N/A |
| Execution intent repository | `RouterExecutionSubscriber._execute_decision()` | execution subscriber construction in `app/engine/main.py` | `execution_intents` |
| Required idempotency | Go `Manager.PlaceBracketOrder()` | `/place_bracket` handler in `internal/api/handlers.go` | `brackets.idempotency_key`, `brackets.request_hash` |
| Execution control | placement final gate and BFF emergency | router routes/main wiring; engine readiness callable | `execution_control` |
| Spot/futures emergency | `Manager.CancelOpenOrders()` / `ClosePositions()` | existing emergency handlers and BFF service | exchange state; emergency audit table remains `emergency_close_operations` |
| Router outbox | bracket/leg repository mutations | `cmd/router/main.go` dispatcher lifecycle | `router_order_update_outbox` |
| Engine inbox | `/internal/order_update` | route/service wiring in `app/engine/main.py` | `engine_order_update_inbox` |
| Strict readiness | `/readyz` | router handlers/main; BFF health; soak monitor | reconcile/outbox/control state |
| Typed risk config | engine startup and pretrade risk | `app/engine/main.py`; Compose env | N/A |
| Alert canary | engine BFF client and alert subscriber | BFF internal controller; soak manifest | existing alert/snapshot/audit tables |
| Kline repair | WS watchdog | ingest startup in `app/engine/main.py` | `candles` watermark/dedup key |
| Acceptance probe | authenticated testnet-only engine endpoint | engine route registration under flag | intents, brackets, orders, outbox/inbox |
| Soak manifest | soak CLI/profile loader | `scripts/run_testnet_soak.py` | artifact JSON schema |
| Monitoring | Prometheus scrape/soak evaluator | `docker-compose.soak.yml` | Prometheus TSDB |
| Alert timezone migration | BFF alert entities/queries | migration runner | migration-033 alert tables |

### Cross-language schema verification before migration RED

Before writing migration 034, exact-search Python, Go and TypeScript SQL/repository references for `brackets`, `bracket_legs`, `orders`, `trading_decisions`, and alert tables. Record the current columns and constraints in the implementation Coding Log. Confirm that root migration 033 is latest at implementation time; if another migration lands first, renumber 034–036 without changing dependencies.

# Plan Draft B — Acceptance-oracle-first with bounded tactical fixes

## B1. Overview

Draft B first lands the three critical tactical contracts and a substantially deeper diagnostic harness, then uses short fault runs to reveal where durable state is most valuable before adding outbox/control tables. Its advantage is earlier operational feedback and fewer simultaneous schema changes; its disadvantage is that the harness initially observes a system that still contains known durability gaps and therefore cannot qualify it.

## B2. Files to change

Draft B changes the same eventual file set as Draft A, but its first milestone is limited to:

- `http_client.py`, `router_execution_subscriber.py` and their unit/integration tests.
- BFF `router-client.service.ts`, manual order route/gateway/service and tests.
- Go `types.go`, `manager.go`, `handlers.go`, bracket repository and idempotency tests.
- BFF emergency service/DTO plus a temporary truthful `execution_stop_supported=false` response until durable halt lands.
- `scripts/run_testnet_soak.py`, a new manifest, soak tests, `docker-compose.soak.yml`, log rotation, provenance and monitoring.

The second milestone adds migrations 034–036, intent/control/outbox/inbox, readiness, emergency flattening, ingest recovery, auth/config and final acceptance behavior.

## B3. Implementation steps

The same test-first RED → minimal GREEN → refactor → scoped-gate loop applies to every step.

1. Fix typed router result handling and prove the historical 400 cannot produce success.
2. Require stable IDs for engine/BFF/soak and enable router warning-only telemetry.
3. Remove the false BFF emergency-stop success immediately: until durable halt exists, a stop request returns a hard failure stating execution halt is unavailable. This is truthful but operationally restrictive.
4. Add a diagnostic-only acceptance profile with streamed logs, provenance, deep read-only health and exchange/DB snapshots. It must always label itself `diagnostic`, never `acceptance`.
5. Run fault injection against typed response/idempotency and use the retained evidence to validate exact persistence/delivery failure modes.
6. Add durable execution intent/control/reservation, emergency flattening, outbox/inbox and strict readiness.
7. Add typed configuration/auth canaries and kline-specific recovery.
8. Promote the diagnostic harness to qualification profiles only after all lower layers are fail closed.
9. Run the same 2h → 24h → seven-day ladder.

## B4. Test coverage

Draft B uses all Draft A tests. Its distinguishing tests are:

- `test_emergency_stop_reports_unsupported_before_durable_control` — prevents local-memory false success.
- `test_diagnostic_profile_can_never_report_acceptance_pass` — separates early evidence from qualification.
- `test_diagnostic_profile_is_read_only_without_order_probe` — supports safe discovery.
- `test_acceptance_profile_requires_all_durable_features` — promotion guard.

## B5. Decision completeness

### Goal/non-goals/success

Goal and final success criteria are identical to Draft A. The temporary diagnostic milestone is expressly non-qualifying. No live-small or seven-day retry is permitted between milestones.

### Public interfaces

- Immediate tactical release makes missing idempotency a warning before enforcement.
- Emergency API truthfully returns unsupported/failed for stop requests until durable router control exists.
- Diagnostic profile is a new CLI surface that cannot be relabeled acceptance.
- Final interfaces/migrations match Draft A.

### Failure policy

All placement failures fail closed immediately. Known persistence/delivery/readiness gaps remain explicit hard blockers during the diagnostic milestone; they are never accepted by error budget.

### Rollout/acceptance

The tactical release may run short, non-trading or tightly controlled diagnostics only. It may not run a seven-day acceptance or live-small. Final rollout/backout and qualification match Draft A.

## B6. Dependencies

Same as Draft A, with an additional requirement that any early diagnostic exchange interaction receive separate user authorization because planning itself does not grant it.

## B7. Validation

Validate the tactical milestone with focused tests and no acceptance claim. Validate the durable milestone and final system through the full Draft A ladder.

## B8. Wiring verification

The final wiring table is identical to Draft A. During the tactical milestone, only typed results, required caller identity, truthful emergency response, and diagnostic manifest are wired; intent/control/outbox/inbox rows are explicitly reported absent and keep readiness non-qualifying.

## B9. Trade-offs

### Strengths

- Faster closure of the confirmed phantom-success and duplicate-retry bugs.
- Earlier high-quality retained evidence from short diagnostics.
- Smaller first migration blast radius.

### Weaknesses

- Creates an intermediate version that is safer but still knowingly non-durable.
- Risks organizational pressure to mistake a diagnostic pass for readiness.
- Duplicates harness work because some probes cannot become authoritative until intent/outbox/control exist.
- Delays a usable emergency stop by first exposing it as unsupported.

# Comparative analysis and synthesis

Draft A better respects the rule that no higher-layer acceptance claim should depend on a fail-open lower layer. Its principal cost is a larger dependency chain and multiple schema-backed components before useful qualification. Draft B provides earlier truthful diagnostics and tactical protection, but its intermediate state cannot satisfy the requested end goal and creates label/rollout risk.

Both plans conform to the repository’s TDD, type, test-placement, DB-migration and cross-language wiring rules. Both preserve current service boundaries and signals. Draft A is selected as the implementation baseline, with two Draft B ideas retained:

1. Land the typed-result and stable-ID changes as independently reviewable first PRs.
2. Add an explicitly non-qualifying diagnostic profile early for fault evidence, while making it impossible to emit an acceptance PASS.

# Unified Detailed Remediation Execution Plan

## U1. Overview

The unified DREP is a 14-slice, dependency-ordered program. Immediate correctness blockers land first; durable control, persistence and delivery follow; then readiness, configuration, authentication and ingest recovery; only then does the representative acceptance harness become eligible to qualify the system. The implementation owner may split a slice into smaller PRs, but may not reorder safety dependencies or turn compatibility modes into live fallbacks.

## U2. Files to change

The authoritative file list is Draft A §A2. Before each slice, refresh exact current owners with RepoPrompt and exact identifier search; modify existing route/controller/repository owners rather than adding parallel paths. New files are limited to the focused repositories/dispatcher/manifest/runbooks listed there. Migration numbers 034–036 are provisional until the current latest migration is rechecked immediately before RED.

## U3. Dependency-ordered slices

### U1 — Placement truth

**Invariant:** only a semantically validated 2xx placement can advance success state.  
**RED:** historical HTTP 400 payload currently reaches persistence/snapshot/event.  
**GREEN:** typed errors/result plus subscriber validator; one retry owner; no success effects on any failure.  
**Done:** unit matrix covers 4xx/5xx/429/timeout/circuit/malformed/partial/ID mismatch and integration log contains no false success.

### U2 — End-to-end idempotency

**Invariant:** every caller creates stable IDs before first POST; replay is one logical bracket.  
**RED:** BFF retry and smoke omit IDs; same-key divergence is not rejected durably.  
**GREEN:** REST/WS/engine/soak identity contract, router validation, canonical hash and 409 conflict.  
**Done:** lost-response/concurrency tests show exactly one exchange entry and all repository callers pass enforcement.

### U3 — Durable intent and reservation

**Invariant:** no execution without engine PREPARED intent and router durable reservation.  
**RED:** DB failures currently continue or are suppressed.  
**GREEN:** migration 034, intent state machine, mandatory store and ACK-before-success ordering.  
**Done:** engine/router DB fault tests produce zero fresh exchange calls; ambiguous accepted state is replayable but not reported successful.

### U4 — Durable halt

**Invariant:** acknowledged halt drains prior submitters and fences later submitters across restarts.  
**RED:** BFF-local flag does not affect execution.  
**GREEN:** execution-control table/API, shared/exclusive advisory-lock protocol, engine local latch plus router final gate.  
**Done:** race, outage and restart tests prove no post-ack exchange POST; resume fails unless readiness safe.

### U5 — Emergency exposure control

**Invariant:** success is based on final exchange state, not cached symbols or attempted calls.  
**RED:** ALL omits spot and unknown exchange orders.  
**GREEN:** exchange enumeration, entry cancellation, protected flatten, orphan cleanup, requery and residual model.  
**Done:** seeded unknown orders/assets converge to clean or explicit below-threshold dust; partials remain halted.

### U6 — Durable order-update delivery

**Invariant:** each exchange-acknowledged state transition is transactionally replayable and effectively-once downstream.  
**RED:** one-shot HTTP loss is unrecoverable.  
**GREEN:** migration 035, state-plus-outbox transaction, retry dispatcher, authenticated idempotent/ordered inbox, shadow rollout.  
**Done:** engine outage/router restart loses zero events; pending drains; projections converge; dead letters block readiness.

### U7 — Execution readiness

**Invariant:** readiness means safe admission, not merely completed startup.  
**RED:** reconcile errors/unrepaired legs still set ready; nil client may remain healthy.  
**GREEN:** component readiness and strict `ROUTER_ACTIVE_EXECUTION`; BFF/soak consume `/readyz`.  
**Done:** every unsafe component yields 503 and zero placements; background recovery can restore readiness only after safe evidence.

### U8 — Typed risk and configuration

**Invariant:** one unit/range definition reaches code, Compose, docs and effective runtime.  
**RED:** ratio code accepts conflicting sample/env semantics and Compose omissions.  
**GREEN:** typed schema, explicit propagation, redacted effective config and automatic safety-halt wiring.  
**Done:** bad ranges/legacy ambiguity fail startup; rendered profiles match; drawdown/error/WS faults halt safely.

### U9 — Authenticated operator evidence

**Invariant:** internal token compatibility and actual delivery are proven by round trip.  
**RED:** presence-only preflight misses historical 401s.  
**GREEN:** canonical token names, constant-time guards, fail-start blanks, snapshot/Telegram canary.  
**Done:** zero 401s in qualification; unique canary has BFF/snapshot/Telegram acknowledgments within SLO.

### U10 — Market-data self-healing

**Invariant:** kline freshness is independently repaired and stateful consumers see ordered, deduplicated closed bars.  
**RED:** ticker traffic masks kline death; fallback failure triggers ten-minute suppression; workers may complete out of order.  
**GREEN:** correlated resubscribe/reconnect, parity backfill, keyed queues and success-based cooldown.  
**Done:** kline-only fault returns to parity within SLO with no duplicate decision side effect; prolonged failure halts execution.

### U11 — Acceptance oracle

**Invariant:** PASS requires a fixed profile and representative, self-cleaning cross-plane behavior.  
**RED:** short/optional/shallow/direct smoke can misclassify system.  
**GREEN:** manifest, non-qualifying diagnostic mode, testnet-only engine probe, cycle state machine, deep checks, error budgets and zero-tolerance safety invariants.  
**Done:** harness cannot pass if any mandatory check is skipped, duration/samples are short, cleanup unresolved, monitoring absent or final convergence false.

### U12 — Forensic lifecycle

**Invariant:** report identity and shutdown/retention are part of acceptance.  
**RED:** report precedes shutdown, logs buffer, failure destroys volumes, provenance missing.  
**GREEN:** streamed/rotated logs, checksummed provenance and snapshots, shutdown-before-verdict, failure retention.  
**Done:** forced shutdown/log/interruption tests retain diagnostic evidence and yield truthful failure status.

### U13 — Monitoring, security and drift closure

**Invariant:** documented health/security/contracts match the running acceptance topology.  
**RED:** no monitoring assertions, permissive WS CORS, naive alert timestamps and stale docs/routes.  
**GREEN:** soak Compose, metrics/alerts/dashboard assertions, real BFF readiness, shared CORS allowlist, migration 036 and updated schemas/runbooks/docs.  
**Done:** monitoring targets/metrics/UI assertions pass; cross-origin negatives pass; timestamp migration preserves known instants; no stale emergency/order API remains authoritative.

### U14 — Qualification and activation governance

**Invariant:** only the exact artifact that passed the complete ladder may be considered for live-small.  
**RED:** previous elapsed duration did not establish acceptance.  
**GREEN:** focused/full CI → fault matrix → 2h → 24h/restarts → fresh 7d; artifact comparison and explicit activation checklist.  
**Done:** all stages pass without combining elapsed time; exact image/migration/config hashes match; testnet account is clean; live-small begins halted and needs operator resume.

## U4. Unified test coverage

All tests in Draft A §A4 are required. Tests must assert full structures where practical and use independent expectations, not values generated by the production function under test. Pure state-machine/hash/config tests remain unit tests; DB transaction, restart, HTTP boundary, exchange-testnet and Compose checks remain integration/chaos/E2E tests.

## U5. Unified decision completeness

### Public surfaces and migrations

The public/internal interfaces, migration design, compatibility flags and failure policies are locked in Draft A §A5. No implementer may change the meaning of `success`, `ready`, `fully_flattened`, or `halted` without revising the cross-language contract and acceptance tests first.

### Error budgets and zero-tolerance invariants

Provisional acceptance SLOs, to be frozen before implementation begins:

- Core-service availability at least 99.9%; no unplanned outage longer than 60 seconds.
- Bracket acknowledgment p95 under 5 seconds on testnet, excluding declared fault windows.
- Order-update delivery p95 under 30 seconds; final outbox pending/dead-letter and inbox gap counts zero.
- Snapshot plus Telegram canary under 60 seconds.
- Kline repair-to-parity within 5 minutes or two expected candle intervals, whichever is larger.
- Process RSS growth no more than 20% above stabilized first-hour baseline; disk headroom never below 20%.
- No unplanned container restart.
- Zero false placement success, duplicate logical bracket, unsafe-ready transition, halt bypass, lost update, unprotected acquired position, quarantined cycle, above-threshold residual or acceptance-owned final open order.

Transient liveness misses count against availability/duration budgets. Safety invariants have no budget.

### Live-small NO-GO

Live-small remains NO-GO if any U1–U13 item is incomplete, any compatibility flag permits missing IDs/direct authoritative delivery, any seven-day artifact lacks provenance/monitoring, any current exchange residual is unknown, or any zero-tolerance invariant is violated.

### Live-small GO prerequisites

- All stages pass on exact intended image digests and migration/config fingerprints.
- Main starts halted; operator verifies readiness/reconcile/control/outbox/account state and explicitly resumes.
- Mainnet acknowledgment, venue/account allowlist and independent maximum-notional cap are active.
- Automatic halt and manual emergency canaries pass immediately before activation.
- On-call operator has executed the halt/flatten/rollback runbook.

## U6. Dependencies and prerequisites

- Implementation begins from an isolated worktree because the primary checkout contains user-owned untracked Coding Logs/artifacts.
- Before the first testnet run, perform read-only exchange-authoritative inventory; cleaning or selling residuals requires separate explicit authorization.
- Freeze cross-service schema versions and provisional SLO values in the first implementation PR.
- Confirm PostgreSQL version/advisory-lock support and migration rollback strategy.
- Ensure Telegram test credentials and testnet keys are scoped, non-withdrawal, IP-restricted where supported, and never emitted in artifacts.

## U7. Validation command groups

Exact package commands are refreshed per slice, but the final gates are:

1. Python formatter/lint/type checks and complete engine tests.
2. `go test ./...`, formatting and configured Go linter.
3. Prettier check, BFF/UI tests, and `turbo typecheck lint`.
4. Migration clean-install and 033-upgrade tests.
5. Render/validate base, dev and soak Compose configurations.
6. Security/dependency gates from the Makefile.
7. Contract generation and cross-language compatibility tests.
8. Full fault-injection matrix with retained artifacts.
9. 2h, 24h and uninterrupted seven-day qualification.

The formal implementation lifecycle must independently rerun all final gates and perform QCHECK plus `g-check` before any PR is considered for landing.

## U8. Unified wiring verification

The authoritative wiring table is Draft A §A8. Every implementation PR must include the subset it changes and prove entry point, registration and schema in tests. Components without a runtime caller, registration site or correct table/contract cannot be marked complete.

## U9. Rollout sequence

1. U1 typed placement truth.
2. U2 caller identity support, then router enforcement in testnet.
3. U3 execution intents and fail-closed reservation.
4. U4 execution control, deployed halted.
5. U5 emergency cleanup.
6. Engine inbox from U6.
7. Router outbox shadow, parity comparison, authoritative switch, direct removal.
8. U7 strict readiness.
9. U8 typed risk/config and safety coordinator.
10. U9 canonical auth/canaries.
11. U10 ingest repair/order.
12. U11 diagnostic then qualification harness.
13. U12 forensic lifecycle.
14. U13 monitoring/security/contracts/docs.
15. Read-only testnet account baseline, then separately authorized cleanup if needed.
16. U14 complete qualification ladder.

## U10. Decision-complete checklist

- [x] Goal, non-goals and measurable success are locked.
- [x] Every confirmed critical/high/medium/low gap maps to a slice and proof.
- [x] Public APIs, env variables, migrations and compatibility modes are listed.
- [x] Fail-closed/fail-open behavior is explicit at every execution boundary.
- [x] Every behavior change has a defect-sensitive test name.
- [x] TDD order and dependency ordering are explicit.
- [x] New components have entry points, registrations and schemas.
- [x] Cross-language schema verification is required before migrations.
- [x] Rollout, shadowing, backout and retained-state rules are defined.
- [x] Acceptance budgets, zero-tolerance invariants and live-small gates are explicit.
- [x] No signal strategy or unrelated architecture change is included.
- [x] No implementation decision remains open; only separately authorized runtime/account actions remain.

## Final recommendation

Adopt the Unified DREP. Start with U1 in an isolated worktree using strict TDD, but do not schedule another seven-day acceptance window until U1–U13 and the full fault-injection stage pass. Treat the current testnet account baseline and residual cleanup as an explicit pre-qualification checkpoint, not an assumption.

## G2 Revalidation (2026-08-13 15:42:25 +07) - U1 through U6

### Repository profile and worktree ledger

- Candidate root: `/Users/subhajlimanond/.codex/worktrees/online-trader-seven-day-soak-u1-u6`
- Branch: `codex/seven-day-soak-u1-u6`
- Baseline and candidate HEAD: `ed13749031bf915e5896cda19cbc680b5895d60c`
- Source primary checkout: `/Users/subhajlimanond/dev/online trader`; branch `main`; HEAD `ed13749031bf915e5896cda19cbc680b5895d60c`
- Protected primary state: all pre-existing untracked `.codex/`, `.turbo/`, Coding Logs, docs, prompt exports, reports, and guideline artifacts remain untouched.
- Baseline worktrees: the primary checkout and pre-existing detached `/Users/subhajlimanond/.codex/worktrees/d919/FE-Dev`.
- Session-created worktree: candidate root above, created from `origin/main` for planning, implementation, gates, review, delivery, and exact-SHA landing; disposition is removal after verified merge and artifact preservation.
- Current Coding Log pointer resolves to this file. The source DREP and pointer were copied byte-for-byte into the isolated candidate because they were untracked in the protected primary checkout.
- Applicable policy: root `AGENTS.md`, supplied Development Delegation Policy, `CONTEXT.md`, explicit-only `g2-planning`, explicit-only `g2-coding`, and formal `g-check`.
- Augment semantic search is not exposed in the live tool inventory. Discovery used the required fallback: RepoPrompt bound to the exact candidate root plus exact-identifier searches.
- Languages/tooling: repository Python >=3.11, Node >=18, pnpm >=8, Go 1.25/toolchain 1.25.8; host reports Python 3.13.1, Node 26.0.0, pnpm 9.15.4, Go 1.25.1.
- Migration sequence was rechecked and ends at `033_bff_alert_tables.sql`; migrations 030/031 already own `brackets` and `bracket_legs`, so new U1-U6 schema starts additively at 034.

### G2 capability and ownership disposition

- The user explicitly selected the g2 path and thereby authorized the task-scoped external DeepSeek probe.
- Full `g2-doctor --allow-external-probe` passed: CLI 0.147.0, Keychain credential present without disclosure, local Responses proxy healthy, `deepseek-v4-pro` advertised, agent registered, and provider tool round returned `G2_TOOL_OK`. Native Responses availability produced one non-blocking warning.
- Q0 fails for delegation because the live parent permission profile is unrestricted, not inspectable `workspace-write` containment with zero extra writable roots.
- Q1 independently assigns all six complete slices to PRIMARY: U1 changes execution-safety and public result semantics; U2 changes public contracts, concurrency and schema; U3 changes migrations/distributed durable state and ambiguity recovery; U4 changes authenticated distributed locking and resume authority; U5 performs exchange-mutating emergency operations; U6 changes migrations, transactional distributed delivery, ordering and authenticated contracts.
- Stop line for U1-U6: `PRIMARY`. Production allowlist for DeepSeek: empty. No DeepSeek implementation handoff will be created.

### Current runtime truth and accepted adversarial corrections

- U1 is a replacement/hardening slice: `RouterHTTPClient` returns ordinary dictionaries for failures and the subscriber accepts nearly all dictionaries as success. Cooldown is acquired before POST and must be released or bound to the durable intent on failure. The subscriber becomes the sole retry owner.
- U2 retains the engine's stable Binance client-ID builder and the router's existing reservation/replay foundation. It adds a versioned canonical normalized request hash, explicit idempotency identity scoped by execution account/environment/venue, complete conflict comparison, and migration of every caller before enforcement.
- U3 hardens existing `BracketRepo` durability rather than creating a competing reservation model. Engine PREPARED intent persistence must precede router access; active execution must reject a nil store, reservation/control failure, or unpersisted acknowledgment. Existing shared `orders` ownership must be reconciled so planned deferred legs are not misreported as exchange-acknowledged.
- U4 route registration belongs in `app/router/cmd/router/main.go`, not the stale planned `internal/api/router.go`. The advisory-lock scope is the execution account/environment/venue, and ALL must cover every configured execution scope. An acknowledged halt is the authoritative boundary.
- U5 freezes the sequence as halt acknowledgment, forced-fresh exchange enumeration, entry cancellation, flattening while retaining protection, orphan-exit cleanup, forced-fresh requery, then residual verdict. Attempted work is never reported as confirmed clean.
- U6 must freeze one versioned router-to-engine envelope before adding durability. Every state writer and current direct producer, including manager, armers/watchers, startup and spot reconcilers, and trade processors, must use a transactional transition-plus-sequence-plus-outbox operation. Direct emitters are removed as authorities after shadow parity. Engine inbox insertion/hash/sequence validation precedes projection mutation and bus publication.
- Current direct update transport, emergency APIs, durable bracket reservations, correlation store, and projections are partial foundations; no parallel authority will be added.
- SMC/retest and daily trend signal generation remain unchanged. The active execution boundary remains `RouterExecutionSubscriber` and the Go router.

### Revalidated dependency order and gates

1. U1 typed placement truth and false-success regression matrix.
2. U2 identity contract, all callers, canonical hash, durable conflict, then enforcement.
3. U3 engine PREPARED intents and mandatory router reservation/ACK ordering.
4. U4 durable control with placement/halt concurrency fence, deployed halted.
5. U5 exchange-authoritative halt-first emergency cleanup and residual truth.
6. U6 authoritative order-update envelope, engine inbox first, router shadow outbox, parity, cutover, and direct-emitter removal.

Each slice uses primary-authored acceptance tests, expected RED confirmation, minimum GREEN, scoped fast gates, runtime wiring evidence, and a coherent Coding Log entry. Final completion requires repository-prescribed tests/typecheck/lint/format/build/security gates, three consecutive affected-suite passes, non-DeepSeek QCHECK, formal `g-check`, PR checks, authorized admin merge, exact merged-SHA local-main landing, and session worktree closeout.

## Implementation (2026-08-13 16:03:50 +07) - U1 placement truth

### Goal and ownership

- Enforce that only a semantically valid router 2xx placement can produce persistence, snapshot, `OrderPlacedEvent`, BFF persistence, or success logging.
- PRIMARY-owned under g2 Q1 because this changes live execution error semantics and cross-language placement contracts. No delegate edited product code.

### RED evidence

- Command: `'/Users/subhajlimanond/dev/online trader/app/engine/.venv/bin/python' -m pytest app/engine/tests/unit/test_router_http_client_placement.py app/engine/tests/unit/test_router_execution_subscriber.py::test_router_failure_has_no_success_side_effects -q`
- Result: `6 failed`. Intended failures: HTTP 400 and circuit-open returned dictionaries; malformed 2xx was accepted; 201 was not returned as a typed result; the client retried internally; the historical 400 caused three order rows plus snapshot/event success effects.
- Command: `pnpm --filter @app/bff test -- router-client/router-client.service.spec.ts --runInBand`
- Result before GREEN: `3 failed, 17 passed`. Intended failures: partial and malformed 2xx resolved successfully; one ambiguous transport observable was subscribed three times.
- Command: `go test ./internal/api -run 'TestPlaceBracketHandler/partial_failure_response' -count=1`
- Result before GREEN: expected HTTP 502, actual HTTP 200.

### Implementation and files

- `app/engine/adapters/router_client/http_client.py`: added immutable `BracketPlacementResult`, client-ID result type, typed circuit/transport/HTTP/protocol errors, bounded error bodies, any-2xx JSON parsing, exact bracket response parsing, and one low-level bracket POST attempt.
- `app/engine/execution/router_execution_subscriber.py`: replaced permissive dictionary checking with semantic validation of bracket ID, exact client IDs/TP count, symbol, side, partial/errors; retained one ambiguity-safe retry owner for transport, 429, and 5xx only; emits typed error classes and cannot advance untyped results.
- `app/engine/core/signal_cooldown.py`: added reservation release for placements that never reach validated success. Redis release failure remains fail closed and is logged.
- Engine tests: added the historical response/error matrix and updated mocks to the actual typed contract; updated the in-process HTTP contract response.
- `app/bff/src/router-client/router-client.service.ts`: added structural/semantic response validation and removed bracket POST retry until U2 makes caller identity mandatory.
- `app/bff/src/router-client/router-client.service.spec.ts`: added partial, malformed, and single-subscription ambiguity regressions.
- `app/router/internal/api/handlers.go`: maps partial bracket placement to HTTP 502 before the success log while preserving placement artifacts for reconciliation.
- `app/router/internal/api/handlers_test.go`: locks the partial-placement 502 contract.

### GREEN and fast gates

- Engine affected unit scope: `62 passed in 0.42s`.
- BFF router client scope: `20 passed`.
- Router API package: `go test ./internal/api -count=1` passed.
- Python Ruff check/fix and formatter were run on the touched U1 Python files; post-format affected tests remained green.
- BFF Prettier check passed and `pnpm --filter @app/bff exec tsc --noEmit` passed.
- The existing `app/engine/tests/integration/test_router_execution_contract.py` could not execute because its directory-level autouse DB preflight requires local Postgres role `trading_user`, which is absent. `-m integration` reaches the exact infrastructure failure; the test's router response was updated to the typed contract and must be rerun during the database-backed full gate.

### Wiring evidence

| Component | Non-test runtime call site | Registration/config load | Schema/contract match |
|---|---|---|---|
| Typed engine placement result | `RouterExecutionSubscriber._place_bracket_with_retries()` | `app/engine/main.py` constructs `RouterHTTPClient` and `RouterExecutionSubscriber` | Go `PlaceBracketResponse` fields parsed and exact client IDs checked |
| BFF placement validator | `RouterClientService.placeOrder()` | `RouterClientModule` provides/exports the service; `TradingService.placeOrder()` calls it | Go response fields, one TP identity, partial/error rejection |
| Router partial failure status | `Handlers.PlaceBracketHandler()` | `/place_bracket` registered in `app/router/cmd/router/main.go` | Existing `PlaceBracketResponse.PartialFailure/Errors`; HTTP 502 |
| Cooldown release | `RouterExecutionSubscriber._execute_decision()` exception path | Existing `SignalCooldown` injection in engine startup | Redis `delete` plus in-memory reservation removal |

### Behavior and remaining dependency

- Fail closed: non-2xx, circuit-open, transport exhaustion, malformed/untyped/partial/mismatched results produce no success side effects.
- BFF sends exactly one bracket POST until U2 supplies mandatory caller-owned identity; U2 will then enable bounded same-body retry where safe.
- U1 does not claim DB acknowledgment durability; that is intentionally locked to U3.

## Implementation (2026-08-13 16:29:33 +07) - U2 end-to-end idempotency

### Locked contract

- Every active `/place_bracket` request carries a non-blank `idempotency_key` plus a complete Binance-safe `client_order_ids` set before the first POST.
- Router identity is scoped by the configured execution account/environment and venue. The durable unique key is `(venue, idempotency_key)` within that router-owned account boundary.
- The request hash is SHA-256 over the canonical post-rounding exchange payload: venue, symbol, side, quantity, entry/TP/SL prices, order type and every client order ID. Non-execution metadata is excluded.
- Same-key same-hash replay adopts the durable bracket/exchange entry. Same-key different-hash replay returns an `IdempotencyConflictError`, mapped to HTTP 409, before any new order POST.

### RED evidence

- Router validation RED failed to compile because `PlaceBracketRequest` had no idempotency identity; hash/conflict tests then failed on missing canonical hashing and durable fields.
- BFF placement RED failed because `placeOrder` accepted no identity and ambiguous transport errors subscribed only once.
- REST/WS RED failed because neither route carried a caller key into `PlaceOrderCommand`.
- UI RED showed the manual placement POST had no `X-Idempotency-Key`.
- Soak RED failed because the body builder accepted no `run_id`/`cycle_id` and emitted no stable identity.

### GREEN implementation and wiring

- Router request validation now requires `idempotency_key` and a complete ID set. Migration `034_execution_safety.sql` adds `brackets.idempotency_key`, `request_hash`, the unique venue/key index and hash-length constraint.
- `BracketRepo.Reserve()` claims by venue/key and returns the stored hash/identity on replay. `canonicalBracketRequestHash()` normalizes decimal scale and includes all exchange-relevant fields; divergent reuse is a typed conflict mapped by the HTTP handler to 409.
- Existing lost-response replay was renamed to the acceptance contract `TestLostResponseReplayPlacesEntryOnce`; `TestPlaceBracketRequiresClientOrderIDs` and `TestIdempotencyKeyPayloadConflict` lock the other router invariants.
- BFF derives a branded router identity from authenticated principal plus REST header / WS field, sends the exact same immutable body through bounded transport/429/5xx retry, and validates returned client IDs against the request.
- UI manual placement creates one UUID per service invocation and supplies `X-Idempotency-Key`. BFF decision events derive stable identities from the event fields. Engine decisions carry stable signal/decision identity. Soak uses `run_id + cycle_id + symbol`; the manual bracket helper reuses its supplied client ID.

### GREEN evidence

- `go test ./... -count=1` in `app/router`: every router package passed, including exact U2 acceptance tests.
- BFF full Jest: `44 passed`, `360 tests passed`; targeted placement/service/controller/gateway tests passed. The pre-existing Jest open-handle notice remains diagnostic and is not a test failure.
- UI `trading.service.spec.ts`: `15 passed` after proving the idempotency header.
- Engine/subscriber/router-client plus soak selection: `86 passed`; isolated-worktree preflight path required a temporary ignored `.venv` symlink, after which `tests/test_run_testnet_soak.py` passed `41/41`.

### Wiring table

| Contract | Entry point | Registration / caller | Durable owner |
|---|---|---|---|
| Required router identity | `Manager.validateBracketRequest()` | `/place_bracket` in router `main.go` | `brackets.idempotency_key`, `request_hash` |
| Manual REST identity | `TradingController.placeOrder()` | UI `TradingService.placeOrder()` header | Router bracket reservation |
| Manual WS identity | `TradingGateway.placeOrder()` | `placeOrder` message `idempotencyKey` | Router bracket reservation |
| BFF stable retry | `RouterClientService.placeOrder()` | `PlaceOrderHandler` / decision handler | Router bracket reservation |
| Engine identity | `RouterExecutionSubscriber._execute_decision()` | Existing engine subscriber wiring | Router bracket reservation |
| Soak identity | `build_dynamic_order_smoke_body()` | periodic soak cycle runner | Router bracket reservation |

## Implementation (2026-08-13 17:43:15 +07) - U3 through U6 durable execution safety

### U3 durable intent and reservation

- Engine migration 034 and `TimescaleDBAdapter` now persist `PREPARED` before router access, transition to `SUBMITTING`, and require `ACKNOWLEDGED` after order projections but before snapshot/order-placed success effects. An accepted placement whose ACK cannot persist becomes `AMBIGUOUS` and retains its setup cooldown.
- Router active placement requires both the DB-backed bracket store and durable execution-control gate. Reservation/control/persistence failures are typed durability failures and cannot call the exchange or return placement success.
- RED contracts covered prepare failure before router submission and ACK persistence failure after a valid typed placement. GREEN affected engine scope passed, and stale test doubles were updated to implement the now-required durable interface.

### U4 durable halt

- Migration 034 creates a default-HALTED global control row and an append-only idempotent request ledger. PostgreSQL shared/exclusive advisory locks fence placement through durable outcome and drain in-flight placement before halt acknowledgment.
- Router exposes authenticated GET/halt/resume control routes. Resume requires a completed safe startup reconcile plus healthy configured outbox delivery. BFF emergency flow halts and confirms authoritative state before flattening; the local UI preference is not treated as stop authority.
- DB-backed race/restart/idempotency tests pass. Independent QCHECK found stale halt replay could lie after a later resume; the replay now verifies the current state/generation/key and rejects stale or payload-divergent reuse. The new `halt(K1) -> resume(K2) -> halt(K1)` integration test passes.

### U5 exchange-authoritative emergency flatten

- Router emergency `ALL`, `SPOT`, and `FUTURES` enumerate forced-fresh exchange state, cancel entries, flatten futures/spot exposure, clean orphan exits, requery for up to three passes, and return starting/final state plus explicit residuals. Requested venues without configured clients fail rather than appearing flat.
- Market-close identities are stable across all passes. A timeout or transport ambiguity is resolved by repeated exchange lookup using the same client ID and then polled to a terminal fill; a fresh close ID is never issued for the same intent.
- Acceptance tests cover unknown spot holdings/orders, above-threshold residual truth, missing clients, spot accepted-but-response-timeout recovery, and futures accepted-but-504 recovery with exactly one submitted client identity.

### U6 durable order-update delivery

- Migration 035 adds per-aggregate sequences, router outbox, engine inbox, transaction trigger, uniqueness, indexes, and least-privilege runtime-role grants. Bracket-leg transitions and their outbox event commit atomically; all active router producers use the DB-backed emitter.
- Active execution now fails startup unless DB, dispatcher URL, and engine token are configured. Resume also fails if the dispatcher is unavailable or the outbox is dead/too old. Direct HTTP is no longer the active runtime authority.
- Outbox claims with `FOR UPDATE SKIP LOCKED`, preserves aggregate order, retries with jitter, and exposes health. Semantic event identity excludes only transport timestamp, preserves distinct partial-fill quantities, and is serialized/unique under concurrent identical enqueue.
- Engine validates/authenticates the versioned envelope, claims a durable ordered inbox before projection/publication, returns idempotent duplicate success, conflicts on hash reuse, parks gaps/regressions, and completes only after projection and bus publication. A terminal state is immutable, including terminal-to-different-terminal transitions.
- PostgreSQL integration tests pass for atomic state/outbox, partial-fill preservation, concurrent deduplication, runtime grants, restart-persistent halt, and replay safety. Engine affected U3/U6 scope passes 91 tests after QCHECK remediation.

### Independent QCHECK disposition

The Terra read-only QCHECK reported eight blocking findings: stale halt replay, ambiguous emergency identity, missing-client false flatness, optional runtime outbox, lossy/racy outbox deduplication, missing runtime grants, terminal-state mutation, and cooldown release after accepted placement. All eight were accepted and remediated with defect-specific tests before formal `g-check`.

### Baseline distinction

- Full engine unit result after U1-U6 repairs: `1577 passed, 2 skipped, 1 failed`. The sole failure reproduces unchanged on protected `main`: MyPy rejects the pre-existing Redis `mset(dict[str, str])` annotation at `redis_adapter.py:717`.
- Full UI Vitest on host Node 26 has 96 files passing and 18 failures in untouched `AuthContext.spec.tsx` because Node 26 exposes an unavailable experimental `localStorage`; repository support is Node >=18 and CI uses Node 18. UI TypeScript and the changed trading-service tests pass.
- Full BFF Jest passed all 44 suites and 361 tests; Jest emitted its existing open-handle diagnostic after success. BFF TypeScript passes.

## Formal g-check (2026-08-13 21:11:00 +07)

### Findings and disposition

The formal skeptical review ran iteratively over the complete U1-U6 diff and then over focused remediation surfaces. Every actionable P0/P1 finding was accepted and repaired with a defect-specific regression before review resumed. The final focused review returned `No findings`.

The last two review rounds found and closed these additional safety gaps:

- Futures hedge-mode conditional entry orders are now classified from `reduceOnly` / `closePosition` and position-reducing side semantics, never from `STOP` or `TAKE_PROFIT` type names alone.
- Spot emergency flatten now cancels protective orders to unlock balances, resolves lost cancellation responses against exchange state, and includes an unresolved group in mandatory restoration when both the cancel response and immediate reconciliation fail.
- Bracket quantity validators reject an exchange/router result that is either larger or smaller than the requested quantity.
- `publish_and_wait` requires at least one successful subscriber and no failed subscribers; execution intents cannot transition to `ACKNOWLEDGED` until `OrderPlacedEvent` delivery completes successfully.
- UI retry identity is operation-scoped and durable across reload. Pending operation handles can be enumerated and resumed explicitly by persisted ID; the canonical field fingerprint rejects payload changes without colliding concurrent identical placements.
- BFF emergency-response validation matches the router contract: residuals equal all final spot balances, dust and historical pass errors may coexist with a later successful flatten, and `fully_flattened` still rejects final exposure or final-state errors.

### Final remediation evidence

- Router `go test ./internal/orders -count=1`: passed, including conditional hedge entries, locked spot protection, lost cancel response, lost cancel plus failed reconciliation, restore-on-close-failure, and exact market-close identity.
- Router database-backed `go test ./internal/orders -count=1`: passed against `trading_platform_test`.
- Engine affected unit scope: `55 passed`; focused integration contracts: `2 passed` against the test database.
- BFF router-client validation: `42 passed`; BFF TypeScript passed.
- UI trading-service retry/reload scope: `20 passed`; UI TypeScript passed.
- Final formal reviewer disposition: `No findings`.

## Final gates (2026-08-13 21:16:00 +07)

### Passing candidate gates

- Router: `go test ./... -count=1`, `go vet ./...`, and `go build ./...` passed. Database-backed `internal/orders` passed; all six new execution-control integration tests passed against `trading_platform_test`.
- Engine: affected U1/U3/U6 tests passed; the full unit run reached `1628 passed, 2 skipped, 27 deselected` with only the confirmed baseline Redis MyPy test failure. Ruff lint passed. Every changed Python file is Ruff-formatted. Root soak/launcher tests passed `48/48`, and engine byte-compilation passed.
- BFF: all `44` suites and `383` tests passed. Prettier, ESLint, TypeScript, and direct `nest build` passed. The package `prebuild` wrapper remains incompatible with the host Node 26 `glob`/`minimatch` combination, while the underlying production compilation succeeds.
- UI: the changed trading-service suite passed `20/20`; TypeScript and Prettier passed. The production Next build compiled, typechecked, generated all 11 pages, and completed successfully. Full Vitest reproduced the unchanged host-Node-26 baseline: `96` files / `1362` tests passed, `18` untouched `AuthContext.spec.tsx` tests failed because experimental `localStorage` is unavailable.
- Security: high-severity Bandit over every changed Python production/script file returned no findings. Formal g-check returned `No findings`.

### Confirmed baseline / environment gates

- Full engine Ruff-format check reports four untouched files; protected `main` reports those same four plus the now-formatted changed `timescale_adapter.py`.
- Full engine MyPy reports the same two errors on candidate and protected `main`: `pipeline_health_service.py:170` and `redis_adapter.py:717`.
- Standalone UI ESLint 9 cannot find a flat config on candidate or protected `main`; the Next production build's integrated lint step completed with four existing warnings.
- The broad dependency audit is non-green on existing locks/environments: `pip-audit` reports 106 known vulnerabilities in 15 installed packages; `pnpm audit` reports 158 advisories (12 low, 72 moderate, 71 high, 3 critical); `gosec` and `nancy` are not installed. No dependency manifest or lockfile is changed by U1-U6.
- The broad storage-package database run also reaches two pre-existing schema-drift failures (`orders.decision_ts` missing and positions conflict constraint missing). The new U4 execution-control integration subset passes independently.
