# Coding Log: Engine durable success boundary

- Created: 2026-08-22 Asia/Bangkok (exact clock unavailable because the configured Code Mode host executable is missing)
- Worktree: `/Users/subhajlimanond/.codex/worktrees/online-trader-engine-durable-success-boundary`
- Branch: `codex/engine-durable-success-boundary`
- Baseline: `9ecd69dcd920b3ab2bb759559841c29e5a2fbb26` (`origin/main`, merge of PR #221)
- Lifecycle scope: first incomplete item from the user-provided optimal pickup order
- Discovery: RepoPrompt Context Builder plus focused file reads/searches. Augment semantic retrieval is not exposed in this session, so repository discovery used the mandated RepoPrompt fallback rather than Bash semantic search.
- Primary checkout boundary: `/Users/subhajlimanond/dev/online trader` remained on `main` with 29 pre-existing untracked files; the unrelated detached `FE-Dev` worktree remained untouched.

## Requirement lock

Repair the engine durable-success boundary after a valid router/exchange ACK. If the engine cannot atomically persist the ACK and complete order projection, it must emit no snapshot notification, no `OrderPlacedEvent`, no placement-success log, and expose no committed partial/completed projection from that attempt. It must retain a durable recoverable `AMBIGUOUS` or prior `SUBMITTING` state. A same-key replay must reuse the exact router identity, avoid duplicate exchange placement, and resume required success delivery.

Current `origin/main` already has stable engine idempotency/client-order IDs, durable router reservations, typed router ACK validation, `PREPARED`/`SUBMITTING`/`AMBIGUOUS` states, and router replay adoption. It does not satisfy the boundary: `RouterExecutionSubscriber._execute_decision()` currently persists each order on separate connections, calls BFF, publishes `OrderPlacedEvent`, and only then tries `ACKNOWLEDGED`. The existing ACK-failure test positively asserts two success events across replay and must be replaced.

## Plan Draft A: Intent-column delivery checkpoints

### 1. Overview

Atomically commit order projections and `ACKNOWLEDGED`, then track snapshot and event completion using additive delivery columns on `execution_intents`. Replays inspect the intent before duplicate/cooldown rejection and resume unfinished effects without calling the router once the ACK is durable.

### 2. Files to change

- `app/engine/tests/unit/test_router_execution_subscriber.py`: replace the defective ACK-failure contract and cover replay/delivery ordering.
- `app/engine/tests/unit/test_execution_intents_adapter.py`: prove transaction and checkpoint SQL contracts.
- `app/engine/tests/integration/test_execution_intent_success_boundary.py`: real PostgreSQL rollback/atomicity evidence.
- `app/engine/execution/router_execution_subscriber.py`: split durable placement from success delivery and build projection rows without independent writes.
- `app/engine/adapters/db/timescale_adapter.py`: atomic ACK/projection API plus intent/delivery reads and checkpoints.
- `db/migrations/036_execution_success_delivery.sql`: add intent delivery state/checkpoint columns and safe legacy backfill.

### 3. Implementation steps

TDD order for each behavior:

1. Add or replace the smallest meaningful test.
2. Run the exact scoped command and confirm expected RED.
3. Hand the locked production allowlist to Luna-Max.
4. Implement the smallest production change to pass.
5. Refactor only shared order-upsert SQL and the independently testable delivery phase.
6. Run scoped tests, formatter, lint, and type checks.

Functions:

- `TimescaleDBAdapter.commit_execution_ack(...)`: in one write transaction, upsert every order projection and guard `SUBMITTING -> ACKNOWLEDGED` while storing the router response and setting delivery pending.
- `TimescaleDBAdapter.get_execution_intent_for_request(...)`: load same-key state, verify the canonical request hash, and fail closed on divergent reuse.
- `TimescaleDBAdapter.record_execution_success_effect(...)`: idempotently checkpoint snapshot/event completion.
- `RouterExecutionSubscriber._build_order_projection_rows(...)`: return the complete entry/TP/SL projection without database side effects.
- `RouterExecutionSubscriber._resume_success_delivery(...)`: run snapshot before event, skip completed effects, and log success only after final checkpoint.

Expected failure behavior: transaction failure rolls back all order rows and ACK; separate best-effort `AMBIGUOUS` persistence follows, otherwise the existing durable `SUBMITTING` remains replayable. Delivery failure does not demote an already durable ACK to ambiguous.

### 4. Test coverage

`test_router_execution_subscriber.py`:

- `test_ack_commit_failure_has_no_success_effects_and_retains_ambiguous_replay`: failed durable boundary emits no success.
- `test_same_key_replay_after_ack_commit_failure_recovers_success_once`: stable replay avoids duplicate exchange placement.
- `test_snapshot_failure_leaves_acknowledged_delivery_pending`: snapshot failure preserves durable ACK.
- `test_pending_snapshot_delivery_replay_skips_router_and_completes`: replay resumes snapshot then event.
- `test_pending_order_event_replay_does_not_repeat_snapshot`: event retry preserves snapshot checkpoint.
- `test_delivered_execution_replay_is_noop`: completed replay emits nothing twice.

`test_execution_intents_adapter.py`:

- `test_commit_execution_ack_uses_one_connection_and_transaction`: projections and ACK share transaction.
- `test_commit_execution_ack_rejects_non_submitting_state`: guarded transition fails closed.
- `test_matching_acknowledged_intent_is_replayable_for_delivery`: same request resumes checkpoints.
- `test_divergent_acknowledged_intent_replay_fails_closed`: hash mismatch never reaches router.

`test_execution_intent_success_boundary.py`:

- `test_ack_commit_rolls_back_all_projection_rows_when_any_leg_fails`: no partial projection survives failure.
- `test_ack_commit_persists_projection_and_pending_delivery_atomically`: one transaction exposes complete durable state.
- `test_delivery_checkpoints_finalize_once`: checkpoint replay remains idempotent.

### 5. Decision completeness

- Goal: make ACK/projection the durable success boundary and make later effects recoverable.
- Non-goals: router behavior changes, client-ID/hash changes, BFF schema changes, global exactly-once delivery, a background outbox dispatcher, readiness/U8+ work.
- Success criteria: all required tests and gates pass; forced ACK/projection failures expose no success effects or rows; same-key replay produces one simulated exchange placement; ACK-pending replay skips router; complete replay is a no-op.
- Public interfaces: additive migration `036`; no endpoint, CLI flag, env var, or event-schema change. Internal adapter APIs change.
- Failure policy: fail closed before router on DB/hash uncertainty; preserve cooldown once submission may have occurred; keep ACK durable and delivery pending on effect failure.
- Delivery cardinality: direct effects are at-least-once across crash windows. Snapshot uses stable `signalId`/idempotency identity and event uses deterministic UUID; downstream deduplication is still required.
- Rollout: apply migration before engine deployment; migration backfills legacy ACKs as delivered so historical effects are not replayed. Backout is application rollback with additive schema retained.
- Monitoring: structured errors distinguish `execution_intent_unavailable` from `success_delivery_pending`; watch ACK commit failures, pending age, retries, and delivery failures.
- Acceptance commands: scoped pytest files, real DB integration test, `make test-engine`, `make lint`, `make typecheck`, `make format-check`, router replay tests, and full `make ci`.

### 6. Dependencies

PostgreSQL integration database with migrations through `036`; existing router durable store/replay behavior from PR #221; BFF client and event bus already wired in engine startup.

### 7. Validation

Trace a valid decision through router ACK, atomic DB commit, snapshot, event, and success log. Fault each boundary and inspect rows/events. Run the affected scope three consecutive times and preserve exact outputs in this log.

### 8. Wiring verification

| Component | Entry point | Registration location | Schema/contract |
|---|---|---|---|
| Atomic ACK API | `RouterExecutionSubscriber._execute_decision()` after typed ACK | Existing adapter injected by `app/engine/main.py:initialize_services()` | `orders`, `execution_intents` |
| Pending delivery | same-key decision replay and immediate post-commit call | Existing subscriber on `TRADING_DECISION` | new columns on `execution_intents` |
| Migration 036 | normal migration runner before engine startup | root DB migration sequence | `execution_intents` |

### 9. Cross-language schema verification

Python uses `execution_intents` and `orders`; Go uses `brackets`, `bracket_legs`, and the durable `(venue,idempotency_key)` reservation. No Go schema or code changes are required. Migration `035_order_update_delivery.sql` is current highest, so this slice must use `036`.

### 10. Decision-complete checklist

All interfaces, failure modes, tests, gates, rollout, and wiring are named. The remaining risk is that intent columns do not provide safe concurrent delivery claims across multiple engine processes.

## Plan Draft B: Generic durable success-delivery outbox

### 1. Overview

Atomically write projections, ACK, and payload-bearing outbox rows, then add a background dispatcher that delivers snapshot/event independently of decision replay. This offers stronger autonomous recovery and extensibility at the cost of a larger migration, new startup service, serialized payload contracts, and more operational state.

### 2. Files to change

Draft A files plus:

- `app/engine/execution/success_delivery_dispatcher.py`: background claim/retry loop.
- `app/engine/main.py`: construct/start/stop dispatcher.
- New dispatcher unit/integration tests and configuration/metrics tests.
- `db/migrations/036_execution_success_delivery.sql`: generic payload-bearing outbox with leases, attempts, retry schedule, and dead-letter state.

### 3. Implementation steps

Use the same RED -> Luna GREEN -> scoped gates sequence. Add `enqueue_execution_success_deliveries(...)`, `claim_due_success_deliveries(...)`, `mark_success_delivery_delivered(...)`, and `mark_success_delivery_failed(...)`. Serialize the complete effect payload in the ACK transaction. Wire a dispatcher lifecycle service that claims with leases, preserves snapshot-before-event ordering, retries with bounded backoff, and reports dead letters.

### 4. Test coverage

Draft A rollback/replay tests plus:

- `test_dispatcher_recovers_pending_delivery_after_engine_restart`: startup drain needs no event replay.
- `test_dispatcher_lease_prevents_concurrent_duplicate_claims`: only one engine owns a due effect.
- `test_dispatcher_reclaims_expired_delivery_lease`: crash recovery resumes work.
- `test_dispatcher_preserves_snapshot_before_event`: effect order remains deterministic.
- `test_dispatcher_dead_letters_after_retry_budget`: permanent failure becomes operator-visible.
- `test_main_starts_and_stops_success_delivery_dispatcher`: runtime wiring is complete.

### 5. Decision completeness

- Goal: autonomous durable at-least-once success delivery.
- Non-goals: globally exactly-once downstream effects and router changes.
- Public interfaces: additive outbox schema and likely retry env/config/metrics; serialized internal effect payload becomes a versioned durable contract.
- Failure policy: fail closed before ACK transaction; retry after ACK; dead-letter exhausted effects.
- Rollout/backout: migrate first, deploy dispatcher disabled, verify backlog, enable; rollback disables dispatcher and retains rows.
- Monitoring: pending age/count, attempt count, lease expiry, delivered rate, dead-letter count.
- Acceptance: Draft A commands plus dispatcher restart/concurrency integration tests and startup smoke.

### 6. Dependencies

A stable serialized event contract, retry configuration, worker lifecycle wiring, and downstream idempotency.

### 7. Validation

Kill the engine after ACK at each dispatcher checkpoint, restart it, and prove automatic drain without another trading decision event.

### 8. Wiring verification

| Component | Entry point | Registration location | Schema/contract |
|---|---|---|---|
| Success dispatcher | engine service startup loop | `app/engine/main.py` initialize/start/stop | `execution_success_outbox` |
| Atomic ACK enqueue | subscriber typed ACK path | existing subscriber | `orders`, `execution_intents`, outbox |
| Retry configuration | environment/config loader | main config assembly | retry/lease fields |

### 9. Cross-language schema verification

Only Python engine owns the new outbox. Go router remains authoritative for exchange replay; no Go schema identifiers change.

### 10. Decision-complete checklist

The architecture is complete but materially exceeds the first requested slice by adding worker lifecycle, durable payload versioning, retry policy, and dead-letter operations.

## Comparative analysis

Draft A is minimal but its intent-column checkpoints cannot safely elect a single delivery owner across multiple processes without awkward compare-and-set fields. Draft B has autonomous crash recovery and extensibility, but it expands the first PR into a new runtime service and operational subsystem. Both correctly place ACK/projection before effects and retain router replay safety. The best synthesis keeps Draft B's normalized leased delivery records and Draft A's replay-driven execution, avoiding a new daemon while making concurrent replay safe and leaving a clean path to a future dispatcher.

## Unified Execution Plan

### 1. Overview

Implement one engine/SQL durability slice: atomically commit the complete order projection, router response, `ACKNOWLEDGED`, and required success-delivery rows. Immediately deliver snapshot then `OrderPlacedEvent` through leased durable checkpoints; on restart or same-key replay, resume unfinished delivery without placing again. Router production remains unchanged because current durable reservation and replay-adoption tests already provide the no-duplicate exchange boundary.

### 2. Files to change

Primary-owned tests/lifecycle artifacts:

- `app/engine/tests/unit/test_router_execution_subscriber.py`
- `app/engine/tests/unit/test_execution_intents_adapter.py`
- `app/engine/tests/integration/test_execution_intent_success_boundary.py` (new)
- this Coding Log and `.codex/coding-log.current`

Luna-Max production allowlist:

- `app/engine/execution/router_execution_subscriber.py`
- `app/engine/adapters/db/timescale_adapter.py`
- `db/migrations/036_execution_success_delivery.sql` (new)

Protected from production delegation: all tests, Coding Logs, `.codex`, router/BFF/UI code, `app/engine/main.py`, Compose/config/env files, and every other path.

### 3. Implementation steps

#### TDD slice S1: atomic ACK/projection failure boundary

1. Replace the defective ACK-failure test and add adapter rollback tests.
2. RED command: `pytest app/engine/tests/unit/test_router_execution_subscriber.py -q -k 'ack_commit_failure'` plus adapter/integration targets as authored.
3. Confirm current code fails because it calls snapshot/event and leaves order rows before ACK failure.
4. Snapshot exact production allowlist for Luna-Max.
5. Luna adds `_upsert_order_with_connection(...)`, `commit_execution_ack(...)`, and `_build_order_projection_rows(...)`; ACK transaction seeds required delivery rows.
6. Primary verifies ownership receipt, complete diff, scoped GREEN, and real rollback evidence.

#### TDD slice S2: same-key placement recovery

1. Add stateful replay test proving identical router payload/IDs, two engine calls, and one simulated exchange placement.
2. Add adapter test for same-hash intent lookup and divergent-key rejection.
3. RED must show cooldown/duplicate guard or current intent handling blocks safe recovery.
4. Luna adds `get_execution_intent_for_request(...)` and branches by durable state:
   - missing/PREPARED: normal duplicate guard, cooldown, prepare, submit;
   - SUBMITTING/AMBIGUOUS: bypass duplicate/cooldown reacquisition and replay exact router request;
   - ACKNOWLEDGED with pending rows: skip router/projection and resume delivery;
   - ACKNOWLEDGED with no pending rows: idempotent no-op;
   - REJECTED/hash conflict/DB uncertainty: fail closed.
5. Primary reruns existing Go replay tests; no router production edit is allowed unless a new RED proves a router defect.

#### TDD slice S3: leased replayable success delivery

1. Add snapshot failure, event failure, checkpoint replay, expired-lease, and concurrent-claim tests.
2. RED confirms current code demotes delivery failures to ambiguity and repeats prior effects.
3. Luna adds adapter APIs:
   - `claim_execution_success_delivery(...)`: atomically lease one eligible row; ORDER_PLACED is ineligible until SNAPSHOT is delivered when snapshot is required.
   - `complete_execution_success_delivery(...)`: token-guarded `DELIVERING -> DELIVERED`.
   - `fail_execution_success_delivery(...)`: token-guarded return to `PENDING`, attempts/error retained.
   - `has_pending_execution_success_delivery(...)`: determine final completion/no-op.
4. Luna adds `_resume_success_delivery(...)`:
   - BFF absent means no SNAPSHOT row was seeded;
   - BFF response succeeds only when it is a mapping with `ok is True`;
   - event succeeds only when `publish_and_wait()` returns true;
   - failure emits `success_delivery_pending` and leaves ACK durable;
   - success log occurs once, only when the final required row transitions to delivered in this invocation.
5. External delivery remains explicitly at-least-once across the crash-after-effect/before-checkpoint window. Stable snapshot identity and event UUID are mandatory; downstream dedupe is not claimed by this PR.

#### Migration behavior

`036_execution_success_delivery.sql` creates:

- `execution_success_deliveries(venue, idempotency_key, delivery_kind, state, attempts, lease_token, lease_expires_at, last_error, created_at, updated_at, delivered_at)`.
- Composite primary key `(venue,idempotency_key,delivery_kind)`.
- Composite foreign key to `execution_intents` with cascade delete.
- Checks for `delivery_kind IN ('SNAPSHOT','ORDER_PLACED')`, `state IN ('PENDING','DELIVERING','DELIVERED')`, coherent lease fields, nonnegative attempts, and delivered timestamp coherence.
- Partial claim index on pending/delivering rows.
- Backfill policy: existing `ACKNOWLEDGED` intents receive a delivered `ORDER_PLACED` row (and no snapshot row), preventing historical replay. New ACK transactions seed `SNAPSHOT` only when BFF is configured and always seed `ORDER_PLACED`.
- Grants mirror `execution_intents`.

Migration is additive and applied before engine code. Backout rolls the engine back while retaining the unused table; do not drop evidence-bearing rows during emergency rollback.

### 4. Test coverage

`test_router_execution_subscriber.py`:

- `test_ack_commit_failure_has_no_success_effects_and_retains_ambiguous_replay`: no success crosses failed transaction.
- `test_same_key_replay_after_ack_commit_failure_recovers_success_once`: router replay uses stable identity once.
- `test_acknowledged_pending_replay_skips_router_and_projection`: durable ACK resumes effects only.
- `test_snapshot_failure_leaves_acknowledged_delivery_pending`: snapshot failure never becomes ambiguous.
- `test_pending_order_event_replay_does_not_repeat_snapshot`: checkpoint ordering survives retry.
- `test_delivered_execution_replay_is_noop`: completed success has no duplicate effects/log.
- `test_success_log_occurs_only_after_all_delivery_rows_complete`: log matches durable delivery completion.

`test_execution_intents_adapter.py`:

- `test_commit_execution_ack_uses_one_transaction`: projection/ACK/delivery rows share connection.
- `test_commit_execution_ack_rolls_back_when_guard_rejects_state`: zero-row ACK update raises.
- `test_get_execution_intent_for_request_accepts_matching_acknowledged`: delivery replay can load response.
- `test_get_execution_intent_for_request_rejects_hash_conflict`: divergent same key fails closed.
- `test_claim_delivery_enforces_snapshot_before_order_event`: SQL prevents reordered effects.
- `test_delivery_completion_requires_matching_lease`: stale worker cannot complete another claim.

`test_execution_intent_success_boundary.py`:

- `test_ack_commit_rolls_back_all_projection_rows_when_any_leg_fails`: PostgreSQL proves atomic rollback.
- `test_ack_commit_persists_orders_ack_and_deliveries_atomically`: all durable state appears together.
- `test_concurrent_delivery_claim_has_one_winner`: database lease elects one owner.
- `test_expired_delivery_lease_is_reclaimable`: restart recovers abandoned claim.

Retain and rerun router evidence:

- `TestLostResponseReplayPlacesEntryOnce`
- `TestPlaceBracketOrder_ReplayWithAllLegsLiveAdoptsEverything`
- divergent-replay and durable-reservation tests.

### 5. Decision completeness

Goal:

- No engine success effect or projection is visible unless ACK and the entire projection commit durably.
- Post-ACK snapshot/event delivery is recoverable and safely claimable.
- Same-key replay cannot create a second exchange entry.

Non-goals:

- No router, BFF, UI, alert-consumer, event-bus, Compose, config, or environment production changes.
- No autonomous background dispatcher in this PR.
- No global exactly-once claim.
- No readiness or U8-U14 work in this PR.

Measurable success criteria:

- Forced transaction failure leaves zero new order rows, zero delivery rows, no ACK, no BFF call, no `OrderPlacedEvent`, and no success log.
- Failure records `AMBIGUOUS`; if that write also fails, prior durable `SUBMITTING` remains and is accepted for replay.
- Same-key replay sends byte-for-byte equivalent logical router request and stable IDs; router production tests prove one exchange entry placement/adoption.
- Durable ACK replay never calls router or rewrites projections.
- Snapshot is checkpointed before event; concurrent claims have one winner; expired leases recover.
- Delivery failure leaves ACK plus pending row and emits `success_delivery_pending`.
- All scoped/full gates, three repeats, wiring checks, QCHECK, and formal `g-check` pass.

Public interfaces:

- Database: additive table in migration `036`.
- Internal Python APIs: intent load, atomic ACK commit, delivery claim/complete/fail/pending queries.
- No external endpoint, message topic/schema, CLI flag, or environment variable changes.

Edge cases/failure modes:

- DB read/hash conflict before router: fail closed, no placement.
- PREPARED persistence failure: fail closed and release newly acquired cooldown.
- Transport/HTTP ambiguity after SUBMITTING: mark AMBIGUOUS, retain cooldown.
- Nonretryable router rejection: REJECTED, retain placement audit.
- Any projection or ACK write failure: transaction rollback; no success effects; AMBIGUOUS recovery.
- Concurrent ACK commits: guarded state permits one winner; loser reloads ACK and may resume delivery rather than overwrite state.
- Snapshot missing/unconfigured: no snapshot delivery row; event remains required.
- Snapshot response absent or `ok != true`: delivery returns pending.
- Event bus false/exception: event row returns pending; snapshot stays delivered.
- Crash after external effect before checkpoint: lease expiry permits at-least-once retry with stable identity.
- REJECTED or divergent replay: fail closed before router.

Rollout and monitoring:

- Apply migration first, deploy engine code second, keep trading halted during migration/startup verification, then restore only through existing execution-control procedure.
- Watch `execution_success_deliveries` pending age, attempts, expired leases, `success_delivery_pending`, ACK commit errors, and AMBIGUOUS count.
- Backout engine code without dropping migration/table; retain records for recovery/forensics.
- No deployment or activation is authorized by source merge alone; later runtime qualification remains a separate attachment item.

Acceptance commands and expected outcomes:

- `pytest app/engine/tests/unit/test_router_execution_subscriber.py -q`: all subscriber tests pass.
- `pytest app/engine/tests/unit/test_execution_intents_adapter.py -q`: SQL contract fakes pass.
- `pytest app/engine/tests/integration/test_execution_intent_success_boundary.py -q`: real DB atomicity/lease tests pass or explicitly report missing integration prerequisite; absence is not accepted as source-completion evidence if canonical CI requires it.
- `pytest app/engine/tests/integration/test_router_execution_contract.py -q`: engine/router typed seam stays green.
- `cd app/router && go test ./internal/orders ./internal/storage -count=1`: replay evidence stays green.
- `make test-engine`, `make lint`, `make typecheck`, `make format-check`, `make ci`: prescribed full gates pass.
- Re-run the affected pytest scope three consecutive times without flake.

### 6. Dependencies

- Python engine virtualenv/dependencies.
- PostgreSQL test database migrated through `036`.
- Existing router durable bracket store and replay-adoption implementation.
- Existing BFF internal alert endpoint and event bus; their downstream exactly-once behavior is not assumed.
- Functional shell/test runner. The current session's Code Mode host is missing; implementation cannot be accepted until primary-owned executable RED/GREEN and final gates run.

### 7. Validation

Primary will author tests, confirm legitimate RED, create an exact production allowlist ownership snapshot, and delegate one sequential GREEN/remediation slice at a time to registered `luna_implementer` (`gpt-5.6-luna`, max). After each receipt, primary will validate hashes/HEAD/protected paths, inspect the complete diff, rerun scoped GREEN, and verify wiring. Final validation includes full gates, three repeats, skeptical QCHECK, formal `g-check`, PR head/check/mergeability verification, authorized admin merge, exact-SHA local-main landing, post-merge verification, and safe worktree closeout.

### 8. Wiring verification

| Component | Non-test call site | Registration/config load | Schema/contract match |
|---|---|---|---|
| `commit_execution_ack` | `RouterExecutionSubscriber._execute_decision()` immediately after typed `validate_bracket_placement()` | Existing `TimescaleDBAdapter` injection in `app/engine/main.py:initialize_services()` | `orders`; `execution_intents.state/response_payload`; `execution_success_deliveries` |
| `get_execution_intent_for_request` | subscriber before duplicate/cooldown/router branching | Same adapter injection | request hash algorithm must match `prepare_execution_intent` |
| `_resume_success_delivery` | immediate post-ACK and ACKNOWLEDGED same-key replay | Existing subscriber registered on `EventType.TRADING_DECISION` | `SNAPSHOT` then `ORDER_PLACED`; deterministic event UUID |
| Delivery claim/complete/fail | `_resume_success_delivery` | no new runtime service | leased rows in `execution_success_deliveries` |
| Migration `036` | DB migration before engine start | existing migration sequence | FK to `execution_intents(venue,idempotency_key)` and grants to `trading_user` |
| Router replay evidence | engine stable `/place_bracket` request | existing router route in `app/router/cmd/router/main.go` with durable `BracketRepo` | router `brackets(venue,idempotency_key,request_hash)` |

Every new production symbol must have the named non-test consumer. No new startup registration is permitted in this slice.

### 9. Cross-language schema verification

- Engine Python reads/writes `execution_intents` and `orders` in `TimescaleDBAdapter`.
- Migration 034 defines `execution_intents`; migration 006/related migrations define `orders`; migration 035 is the current ceiling.
- Router Go uses `brackets` and `bracket_legs`; `BracketRepo.Reserve()` keys on venue/idempotency and canonical request hash.
- Router handler `/place_bracket` is registered in `app/router/cmd/router/main.go` and active startup requires the durable store.
- Migration `036` is engine-only and does not rename or reinterpret Go-owned tables.

### 10. Decision-complete checklist

- [x] No open behavior or architecture decision remains for Luna.
- [x] Every changed public/internal interface is named.
- [x] Every behavior change has a defect-sensitive test.
- [x] Validation commands are specific and scoped.
- [x] Wiring covers migration, adapter APIs, subscriber, and router replay evidence.
- [x] Rollout/backout and observability are specified.
- [x] External delivery is honestly at-least-once, not misclaimed exactly-once.
- [x] Production allowlist and protected paths are exact.

## Planning disposition

Unified plan selected. Draft A was rejected because simple intent columns do not cleanly support concurrent leased delivery. Draft B was narrowed because a new background dispatcher and durable payload-versioning contract are unnecessary for the first pickup item. The selected plan uses normalized leased checkpoint rows, immediate/replay-driven delivery, atomic ACK/projection persistence, and unchanged router production.

## RED attempt (2026-08-22 Asia/Bangkok) - S1 atomic ACK/projection boundary

### Primary-authored tests

- Replaced `test_ack_persistence_failure_replay_uses_stable_success_event_id`, which codified premature duplicate success, with `test_ack_commit_failure_has_no_success_effects_and_retains_ambiguous_replay`.
- Added `test_commit_execution_ack_uses_one_transaction`.
- Added `test_commit_execution_ack_rolls_back_when_guard_rejects_state`.
- Production files remain unmodified; test scaffolding exposes the locked `commit_execution_ack(..., order_rows, delivery_kinds)` contract.

### Exact RED command attempted

`./app/engine/.venv/bin/pytest app/engine/tests/unit/test_router_execution_subscriber.py app/engine/tests/unit/test_execution_intents_adapter.py -q -k 'ack_commit_failure or commit_execution_ack'`

### Result

Pytest did not start. The primary command runner failed first with:

`failed to spawn code-mode host /opt/homebrew/Caskroom/codex/0.148.0/bin/codex-code-mode-host: No such file or directory (os error 2)`

This is not accepted as RED. Read-only installation inspection proved Homebrew currently contains `/opt/homebrew/Caskroom/codex/0.149.0/bin/codex` and `/opt/homebrew/Caskroom/codex/0.149.0/bin/codex-code-mode-host`; the active Codex process retained the removed 0.148.0 path. A fresh Codex session is required to bind the current host. No Homebrew shim or binary move was made.

### Lifecycle disposition

- Luna-Max production delegation has not started because expected RED is not executable yet.
- No ownership snapshot or receipt exists yet.
- No production code, commit, push, PR, merge, deployment, or activation occurred.
- Worktree is intentionally retained clean of production changes so the persistent goal can resume after restart.

## Resumed RED confirmation (2026-08-22 21:58:28 +07)

The fresh session restored a working command runner. The retained worktree remained at baseline
`9ecd69dcd920b3ab2bb759559841c29e5a2fbb26` with only primary-owned tests, Coding Log, and pointer
changes; no production file had changed.

### Executable RED

- Exact command: `'/Users/subhajlimanond/dev/online trader/app/engine/.venv/bin/pytest' app/engine/tests/unit/test_router_execution_subscriber.py app/engine/tests/unit/test_execution_intents_adapter.py -q -k 'ack_commit_failure or commit_execution_ack'`
- Result: `3 failed, 43 deselected` in 0.13 seconds.
- Expected defects observed:
  - the subscriber never called the locked `commit_execution_ack(...)` boundary and still emitted
    `Order placed successfully` through the old success path;
  - `TimescaleDBAdapter` had no `commit_execution_ack(...)` API, so both transaction-contract tests
    failed with `AttributeError`.

### Real-database RED contract

- Added primary-owned `app/engine/tests/integration/test_execution_intent_success_boundary.py`.
- It locks real PostgreSQL rollback and successful atomic visibility for orders, ACK response/state,
  and required delivery rows.
- Ruff format/check passed for the new test file.
- Exact integration command: `'/Users/subhajlimanond/dev/online trader/app/engine/.venv/bin/pytest' app/engine/tests/integration/test_execution_intent_success_boundary.py -q -m integration`.
- Result: infrastructure-only failure before test execution because the default local PostgreSQL
  instance lacks role `trading_user`. This is not counted as RED; the retained isolated TimescaleDB
  container on host port 55432 will be used for GREEN database evidence after migration 036 exists.

### Refreshed discovery and S1 allowlist

RepoPrompt Context Builder reconfirmed that S1 requires exactly these production paths:

- `app/engine/execution/router_execution_subscriber.py`
- `app/engine/adapters/db/timescale_adapter.py`
- `db/migrations/036_execution_success_delivery.sql`

No router, BFF, UI, startup, bus, model, configuration, environment, or existing-migration edit is
required. S1 remains limited to atomic projection/ACK/delivery-row persistence before external
effects; S2 replay lookup and S3 leased delivery processing remain separate TDD slices.

## S1 GREEN acceptance (2026-08-22 22:14:13 +07)

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-s1.nqa1Ml/snapshot-final.json`, SHA-256
  `fb2f16c43b0c430651e776464caf5356bcfd237cdd8211a93477ee6bd6c93b6d`.
- Receipt: `/tmp/online-trader-s1.nqa1Ml/receipt.json`.
- Primary ownership verification: `verified: true`; HEAD remained
  `9ecd69dcd920b3ab2bb759559841c29e5a2fbb26`; exactly the three allowlisted production paths
  changed and receipt hashes matched.
- Primary scoped GREEN: `3 passed, 43 deselected` in 0.06 seconds.
- Primary PostgreSQL GREEN with the isolated TimescaleDB container on host port 55432: `2 passed`
  in 0.34 seconds, proving rollback of the first projection when a later leg violates a real check
  constraint and atomic visibility of projections, ACK response/state, and delivery rows.
- Wiring: existing `main.initialize_services()` injects the adapter into the subscriber; the
  subscriber invokes the atomic commit immediately after typed ACK validation; migration discovery
  automatically applied additive migration 036. No new runtime registration was added.

## S2 RED - same-key placement recovery

### Locked contract

- Load and hash-verify any existing `(venue,idempotency_key)` intent before ordinary duplicate and
  cooldown rejection.
- `SUBMITTING` and `AMBIGUOUS` same-hash attempts are recovery: bypass duplicate/cooldown
  reacquisition, reuse the exact stored request payload/client IDs, transition to SUBMITTING, and
  call the router with that immutable payload.
- Router may receive the same request again; existing durable router reservation/adoption tests are
  the exchange-level one-placement oracle.
- Missing/PREPARED remains the normal path. REJECTED, ACKNOWLEDGED in this S2 slice, hash conflict,
  or database uncertainty fails closed before router access. S3 will make ACKNOWLEDGED resume
  delivery rather than fail.

### Primary-authored tests and expected RED

- `test_same_key_replay_after_ack_commit_failure_recovers_success_once` locks two identical router
  requests, two atomic commit attempts (fail then succeed), one snapshot, one OrderPlacedEvent, one
  success log, and AMBIGUOUS then ACKNOWLEDGED durable transitions.
- `test_get_execution_intent_for_request_accepts_matching_ambiguous` locks the adapter load shape.
- `test_get_execution_intent_for_request_rejects_hash_conflict` locks fail-closed divergent reuse.
- Exact RED command: `'/Users/subhajlimanond/dev/online trader/app/engine/.venv/bin/pytest' app/engine/tests/unit/test_router_execution_subscriber.py app/engine/tests/unit/test_execution_intents_adapter.py -q -k 'same_key_replay_after_ack_commit_failure or get_execution_intent_for_request'`.
- Result: `3 failed, 46 deselected` in 0.12 seconds. The subscriber made zero intent lookups, and
  the adapter lacked `get_execution_intent_for_request(...)`; these are the intended missing
  behaviors. Ruff format/check passed on the primary-owned test files.

## S2 GREEN acceptance (2026-08-22 22:27:43 +07)

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-s2.SloibR/snapshot.json`, SHA-256
  `72ceacededdebe269f233af5ef97556ddbd4ea4a0f626c7a29b796887d84eab4`.
- Receipt: `/tmp/online-trader-s2.SloibR/receipt.json`.
- Primary ownership verification passed with exact two-file allowlist, matching hashes, protected
  test/log state, and unchanged HEAD.
- Primary scoped GREEN: `3 passed, 46 deselected` in 0.06 seconds.
- Unchanged router exchange-replay oracle passed:
  `go test ./internal/orders -run 'TestLostResponseReplayPlacesEntryOnce|TestPlaceBracketOrder_ReplayWithAllLegsLiveAdoptsEverything|TestIdempotencyKeyPayloadConflict' -count=1`.
- Wiring remains the existing subscriber/adapter injection. Same-hash SUBMITTING/AMBIGUOUS
  recovery now reuses the stored request before ordinary duplicate/cooldown rejection; router
  durable reservation remains exchange-authoritative.

## S3 RED - leased replayable success delivery

### Locked contract

- Claim the next delivery obligation atomically with a 60-second lease. SNAPSHOT precedes
  ORDER_PLACED; ORDER_PLACED is ineligible while a required SNAPSHOT is not DELIVERED.
- Concurrent claimers have one winner. Expired DELIVERING rows are reclaimable. Completion and
  failure updates require the exact lease token; stale workers cannot mutate another claim.
- Snapshot succeeds only when the BFF response is a mapping with `ok is True`. Event succeeds only
  when `publish_and_wait()` returns true.
- Failure returns the claimed row to PENDING with attempts/error retained, emits
  `success_delivery_pending`, keeps the intent ACKNOWLEDGED, and logs no placement success.
- ACKNOWLEDGED same-hash replay skips router/projection and resumes pending delivery. A completed
  replay is a no-op. Success logging occurs only when this invocation completes the final required
  delivery row.
- Crash after an external effect but before checkpoint remains honestly at-least-once; stable
  snapshot identity and deterministic OrderPlacedEvent UUID are retained.

### Primary-authored RED evidence

- Replaced the stale pre-S1 test with
  `test_order_event_failure_leaves_acknowledged_delivery_pending`.
- Added snapshot-failure, event-only replay, and delivered-no-op subscriber tests.
- Added unit SQL contracts for snapshot-first claiming and token-guarded completion.
- Added real PostgreSQL tests for one concurrent lease winner and expired-lease reclamation.
- Targeted unit RED initially produced five expected failures and one insufficiently constrained
  pass; the delivered replay test was strengthened to require durable DELIVERED rows and no error,
  and then failed on the current PENDING state as expected.
- PostgreSQL RED: `2 failed, 2 deselected`; both failures were the missing
  `claim_execution_success_delivery(...)` API.
- Ruff format/check passed for all primary-owned S3 test files.

## S3 GREEN acceptance (2026-08-22 22:39:50 +07)

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-s3.XdOdQS/snapshot.json`, SHA-256
  `3b9f9722cfd6a6c0d4285507bc91c9fe5b3c50976d46796c8a2cc5ced45e8332`.
- Receipt: `/tmp/online-trader-s3.XdOdQS/receipt.json`.
- Primary ownership verification passed with exact two-file allowlist, matching hashes, protected
  test/log state, and unchanged HEAD.
- Primary affected unit GREEN: `54 passed`.
- Primary real PostgreSQL success-boundary GREEN: `4 passed` in 0.43 seconds, including one
  concurrent claim winner and expired-lease reclamation.
- Updated three pre-existing test doubles for the new durable adapter contract; their compatibility
  scope passed `16/16`.
- Complete affected unit/integration scope passed three consecutive times: `74 passed` in 0.61,
  0.54, and 0.53 seconds.

### Full and cross-component gates

- Full engine non-integration suite: `1689 passed, 2 skipped, 44 deselected, 1 failed`. The sole
  failure is the untouched Redis `mset(dict[str,str])` MyPy assertion at `redis_adapter.py:717`.
  The exact test reproduces on protected local `main`.
- Engine Ruff lint: passed.
- Full engine Ruff format check reports the same four untouched files on candidate and protected
  `main`: `redis_adapter.py`, `error_handling.py`, `pipeline_health_service.py`, and
  `retest/__init__.py`.
- Full engine MyPy reports the same two untouched errors on candidate and protected `main`:
  `pipeline_health_service.py:170` and `redis_adapter.py:717`.
- Router `go test ./... -count=1`, `go vet ./...`, and `go build ./...`: passed.
- Migration 036 applied through the normal migration runner against the isolated TimescaleDB test
  database; atomicity and lease behavior passed on PostgreSQL.

### Final wiring evidence

| Component | Non-test call site | Registration/config load | Schema/contract match |
|---|---|---|---|
| Atomic projection/ACK commit | `RouterExecutionSubscriber._execute_decision()` after typed ACK | Existing `TimescaleDBAdapter` injection in `main.initialize_services()` | `orders`, `execution_intents`, migration 036 delivery rows |
| Existing-intent replay lookup | subscriber before duplicate/cooldown/router branching | Same adapter injection | current request hash verified against durable request payload |
| Success delivery resume | immediate post-ACK and ACKNOWLEDGED replay branch | Existing `TRADING_DECISION` subscriber; no new service | SNAPSHOT then ORDER_PLACED, 60-second lease |
| Delivery claim/complete/fail | `_resume_success_delivery()` | Existing adapter; no startup registration | exact lease token and state guards |
| Migration 036 | normal DB migration discovery before engine startup | Existing migration runner | composite FK to execution_intents; trading_user CRUD grant |
| Router replay authority | unchanged `/place_bracket` call with stored payload | Existing durable router store/control wiring | `(venue,idempotency_key,request_hash)` adoption tests pass |

Source merge remains distinct from deployment or activation. No runtime deployment, resume, or
live-small action is authorized by this lifecycle.

## Independent QCHECK (2026-08-22 22:47:03 +07)

The read-only Terra QCHECK reported three findings. The primary accepted all three.

### P1 - ACK delivery replay blocked by submission-only gates

- Finding: current risk/readiness checks run before the durable intent lookup, so a risk database or
  ingest-readiness outage can block ACKNOWLEDGED snapshot/event recovery even though that path does
  not submit to the router.
- Locked remediation: construct/hash the canonical request and handle only ACKNOWLEDGED replay
  before live pre-trade gates. Missing/PREPARED/SUBMITTING/AMBIGUOUS/REJECTED behavior remains
  downstream of the existing submission gates; no risk policy is weakened for exchange access.
- Primary RED:
  `test_acknowledged_replay_resumes_delivery_when_live_risk_is_unavailable`.
- Result: expected failure because the risk snapshot returned early and BFF delivery was never
  called. The companion snapshot-ordering test passed.

### P2 - snapshot-ordering test false positive

- Finding: the test BFF returned `{"success": true}` while production requires `{"ok": true}`, and
  its bus labeled every event as an order event.
- Disposition: fixed the primary-owned test to return `{"ok": true}`, record event objects, require
  an actual `OrderPlacedEvent`, and reject any `ErrorEvent`. The corrected test passes.

### P2 - missing stale-lease PostgreSQL proof

- Finding: reclaim was covered but stale-worker completion after reclaim was not.
- Disposition: added `test_stale_delivery_lease_cannot_complete_reclaimed_work`. PostgreSQL GREEN
  proves stale token A raises and cannot alter active lease B; only B completes the row. Result:
  `1 passed, 4 deselected`.

## R1 GREEN - ACK replay gate ordering

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Primary ownership verification passed for the bounded subscriber-only remediation.
- ACKNOWLEDGED same-hash replay now resumes durable success delivery without consulting live
  submission readiness or risk. All paths that could submit to the router retain the existing
  readiness and risk gates.
- Primary targeted GREEN and the complete affected three-repeat gate passed.

## Formal g-check review and R2 remediation

The first formal review accepted four blockers: no restart drain, BFF snapshot payload mismatch,
unsafe adoption of a conflicting existing order projection, and cross-venue downstream identity
collisions. It also requested stronger queue-acceptance and migration coverage.

- R2 Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r2.9WzAJM/snapshot.json`, SHA-256
  `95b945dd9d228b9b3e0ab5f9c617f4d2f78ffed698b3f1f02be26bc498a8c9f3`.
- Receipt: `/tmp/online-trader-r2.9WzAJM/receipt.json`.
- Primary ownership verification passed for the exact five-file production allowlist.
- R2 added payload-bearing outbox rows, a supervised restart worker, insert-or-validate ACK
  projections, the BFF numeric snapshot DTO/fallbacks, venue-scoped snapshot/event identity, and
  startup ordering that makes the BFF available before delivery drain.
- Primary affected gate passed three times (`88` engine tests plus `8` PostgreSQL integration
  tests); focused and full BFF tests, typecheck, lint, Prettier, changed-file Ruff, router tests/vet/
  build, and `git diff --check` passed. The full-engine baseline exceptions remain identical to
  protected `main` and are recorded above.

## R3 RED - restart liveness, disabled recovery, alert acknowledgement, and provenance

The same formal-review conversation re-reviewed R2 and found that a poison oldest delivery could
starve unrelated keys, recovery was absent in disabled mode and only covered one venue, provenance
adoption did not validate/enrich timeframe and zone, and an active lease could emit a false pending
error. Primary wiring inspection also found no production subscriber for `OrderPlacedEvent`, so
`publish_and_wait()` could not acknowledge the durable event in the real application.

### Locked contract

- Persist `next_attempt_at`; failed claims receive capped exponential backoff with jitter. Global
  claiming selects the oldest due row, using delivery kind only as a same-key tie-breaker, while the
  existing dependency rule keeps SNAPSHOT before ORDER_PLACED for one key.
- Always construct/start the execution subscriber. In disabled mode it starts one recovery worker
  for each of `SPOT` and `USD_M`, but performs no router probe, decision subscription, or placement.
- Claims carry their venue and completion/failure use that claimed venue.
- Both alert modes subscribe to enriched `OrderPlacedEvent`; the handler routes its decision to
  Telegram without posting a second snapshot to BFF. This is the real acknowledged consumer.
- Existing null decision/signal/timeframe/zone provenance is enriched. Divergent non-null values
  fail the atomic ACK transaction as an identity conflict.
- ACK replay with a currently active delivery lease is quiet; real effect failures still emit the
  pending error.

### Primary-authored RED evidence

- Alert contract: four expected failures for missing ORDER_PLACED registration/handling; the
  independent STOP_MARKET characterization passed, proving current ingestion normalizes it to
  canonical STOP_LOSS before projection.
- Disabled/main/active-lease contract: three expected failures (subscriber absent in disabled
  wiring, unsupported multi-venue recovery configuration, and false ErrorEvent).
- PostgreSQL contract: missing `next_attempt_at`, missing timeframe/zone enrichment, and missing
  divergent-provenance rejection each failed at its intended boundary. The enrichment fixture was
  corrected to seed its referenced trading decision before locking this RED.
- Migration 036 is uncommitted and has never shipped; compatibility with an earlier local draft is
  not a release upgrade obligation. The final migration remains required to apply from pre-036 and
  rerun safely.

## R3 GREEN - fair recovery and acknowledged placement delivery

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r3.hc42PD/snapshot.json`, SHA-256
  `feda74faa42fe4542129d6bb9c3ca4f740288c9020404c45f7b32db1cff79767`.
- Receipt: `/tmp/online-trader-r3.hc42PD/receipt.json`, SHA-256
  `7bc5abf3011b9581e95dcf63499d168eacbe2275af28ee1c2acba08d58effe40`.
- Primary ownership verification passed for the exact five-file production allowlist.
- Targeted unit/characterization tests passed; the affected engine gate passed three times
  (`179` unit plus `11` PostgreSQL tests on every run).
- Full non-integration engine gate passed (`1698 passed, 2 skipped, 44 deselected`), apart from
  the already-recorded protected-main Redis MyPy characterization. BFF, router, Ruff, and
  diff-check gates passed with only the unchanged protected-main format/MyPy exceptions.

## Formal g-check R4 findings and locked RED (2026-08-23 00:30:34 +07)

The same formal-review conversation found five remaining issues. The primary accepted all five.

### P1 - durable placement had no unconditional production consumer

- Finding: the contract publisher did not subscribe to `OrderPlacedEvent`, while the Telegram
  subscriber is absent when Telegram is not configured. Durable success delivery could therefore
  remain pending despite Redis contract publication being the unconditional production sink.
- Locked RED: registration, exact `order_update.v1` mapping, and real-event-bus acknowledgement.
- Result: three expected failures (missing subscription, missing handler, and rejected real-bus
  dispatch).

### P1 - Telegram failure was falsely acknowledged

- Finding: `AlertSubscriber` swallowed every Telegram exception, so an `OrderPlacedEvent`
  delivery could be checkpointed even though its configured effect failed.
- Locked RED: re-raise only placement-event failures; retain best-effort handling for ordinary
  decision and alert events.
- Result: two expected failures, including real-event-bus dispatch returning true.

### P1 - stop trigger used the limit-price field

- Finding: STOP_MARKET webhook ingestion normalized only the type, leaving the trigger in
  `price`; migration 035 also emitted an SL trigger as `price` without `stop_price`.
- Locked RED: the engine model/contract carries `stop_price`; STOP_MARKET projection stores
  canonical `STOP_LOSS` with `price = NULL` and `stop_price = trigger`; a new forward-only,
  rerunnable migration 037 replaces the shipped trigger function without editing migration 035.
- Result: unit publication and projection fail on missing/wrong `stop_price`; the durable
  PostgreSQL envelope fails specifically at the stop-order constraint; the router migration test
  fails because migration 037 does not yet exist.

### P2 - duplicate execution decision alerts were enabled by default

- Locked RED: `TELEGRAM_EXECUTION_DECISION_ALERTS_ENABLED` defaults off and remains explicitly
  opt-in for `1/true/yes/on`.
- Result: expected default-policy failure; explicit opt-in characterization remains green.

### P2 - concurrent global claim proof

- Added a real PostgreSQL three-claimer test. It proves a dependent key exposes only SNAPSHOT while
  an unrelated ORDER_PLACED progresses, then exposes the dependent ORDER_PLACED after snapshot
  completion. This test passed without production changes.

## R4 GREEN - unconditional publication and canonical stop triggers

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r4.8vDeaX/snapshot.json`, SHA-256
  `ce69378cb85b94022da9a1a88cf7c0f5c3d09a21d81125345b1a05bc4aee8888`.
- Receipt: `/tmp/online-trader-r4.8vDeaX/receipt.json`, SHA-256
  `0a6f8e6ac311c6e74ad95d682255d3dd6d0ebdcab0600e199fcd9e7c0ba85999`.
- Primary ownership verification passed for the exact five-file production allowlist.
- Focused Python tests passed (`116`), the PostgreSQL success-boundary contract passed (`12`),
  and the router stop-trigger migration test passed. The affected Python/PostgreSQL/router gate
  passed three consecutive runs.
- Full engine non-integration tests passed (`1703 passed, 2 skipped, 45 deselected`); full BFF,
  UI under Node 22, router tests/vet/build, workspace typecheck/lint/Prettier, changed-file Ruff,
  direct BFF/Next builds, and `git diff --check` passed. The root build wrapper remains unusable
  because the existing dependency installation lacks the glob/minimatch shape expected by rimraf;
  direct package builds are green.

## Formal g-check R5 findings and locked RED (2026-08-23 00:58:02 +07)

The same formal-review conversation found four remaining issues. The primary accepted all four.

### P1 - ephemeral Redis publication could be checkpointed as durable success

- Finding: `ORDER_PLACED` delivery completed after Redis Pub/Sub publication, including when no
  subscribers received it. Pub/Sub is a live fanout mechanism, not a durable consumer boundary.
- Locked contract: after the existing event-bus effects, post the canonical `order_update.v1`
  payload to authenticated BFF endpoint `/api/internal/trading/order-update`; complete the ledger
  only when BFF returns `{ ok: true }` after matching and persisting the existing order projection.
  The direct durable-acceptance method updates repository/cache but does not emit a websocket event;
  the existing Pub/Sub handler reuses it and remains the sole live-event emitter.
- RED evidence: the engine delivery test expected `False`, no checkpoint, the exact endpoint and
  failure message when BFF returns `{ ok: false }`, but current code returned `True`. BFF tests fail
  at compile time because `TradingService.acceptOrderUpdate` and `InternalTradingController` do not
  exist; these are the intended missing production contracts.

### P1 - enabled recovery drained only the active placement venue

- Finding: enabled futures mode created a recovery worker only for `USD_M`, allowing committed SPOT
  delivery backlog to remain stranded after a mode switch.
- Locked contract: success-delivery recovery always covers both `SPOT` and `USD_M`; execution mode
  continues to govern router probing, decision subscription, and new placement only.
- RED evidence: enabled wiring exposed only `USD_M`; the multi-venue restart test also proves both
  order events require durable BFF acceptance.

### P2 - legacy stop replay emitted a non-canonical event

- Finding: pre-037 STOP_MARKET payloads were canonicalized for the database row but the bus event
  retained `price = trigger` and `stop_price = null`.
- Locked contract: canonicalize the parsed update before both projection and event construction so
  STOP_MARKET uses `price = null`, `stop_price = trigger` throughout.
- RED evidence: the projection assertions passed while the bus-event assertions failed on those two
  fields, isolating the missing event canonicalization.

### P2 - repeated subscriber start orphaned workers

- Finding: calling `start()` twice subscribed twice and overwrote recovery-task references.
- Locked contract: `start()` is idempotent and `stop()` cancels every recovery worker it owns.
- RED evidence: the focused test observed two `router-execution` subscriptions instead of one.

### R5 focused RED command

- Engine: `10` intended failures across wiring, canonical stop replay, idempotent startup, durable
  BFF acceptance, multi-venue recovery, and successful replay path expectations.
- BFF: two intended TypeScript compile failures for the absent public durable-acceptance method and
  absent internal controller.

## R5 GREEN - durable BFF acceptance and restart-complete recovery

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r5.dCLKZI/snapshot.json`, SHA-256
  `0ab87d53040391adc9acf309b1c3acdc042de2d447eb3e77b9eef4251320cf3c`.
- Receipt: `/tmp/online-trader-r5.dCLKZI/receipt.json`, SHA-256
  `90aab032a4770c301a3c270bc576aa11392a8e57c72d584ea638e5dc8192278f`.
- Primary ownership verification passed for the exact six-file production allowlist; protected
  state and baseline HEAD `9ecd69dcd920b3ab2bb759559841c29e5a2fbb26` were unchanged.
- `RouterExecutionSubscriber` startup is idempotent, owns/cancels every recovery worker, and drains
  both venues in all execution modes. STOP_MARKET webhook replay now constructs its database row and
  bus event from the same canonical parsed update.
- ORDER_PLACED delivery retains acknowledged event-bus effects, then requires authenticated BFF
  persistence through `/api/internal/trading/order-update`; Redis Pub/Sub alone cannot checkpoint
  the delivery. BFF direct acceptance updates the durable projection/cache without duplicate live
  websocket emission, while the existing Pub/Sub callback remains the sole live-event emitter.

### Primary verification (2026-08-23 01:15:32 +07)

- Focused GREEN: `10` engine tests and `24` BFF tests passed.
- Affected gate passed three consecutive settled-candidate runs: `194` engine unit tests, `13`
  real-PostgreSQL integration tests, and `24` focused BFF tests on every run.
- Full engine non-integration gate passed through the repository virtualenv: `1706 passed, 2
  skipped, 44 deselected`. A system-Python attempt was superseded because that interpreter lacks the
  repository's matplotlib dependency.
- Full BFF: `46` suites / `389` tests passed. Jest retains the repository's known open handle after
  completion, so the final bounded run used `--forceExit` after the complete passing result.
- Full UI under Node 22: `97` files / `1380 passed, 1 skipped`; typecheck, lint, Prettier, and
  optimized Next build passed with only the existing hook/font/workspace-root warnings.
- Router `go test ./...`, `go vet ./...`, and `go build ./...` passed. Python Ruff, focused Makefile
  MyPy, BFF ESLint/Prettier/direct build, contract synchronization, changed-file Ruff format,
  gofmt, and `git diff --check` passed.
- The repository-local `turbo` command remains unavailable, so the native workspace scripts and
  direct package builds are the executable TypeScript gates.

## R6 RED - formal-review remediation contract

Formal g-check blocked R5 on replay monotonicity, exchange-identity provenance, mandatory durable
delivery configuration, subscriber lifecycle races, and a suspected multi-subscriber acknowledgement
gap. Primary and independent Terra inspection refined those findings before production handoff:

- The event bus already requires at least one successful handler and zero failed handlers. Combined
  real-bus tests prove Redis success plus Telegram failure and Telegram success plus Redis failure
  both reject acknowledgement, so that suspected production gap is closed by characterization only.
- The router's `bracket_order_id` is a router-generated correlation UUID, not authoritative exchange
  identity. The initial placement update therefore carries an empty `order_id`; BFF preserves the
  projection's existing exchange ID, while later real router updates may supply the exchange ID.
- Durable BFF acceptance must validate immutable venue, symbol, side, type, quantity, and decision
  identity; keep terminal states terminal; never reduce filled quantity or its authoritative average
  fill price; and return/cache the effective persisted state after replay.
- Reconciliation must execute under a PostgreSQL pessimistic row lock in one transaction so concurrent
  deliveries cannot both derive updates from stale state.
- Enabled execution requires both BFF URL and internal token, and concurrent start/start or start/stop
  must converge without duplicate subscriptions or orphan recovery workers.

Focused RED evidence on 2026-08-23:

- Engine contract, wiring, and subscriber set: `63 passed`. This confirms the combined-handler,
  mandatory-delivery-config, empty-exchange-ID, and lifecycle-race tests are already satisfied by the
  settled production candidate and need no further engine production edits.
- BFF service/repository set: `12 failed, 21 passed`, plus TypeScript compile errors for the intentionally
  absent `withLockedOrderForUpdate` seam. Failures cover fallback execution-price leakage, terminal
  regression, decreasing partial-fill state, and divergent immutable identity.
- Locked repository seam: `withLockedOrderForUpdate(identity, reconcile)` owns a transaction and
  `pessimistic_write` row lock, applies a synchronous reconciliation result through the transaction
  repository, and returns the effective row with an `updated` flag; a null reconciliation is a no-op.

## R6 GREEN - atomic monotonic BFF reconciliation

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r6.pLbYsR/snapshot.json`, SHA-256
  `903a33b54394b1dd17fd0a1549d3b0f9309069b6b8ca12f21b3fc50c76969236`.
- Receipt: `/tmp/online-trader-r6.pLbYsR/receipt.json`, SHA-256
  `21b97d0c18bff41f9c7c9608fde68aca2a80715d84fb9ceecf9dbf27a78f8926`.
- Primary ownership verification passed for exactly `trading.service.ts` and
  `order.repository.ts`; protected state and baseline HEAD were unchanged.
- Focused delegate GREEN passed `47` BFF tests; Prettier, ESLint, and TypeScript no-emit checks
  passed. Primary receipt verification and complete two-file diff inspection passed.

## R7 RED - live-event delivery race

- Finding: durable HTTP acceptance and Redis live delivery are distinct consumers. If HTTP
  acceptance updates the row before the Redis callback runs, the callback observes an idempotent
  no-op. Suppressing live emission on `updated: false` then loses the only websocket event.
- Locked contract: direct durable acceptance never emits the live event; every successfully matched
  Redis callback emits the effective normalized persisted update once, regardless of whether that
  callback advanced durable state. Reconciliation and position mutation remain idempotent.
- RED evidence: the focused BFF set reported `1 failed, 47 passed`; the sole failure expected the
  Redis callback to emit the already-durable FILLED update after HTTP acceptance won the race, but
  observed zero emissions.

## R7 GREEN - preserve live delivery after durable-first acceptance

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r7.tIBb79/snapshot.json`, SHA-256
  `f784e9e8a8ecd0552752b0a457ba9724fc360acffecf7d2e3bb8c6a0fdca2600`.
- Receipt: `/tmp/online-trader-r7.tIBb79/receipt.json`, SHA-256
  `b4b7de294c8f77dc09a5db8b0eb15acbdc8b1ec68cff569002d63feb85295015`.
- Primary ownership verification passed for the single allowlisted production file; protected state
  and baseline HEAD were unchanged.
- The live callback now emits every compatible effective update while direct acceptance remains
  non-emitting and durable/position side effects remain no-op safe.
- Delegate and independent primary focused GREEN both passed `48` BFF tests; delegate Prettier,
  ESLint, and TypeScript checks passed.

## R8 RED - corrected worktree execution of engine review contracts

- Correction: the earlier `63 passed` R6 Python note invoked the protected-main test paths because
  its working directory was the primary checkout. It characterized baseline behavior and was not a
  valid candidate GREEN. The primary reran with the repository virtualenv executable while keeping
  the candidate worktree as cwd.
- Correct candidate result: `6 failed, 194 passed`. The failures are exactly the locked behaviors:
  initial durable publication still exposes router `bracket_order_id` as exchange `order_id` in two
  mappings; enabled execution does not reject missing BFF URL/token; concurrent start/start probes
  twice; and concurrent start/stop can finish started with owned workers.
- The BFF focused candidate remained green at `51 passed` in the same gate run.
- Locked production scope is limited to `contract_publisher.py`, `main.py`, and
  `router_execution_subscriber.py`: publish an empty initial exchange ID, require both durable BFF
  settings before enabled execution starts, and serialize lifecycle transitions so concurrent calls
  converge without duplicate subscriptions or orphan workers.

## R8 GREEN - durable identity, mandatory sink, and serialized lifecycle

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r8.sfTDf8/snapshot.json`, SHA-256
  `013902ec061a1962d5ce6c7a93ff56d053cb0ee91dab2b452ae1751c4ce9bbdc`.
- Receipt: `/tmp/online-trader-r8.sfTDf8/receipt.json`, SHA-256
  `02d2efa3e533dd94f13e34326c414dbc726e82078fa291c2d99b1779554328ae`.
- Primary ownership verification passed for the exact three-file production allowlist; protected
  state and baseline HEAD were unchanged. Complete changed-region inspection passed.
- All three settled-candidate affected runs passed: `200` engine unit tests, `13` real-PostgreSQL
  integration tests, and `51` focused BFF tests on every run.

### Final candidate gates before review

- Full engine from `app/engine`: `1711 passed, 2 skipped, 45 deselected`.
- Full BFF: `46` suites / `404` tests passed; the repository's known retained Jest handle required
  `--forceExit` after the complete passing result.
- Router: `go test ./... -count=1`, `go vet ./...`, `go build ./...`, and gofmt check passed.
- UI under required Node `22.22.3`: `97` files / `1380 passed, 1 skipped`; typecheck, lint,
  Prettier, and optimized Next build passed with only existing warnings.
- Python Ruff lint, changed-file Ruff format, and focused Makefile MyPy scope passed. BFF ESLint,
  Prettier, TypeScript no-emit, contract synchronization, and direct Nest build passed.
- `git diff --check` passed.
- Superseded environment attempts: root-level pytest selected obsolete root tests and failed import
  collection; UI under Node 26 lacked the expected browser storage shim; BFF's rimraf prebuild under
  Node 26 hit the known glob/minimatch export mismatch. Correct component roots, Node 22, and direct
  package build gates above are green.

## Formal g-check and independent QCHECK R9 findings

Fresh deep diff snapshot `2026-08-23/0151` was reviewed in the continuing formal g-check session.
Disposition: **BLOCKED** on two P1 findings. Independent Terra QCHECK converged on the state-integrity
finding and added one P2 integration-proof gap.

### P1 - established exchange and price identity remained mutable

- A row selected by the correct venue/client ID could replace an already nonempty authoritative
  exchange ID with any different inbound ID. Immutable validation also omitted limit price and stop
  price, allowing a conflicting payload to be acknowledged.
- Locked contract: empty initial `order_id` preserves the row; a nonempty inbound ID may populate a
  missing stored ID or equal the stored ID, but cannot replace a different established ID. Price and
  stop-price identity must match the persisted order, including null semantics.

### P1 - stale nonterminal updates could advance status or error state

- The implementation retained the maximum timestamp but did not use it to gate mutations. A delayed
  CANCELED/REJECTED update could terminalize a newer PARTIALLY_FILLED row while leaving the newer
  timestamp in place.
- Locked contract: an update strictly older than `lastUpdateTime` is a durable no-op returning the
  effective persisted projection. Direct acceptance remains non-emitting; the live callback emits
  the effective newer projection and never applies stale position/error/status/fill state.

### P1 - authenticated endpoint lacked runtime payload validation

- `OrderUpdateV1` is a TypeScript interface and supplies no Nest runtime metadata. Malformed version,
  enum, timestamp, identity, numeric, or extra fields could reach reconciliation or poison retries.
- Locked contract: a class-validator DTO enforces version `1.0.0`, required identities, contract
  enums, ISO update time, finite nonnegative decimal values, nullable price fields and applicable
  order-price rules, booleans, and whitelist rejection before repository access.

### P2 - real PostgreSQL lock proof was missing

- Existing tests mocked TypeORM's query builder and reconciliation seam.
- Primary added a real isolated-schema PostgreSQL test with an update-delay trigger and two
  overlapping BFF accepts. It proves the second transaction observes the first committed row under
  `pessimistic_write` and must reject a stale terminal transition.

### R9 RED evidence

- Focused BFF unit/HTTP set: `14 failed, 51 passed`. Five service failures cover stale direct/live
  behavior plus conflicting exchange/price/stop identity; nine HTTP failures show malformed or
  missing payloads currently return 200 instead of 400.
- Real PostgreSQL overlap test failed specifically with final `CANCELED` and stale reject reason,
  while retaining the newer fill and timestamp. This isolates timestamp gating after successful
  transaction serialization.

## R9 GREEN - immutable identity, stale gating, and validated HTTP boundary

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r9.XXBRKO/snapshot.json`, SHA-256
  `a33b28ec4d4055b3aad840eda907528c62e6aa7d55336bf8d9c2a1bf77d6459e`.
- Receipt: `/tmp/online-trader-r9.XXBRKO/receipt.json`, SHA-256
  `d59b59ee135c92508c23ac0b49c46de51178d824197a7a255edc5a76c39a04d4`.
- Primary ownership verification passed for exactly the service, controller, and new DTO; protected
  state and baseline HEAD were unchanged. Complete changed-region inspection passed.
- The service now rejects conflicting established exchange IDs and price identity, treats strictly
  stale updates as effective-state no-ops, and preserves direct/live emission boundaries. The
  internal route now has runtime DTO validation under the production ValidationPipe.
- Primary added a positive valid-payload HTTP characterization after receipt verification.
- All three final affected runs passed: `200` engine unit, `13` engine real-PostgreSQL, `66` focused
  BFF unit/HTTP tests, and `1` BFF real-PostgreSQL overlap test on every run.

### Final R9 candidate gates

- Full engine: `1711 passed, 2 skipped, 45 deselected`.
- Full BFF: `46` suites / `419` tests passed; known retained handle handled with `--forceExit` after
  complete success.
- Full UI under Node `22.22.3`: final settled run `97` files / `1380 passed, 1 skipped`; one preceding
  run exposed the untouched OrderForm submission-state timing flake once. The exact test then passed
  three consecutive isolated runs and the complete suite passed on immediate rerun.
- Router tests, vet, build, and gofmt passed.
- Python Ruff lint/changed-file format/focused MyPy; BFF ESLint/Prettier/TypeScript/contracts/direct
  Nest build; UI typecheck/lint/Prettier/build; and `git diff --check` all passed.

## Formal g-check R10 finding and RED

Fresh deep snapshot `2026-08-23/0212` closed every earlier finding but remained **BLOCKED** on one
P1 money-integrity issue:

- PostgreSQL `NUMERIC(18,8)` identity and reconciliation passed through JavaScript `Number`. Adjacent
  high-range values can collapse to the same binary number, and unrelated status/time updates
  unconditionally rewrote filled quantity and average fill price using rounded values.
- Locked contract: compare quantity, price, stop price, fill quantity, and average fill with exact
  scale-8 decimal semantics; reject adjacent divergent identity; write an increased fill/average from
  its exact contract string; and omit unchanged numeric columns from repository updates.
- The HTTP DTO must match database precision by accepting at most ten integer and eight fractional
  digits for `NUMERIC(18,8)` decimal-string fields.

Primary RED evidence:

- Focused BFF set: `5 failed, 66 passed`. Failures cover adjacent price identity, exact status-only
  preservation, exact increased-fill writes, and DTO scale/precision rejection.
- Real PostgreSQL set: `2 failed, 1 passed`. Adjacent prices were falsely accepted, and a status-only
  update changed `9999999999.00000001` to `9999999999.00000000` in `average_fill_price`.

## R10 GREEN - exact NUMERIC(18,8) reconciliation

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r10.kZmh40/snapshot.json`, SHA-256
  `231f9668f979359e647766bd42e2e15d4c64666014024375229b8ef4afc53bdb`.
- Receipt: `/tmp/online-trader-r10.kZmh40/receipt.json`, SHA-256
  `7a8bd9a3f4064af573ac9a1ce438c2e374cf4a8db0a79d5af9f7932666d957ca`.
- Primary ownership verification passed for exactly the service, DTO, and repository allowlist;
  protected state and baseline HEAD were unchanged. Complete changed-region inspection passed.
- Reconciliation now parses contract and persisted decimals into exact scale-8 bigint values,
  compares immutable identity and monotonic fills without binary-number collapse, preserves exact
  inbound strings for database writes, and omits unchanged decimal columns from status-only updates.
- Runtime validation now mirrors `NUMERIC(18,8)` with at most ten integer and eight fractional digits.
- Primary independent acceptance passed: `71/71` focused BFF unit/HTTP tests and `3/3` real
  PostgreSQL reconciliation tests, including adjacent identity rejection and exact status-only
  preservation.

### Final R10 candidate gates

- Three consecutive affected runs passed without flake: `200` engine unit, `13` engine real-
  PostgreSQL, `71` focused BFF unit/HTTP, and `3` BFF real-PostgreSQL tests on every run.
- Full engine: `1711 passed, 2 skipped, 45 deselected`.
- Full BFF: `46` suites / `424` tests passed; the known retained Jest handle was bounded with
  `--forceExit` after complete success.
- Full UI under Node `22.22.3`: `97` files / `1380 passed, 1 skipped`.
- Router `go test ./... -count=1`, `go vet ./...`, and `go build ./...` passed.
- Python Ruff lint, changed-file Ruff format, focused Makefile MyPy; BFF ESLint, Prettier,
  TypeScript, contract synchronization, and direct Nest build; UI typecheck, lint, Prettier, and
  optimized build; router gofmt; and `git diff --check` all passed.

## Final formal g-check and independent QCHECK findings after R10

Fresh deep snapshot `2026-08-23/0232` verified the exact-decimal remediation but remained
**BLOCKED** on five P1 correctness paths. The continuing formal g-check found the first three;
independent Terra QCHECK found the final two and reported no other P0-P2 issues.

- Synthetic placement updates have an empty exchange `order_id` but advanced BFF's exchange-update
  watermark. A fast exchange fill timestamped before the later synthetic placement event could then
  be discarded forever as stale.
- Engine webhook ingestion used a mutable upsert before BFF validation. A payload with the right
  venue/client ID but divergent symbol, side, type, quantity, price, stop price, or established
  exchange ID could rewrite the shared canonical row before downstream rejection.
- BFF accepted impossible status/fill relationships, including zero or excessive FILLED states and
  invalid PARTIALLY_FILLED/NEW combinations. Terminalization then prevented later correction.
- BFF selected the client-ID row first and could assign an exchange ID already owned by another row
  in the venue, because the supplied client and exchange identifiers were not resolved together.
- Engine's synthetic order-update publisher used `str(Decimal)`, producing scientific notation for
  valid scale-8 values such as `1E-8`; the BFF fixed-point DTO rejects that payload and retries the
  acknowledged delivery indefinitely.

### R11/R12 locked RED evidence

- BFF unit/HTTP scope: `7 failed, 58 passed`. The failures are the lost earlier exchange fill and six
  impossible status/fill combinations; the fixed-point scale-8 HTTP contract is already accepted.
- BFF real PostgreSQL scope: `2 failed, 3 passed`. The failures prove both the synthetic watermark
  loss and two-row exchange-ID alias corruption.
- Engine contract publisher scope: `1 failed, 13 passed`, with all five decimal fields emitted as
  exponent strings instead of fixed point.
- Engine real PostgreSQL webhook scope: `6 failed, 12 passed`. Five immutable limit-order identity
  variants plus a divergent stop price were accepted instead of returning retryable `503`; after
  correcting the seed's required `created_at`, every failure is the intended missing behavior.

## R11 GREEN - safe engine ingestion and fixed-point delivery

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r11.FQxdXd/snapshot.json`, SHA-256
  `57597995b3601a23ae506556795c98451f0ac4c394ed7569bbcc97d78b17a2d2`.
- Receipt: `/tmp/online-trader-r11.FQxdXd/receipt.json`, SHA-256
  `e82ca51e01250259fa78cbf4f43f7bd35ecd68b14dd5c196730fd45ed88a7fae`.
- Primary ownership verification passed for exactly the contract publisher, Timescale adapter, and
  main webhook wiring; protected state and baseline HEAD were unchanged. Complete changed-region
  inspection passed.
- The publisher now uses fixed-point Decimal serialization. Enveloped webhook projection now enters
  a transaction-scoped insert/lock/immutable-validate/mutable-update path, including established
  exchange-ID ownership validation; conflicts fail the inbox and return retryable `503` without
  publication. Legacy generic upsert behavior remains separate.
- Primary independent GREEN passed: `85` focused engine unit/wiring tests and `18` real-PostgreSQL
  webhook/durability tests.

### R12 additional RED - database-enforced exchange identity ownership

- A new real-PostgreSQL contract inserts two different client orders in one venue with the same
  non-null exchange order ID and requires the second insert to raise `UniqueViolationError`.
- Current schema accepted both rows, producing the intended `1 failed` RED. The locked remediation
  requires a rerunnable partial unique index on `(venue, exchange_order_id)` for non-null IDs, so
  the invariant remains true across BFF/engine instances and concurrent adopters.

## R12 GREEN - BFF exchange state machine and global exchange identity

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r12.Hq1ze0/snapshot.json`, SHA-256
  `f02c4276379711b3ce1e041c0f0b67c1e5f15a7b663ffd2296851b7ed1d83df9`.
- Receipt: `/tmp/online-trader-r12.Hq1ze0/receipt.json`, SHA-256
  `4312cea8b5738088a0da6a5b74782cb54e6dbbf399ba8fbe1e352970a470a27e`.
- Primary ownership verification passed for exactly the BFF service, repository, entity, and new
  migration 038; protected state and baseline HEAD were unchanged. Complete changed-region
  inspection passed.
- Synthetic empty-exchange-ID updates no longer advance the exchange watermark. Exact relational
  status/fill/average invariants are validated before mutation. Repository locking resolves both
  venue-scoped client and exchange IDs, while the partial unique index enforces exchange ownership
  across concurrent processes and TypeORM metadata matches the canonical schema.
- Primary independent GREEN passed: `79` focused BFF tests, `5` BFF real-PostgreSQL tests, and the
  real-PostgreSQL duplicate exchange-ID oracle.

### R12b RED and GREEN - remove invalid overfill compatibility

- Inspection found a delegate-added compatibility branch that allowed a terminal status-only update
  to preserve an already-overfilled row. The real-PostgreSQL decimal-preservation fixture that had
  motivated it was corrected from quantity `0.01` to `1.00`.
- Primary added a direct regression; RED was `1 failed`, returning CANCELED with `0.02` filled on a
  `0.01` order instead of rejecting without mutation.
- Ownership snapshot: `/tmp/online-trader-r12b.gZUdHE/snapshot.json`, SHA-256
  `7b35b7d016ec9aeb39bfa584ca7c0a4aecb3014e0a5c87675b7b7720ca793dfa`.
- Receipt: `/tmp/online-trader-r12b.gZUdHE/receipt.json`, SHA-256
  `c20bc3c2437c3360407e1a7dd31b73d1f2fc1013a52d7ad511485b1324dea75b`.
- Primary ownership verification passed for the one-file service remediation. The invalid exception
  is removed; the regression, all `50` service tests, the `66` focused BFF set, `5` PostgreSQL tests,
  and delegate static gates passed.

### Final R12 candidate gates

- Three consecutive expanded affected runs passed without flake: `201` engine unit, `20` engine
  real-PostgreSQL, `80` focused BFF unit/HTTP, and `5` BFF real-PostgreSQL tests on every run.
- Full engine: `1712 passed, 2 skipped, 45 deselected`.
- Full BFF: `46` suites / `433` tests passed; the known retained Jest handle was bounded with
  `--forceExit` after complete success.
- Full UI under Node `22.22.3`: `97` files / `1380 passed, 1 skipped`.
- Router `go test ./... -count=1`, `go vet ./...`, and `go build ./...` passed.
- Python Ruff lint, changed-file Ruff format, focused Makefile MyPy; BFF ESLint, Prettier,
  TypeScript, contract synchronization, and direct Nest build; UI typecheck, lint, Prettier, and
  optimized build; router gofmt; and `git diff --check` all passed.

## Fresh formal g-check findings after R12

Fresh deep snapshot `2026-08-23/0312` remained **BLOCKED** on three P1 delivery-contract paths:

- Engine ACK projection persisted the router correlation `bracket_order_id` as the main order's
  authoritative exchange ID, causing a later real exchange update to fail strict identity checks.
- Router order-update/outbox payloads omitted the authoritative average fill price; engine then
  published `average_fill_price: null`, which BFF correctly rejects for positive partial/filled
  states.
- A repeated synthetic placement `NEW` against an already PARTIALLY_FILLED BFF projection was
  promoted to the persisted status and then validated against the synthetic zero-fill payload,
  returning `ok: false` and retrying the durable delivery indefinitely.

## R13 GREEN - separate router bracket correlation from exchange identity

- Primary RED was `1 failed`: ACK projection stored `bracket-abc-123` in `exchange_order_id`.
  The forward-migration oracle also failed because migration 039 did not exist. A real-PostgreSQL
  contract independently proved that a clean ACK projection adopts the first authoritative
  exchange ID, marks its inbox event PROCESSED, and rejects a second ID with a FAILED inbox event.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r13.de7muc/snapshot.json`.
- Receipt: `/tmp/online-trader-r13.de7muc/receipt.json`, SHA-256
  `1388579dd2c4afd9483417136e32a382e52ee04873a1e0ea7b4f4556f6738a2e`.
- Primary ownership verification passed for exactly the projection builder and new migration 039;
  protected state and baseline HEAD were unchanged. Complete changed-region inspection passed.
- New ACK rows leave `exchange_order_id` null. Migration 039 idempotently clears only same-venue
  order identities equal to an acknowledged execution intent's router bracket correlation, while
  retaining unrelated authoritative exchange IDs.
- Primary independent GREEN passed: `1` focused unit test and `2` real-PostgreSQL contracts; the
  relevant Python source and tests pass Ruff after import normalization.

### R15 locked RED - synthetic placement replay over a partial fill

- BFF unit RED is `1 failed`: the replay returns `null` instead of the effective persisted
  PARTIALLY_FILLED event; the stale NEW cache entry is therefore not repaired.
- BFF real-PostgreSQL RED is `1 failed`: the same replay returns `null` even though the durable row
  remains a valid `0.006 @ 45005` partial fill with its original exchange watermark.
- The locked remediation is a compatible synthetic no-op that returns the effective durable state,
  does not write fill/average/timestamp fields, repairs the active cache, creates no position, and
  permits the internal controller to acknowledge durable delivery completion.

## R15 GREEN - acknowledge compatible partial-fill placement replays

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r15.K4HDjh/snapshot.json`.
- Receipt: `/tmp/online-trader-r15.K4HDjh/receipt.json`, SHA-256
  `ea813bc8533bf241f1f5ce829377dcf70afc7cab687df851e3684be2577cdc73`.
- Primary ownership verification passed for exactly `trading.service.ts`; protected state and the
  baseline HEAD were unchanged. Complete changed-region inspection passed.
- A compatible synthetic NEW over a PARTIALLY_FILLED row now returns the locked durable row as an
  accepted no-op. It preserves exchange identity, fill, average, and watermark; refreshes the active
  cache; and does not create a position or write the repository.
- Primary independent GREEN passed for the focused unit and real-PostgreSQL contracts. Delegate
  evidence additionally passed all `51` service tests, all `6` reconciliation integration tests,
  Prettier, ESLint, and TypeScript.

### R14 locked RED - authoritative average-fill transport

- Engine RED is `2 failed`: `OrderUpdate` ignores the inbound authoritative average, webhook
  persistence substitutes immutable limit price as fill average, and the contract publisher emits
  `average_fill_price: null`.
- Router RED is an expected compile failure across the focused packages: neither Binance
  `OrderResponse` nor durable `OrderUpdate` exposes a separate average field, and `BracketRepo`
  lacks the atomic leg-execution method needed to place the average into the same transaction as the
  status/outbox trigger.
- Locked router behavior preserves immutable limit/market `price`, transports the exchange or
  trade-weighted average separately, stores immediate-fill average on `bracket_legs`, and emits it
  from a forward migration 040 trigger. Status-only terminal transitions may preserve a prior or
  canonical stored average but must not synthesize one from limit/trigger price.
- Locked engine behavior parses, persists, and republishes the separate fixed-point average without
  substituting price. Existing BFF real-PostgreSQL reconciliation already proves that distinct
  immutable price and authoritative average are accepted and projected exactly.

## R14a GREEN - router average transport and immediate-fill trigger state

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r14a.WoK88H/snapshot.json`.
- Receipt: `/tmp/online-trader-r14a.WoK88H/receipt.json`, SHA-256
  `0631e5fe5a99a90cc6b59738b9f5b5ef815c0db40ae202cfeb106e3b4b839c29`.
- Primary ownership verification passed for exactly eight router/storage/migration files; protected
  state and baseline HEAD were unchanged. Complete changed-region inspection passed.
- Router placement/query models now separate immutable price from average. Spot reconciliation no
  longer rewrites price. `UpdateLegExecution` stores immediate-fill average on `bracket_legs`, and
  migration 040 emits NEW average first with canonical/prior fallbacks while retaining migration
  037 stop-price semantics.
- Primary independent focused GREEN passed across Binance, orders, and storage packages. Delegate
  `go vet ./...`, `go build ./...`, gofmt, and twice-applied migration 040 evidence passed. The
  delegate's broad storage run encountered pre-existing fixture-schema failures, so it is not counted
  as acceptance; primary final gates remain required.
- Independent QCHECK immediately identified follow-on recovery contracts outside this fixed
  ownership snapshot: null (not numeric zero) for no-fill averages, futures query DTO mapping,
  delayed entry-fill terminalization, restart/adoption average persistence, and explicit trigger
  precedence/sequence tests. R14a is therefore an accepted intermediate slice, not a final candidate.

### R14a2 locked RED - recovery-path average persistence

- Primary-owned focused RED is intentional across six assertions: a no-fill order update serializes
  numeric `"0"` instead of JSON null; futures order adoption drops `avgPrice`; a live futures entry
  fill does not terminalize the ENTRY leg with its exchange ID and average; the restart watcher arms
  a spot bracket without persisting the observed ENTRY execution; a futures exit stream fill drops
  its average; and startup exit reconciliation drops the observed average.
- Locked behavior uses `UpdateLegExecution` only when an authoritative positive average is present,
  preserving the existing status-only path for non-fill transitions. Entry terminalization must
  precede protective-leg arming so a crash cannot leave the canonical ENTRY state stale.
- Test ownership hashes before the production handoff: `events_test.go`
  `04b56ddf452034dfe950d86ccc3fcc0fb82d2ceb1ebbab92d50e4b4e091d7dbf`,
  `client_test.go` `25be0e3c5f62c5e99f9a54eb8751b2d155d710fb60ed9e9c83727c07b3bbbc69`,
  `leg_armer_test.go` `439fd6312e621b86b9ea7496806c56cb97a5f546fad95c4f78112418f94ee9ba`,
  `entry_fill_watcher_test.go` `0eb56b6bb837767cc7646dab5cc861e4f3477864897986c8dc5f763bc3136359`,
  and `startup_reconciler_test.go`
  `1043bbbfe46fd7c53474733f6e45b76327136d45bb57f4b2afca9e6bbf34c3f0`.

## R14a2 GREEN - persist authoritative averages across recovery paths

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r14a2.WvN1hg/snapshot.json` (SHA-256
  `ddfd996a7e876639994cb1ab4b7a5e95309bb4f17acff85e2c9ec9e2c6ab97a8`).
- Receipt: `/tmp/online-trader-r14a2.WvN1hg/receipt.json` (SHA-256
  `4d1debb0d1821cef83b5b3d30de25437f93a0bb0a1be48e53b8b633eb36c630f`).
- Primary ownership verification passed for exactly the six allowlisted router files; HEAD and every
  protected file were unchanged. Complete changed-region inspection passed.
- No-fill updates now serialize a null average. Futures adoption decodes `avgPrice`/`cumQuote`, and
  live-stream, watcher, PLACING-adoption, and startup exit paths persist authoritative averages with
  the terminal bracket-leg transition before downstream arming/settlement.
- Primary independent focused GREEN passed across Binance and orders. Delegate evidence also passed
  both complete affected packages, gofmt, `go vet ./...`, `go build ./...`, and diff whitespace.

### R14a acceptance-strengthening database contracts

- Primary-owned tests now distinguish all migration 040 precedence inputs: a NEW execution average
  `50020` wins over canonical `50010` and prior `50000`; a canonical `102.50` wins over prior
  `101.25`; after canonical removal, that newest prior `102.50` survives another terminal status.
- A STOP_MARKET fill proves `price` remains null, `stop_price` remains the trigger price, and the
  independent execution average is retained. Immediate spot and futures placement responses also
  prove immutable zero market price and authoritative average remain separate.
- The real-PostgreSQL trigger contract allocates contiguous sequences `[1,2]`, claims sequence 1,
  proves sequence 2 ineligible while its predecessor is DELIVERING, then claims sequence 2 only
  after sequence 1 is DELIVERED. All focused Binance/orders/storage proofs pass.

### R14b locked RED - engine average-fill ingestion and publication

- Primary focused RED is exactly `2 failed, 57 passed`: webhook persistence uses immutable limit
  price `50000` instead of authoritative average `50020`, and the contract publisher emits a null
  average instead of fixed-point `"50020"`.
- Locked behavior adds an optional decimal average to the engine model, parses the router field,
  persists it without price substitution, and republishes it independently. A positive-fill update
  without an average stays invalid downstream; the engine must not invent an average from price.

## R14b GREEN - engine preserves authoritative average fill price

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r14b.sdaUhQ/snapshot.json` (SHA-256
  `55cb0f98411aece2d6f3a9c0ed04ff19633dbd706629ef0d7af9680513f7c788`).
- Receipt: `/tmp/online-trader-r14b.sdaUhQ/receipt.json` (SHA-256
  `625c0d33e9a156dee5464bd2f39136c76f7044a33c6ba6161622700676eee394`).
- Primary ownership verification passed for exactly `models.py`, `main.py`, and
  `contract_publisher.py`; HEAD and every protected file were unchanged. Changed-region inspection
  confirms the model, parser/persistence, and publisher use the same optional Decimal contract.
- Primary independent focused GREEN is `59 passed, 11 deselected`. Delegate evidence additionally
  passed all `70` tests in the two affected files plus Ruff format/check.

## R16 RED - reject executed spot snapshots without trade evidence

- A real-PostgreSQL full-router gate first exposed stale test fixtures: three temporary `orders`
  schemas lacked the migration 023 timing columns, one position fixture omitted its already-defined
  partial uniqueness index, and one exact string assertion ignored NUMERIC display scale. Primary
  repaired only those test fixtures; their focused contracts pass.
- With the fixture capable of reaching production behavior, the pre-existing
  `TestSpotTradeProcessor_RejectsExecutedSnapshotWithoutTrades` now supplies the intended RED: a
  FILLED snapshot with positive `ExecutedQty` and no trades returns nil after marking the order
  filled, while position/fill state cannot be reconciled.
- Locked one-file remediation rejects that contradictory snapshot before any order mutation. It does
  not weaken duplicate-trade idempotency: snapshots whose trades were already persisted may still
  have no newly inserted trades after evidence validation.

## R16 GREEN - require spot trade evidence before fill mutation

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r16.NASiNK/snapshot.json` (SHA-256
  `7b59c681389066d4e9e6f230ff889f0a935b523066e8783b21a30862e79eeae0`).
- Receipt: `/tmp/online-trader-r16.NASiNK/receipt.json` (SHA-256
  `26496705e00560c37b1e0a217bd8009e28fe26db948f6308ceddb2ecfda06e48`).
- Primary ownership verification and changed-region inspection passed for the single allowlisted
  production file. The processor validates positive executed snapshots have inbound trade evidence
  before any mutation; duplicate insertion remains idempotent after that boundary.
- Primary focused GREEN passed. Delegate evidence additionally passed the complete execution
  package, gofmt, `go vet ./...`, and `go build ./...`.

## R17 RED - Redis mset typing under the canonical engine environment

- Full non-integration engine execution reached `1712 passed, 2 skipped, 45 deselected`; the sole
  failure is its embedded MyPy contract for `redis_adapter.py`.
- Installed Redis typing accepts `Mapping[str | bytes, bytes | float | int | str]`, while the local
  `redis_pairs` variable is annotated as invariant `dict[str, str]`; runtime values are already
  valid serialized strings. The locked remediation is annotation-only and must not change key
  construction, serialization, exception handling, or return behavior.

## R17 GREEN - align Redis mset annotation with installed typing

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r17.BJkIuI/snapshot.json` (SHA-256
  `1fd3f06d18f3dbc37453a98acf31c3873a152d4c7ce59aaaedc3968c26918b79`).
- Receipt: `/tmp/online-trader-r17.BJkIuI/receipt.json` (SHA-256
  `aadf6ba82bc48482cdc02669153b50c42853fcebc42f2f8e9a655d510d6c7d36`).
- Primary ownership verification and complete two-line diff inspection passed. Only the local mapping
  annotation and formatter-required blank line changed; runtime behavior is unchanged.
- Primary embedded MyPy GREEN passed. Delegate direct MyPy and Ruff format/check also passed.

## R18 RED and GREEN - canonical MARKET payloads and futures placement averages

- Fresh formal-review REDs proved four concrete gaps: Router MARKET JSON emitted price `"0"`;
  migration 040 emitted a numeric MARKET entry price; Engine ingestion persisted `Decimal("0")`;
  and immediate futures placement ignored the existing `cumQuote / executedQty` fallback when
  `avgPrice` was zero.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r18.6fifIR/snapshot.json` (SHA-256
  `c4224b0d3f10602cd7c678738ff59ff35273ca11272b434d3fbd13d65c31366d`).
- Receipt: `/tmp/online-trader-r18.6fifIR/receipt.json` (SHA-256
  `7feb751389ca19b4d6c3e0bb69e1861a7589a320501c4e861df8da0607aa2ed3`).
- Primary ownership verification passed for exactly `orders/types.go`, migration 040,
  `engine/main.py`, and `binance/client.go`; HEAD and protected files were unchanged.
- MARKET now has null immutable price and null stop price at Router JSON, trigger outbox, Engine
  persistence/event, and BFF DTO boundaries. LIMIT/STOP behavior is unchanged. Immediate futures
  placement now prefers positive `avgPrice`, then authoritative cumulative quote divided by fill.
- Primary independent GREEN passed all four focused RED commands, including the real-PostgreSQL
  trigger contract.

## R19 RED and GREEN - deterministic terminal fill and BFF-first delivery

- Real-PostgreSQL RED proved equal-timestamp CANCELED(partial) then FILLED(full) remained canceled,
  while inverse arrival became filled. Engine RED proved BFF `{ok:false}` was observed only after an
  `OrderPlacedEvent` had already been published, widening duplicate-alert exposure.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r19.NCaWgp/snapshot.json` (SHA-256
  `f9642345a9b30d8369c9e9947708cb2c5157dcb05983d4fa966090b2bc7e35ed`).
- Receipt: `/tmp/online-trader-r19.NCaWgp/receipt.json` (SHA-256
  `f4c343c10e4fd95c310038591b64f338036ca0b9da8dec14ad367d558a2113a1`).
- Primary ownership verification passed for exactly BFF `trading.service.ts` and Engine
  `router_execution_subscriber.py`; HEAD and protected files were unchanged.
- A non-stale authoritative full FILLED update with increased fill may upgrade CANCELED/EXPIRED;
  FILLED and REJECTED remain immutable, older updates remain stale, and a successful upgrade clears
  the prior rejection reason. ORDER_PLACED now requires durable BFF `{ok:true}` before bus/alert
  publication. BFF failure publishes no placement event; post-BFF bus failure retries against BFF's
  compatible idempotent reconciliation.
- Primary independent GREEN passed the Engine delivery test and all `8` real-PostgreSQL BFF
  reconciliation tests. Two existing test expectations were updated to the locked BFF-first order.

## Final candidate gates after R19 (2026-08-23 04:50:48 +07)

- Three consecutive affected runs passed: Engine `127` unit plus `21` real-PostgreSQL; BFF `81`
  unit plus `8` real-PostgreSQL; Router `api`, `binance`, `execution`, `orders`, and `storage`.
- Full Engine: `1714 passed, 2 skipped, 45 deselected`.
- Full Router with real PostgreSQL: every package passed.
- Full BFF: `46` suites / `434` tests passed; retained Jest handles were bounded with `--forceExit`
  after complete success.
- Full UI under Node `22.22.3`: `97` files / `1380 passed, 1 skipped`. An unrelated timer-based
  `OrderForm` assertion flaked once under four-suite concurrency; primary replaced its 100 ms timer
  with a controlled deferred promise. The focused test passed three times and the full UI rerun
  passed.
- Go gofmt/vet/golangci-lint/build; Python Ruff lint, changed-file Ruff format and focused MyPy;
  BFF ESLint/Prettier/TypeScript/contracts/Nest build; UI lint/Prettier/typecheck/optimized build;
  and `git diff --check` all passed.
- Root `make ci` was not run because its BFF lint target invokes `eslint --fix`, which would violate
  the primary production-write boundary. The equivalent non-mutating component commands above were
  executed directly. The Makefile Python packaging target was unavailable because the existing
  Engine virtualenv lacks the `build` module; runtime tests, lint, typecheck, and all service builds
  passed.

### Final wiring verification

| Component | Non-test call site | Registration/config load | Schema/contract match |
|---|---|---|---|
| Router placement/update | `app/router/internal/orders/manager.go:569` builds the authoritative initial update | durable store suppresses direct emission at `manager.go:586`; storage/outbox owns delivery | average and MARKET-null JSON are asserted by Router unit and real-PostgreSQL trigger tests |
| Router fill/recovery | `leg_armer.go:76`, `entry_fill_watcher.go:145`, and `startup_reconciler.go:462` persist live and adopted fills | `persistLegExecution`/`UpdateLegExecution` is used before protective arming | migration 040 emits stop/market/average fields and contiguous aggregate sequence |
| Engine ACK boundary | `router_execution_subscriber.py:883` constructs projections/deliveries and calls atomic ACK commit | subscriber receives the BFF client at `main.py:699` and BFF starts before the drain at `main.py:788` | `timescale_adapter.py:1794` atomically commits projections, ACK, and delivery rows |
| Engine delivery | `router_execution_subscriber.py:1195` executes SNAPSHOT or BFF-first ORDER_PLACED | venue drain is registered by the runtime subscriber; stable event ID is built at line 1385 | leased claim/fencing and completion live at `timescale_adapter.py:1858` and `:1971` |
| Engine order update | `main.py:1123` parses authenticated Router updates and canonicalizes MARKET/STOP at `:1196` | FastAPI route uses the initialized DB/event-bus services | fixed-point average, null price, stop price, exchange identity and terminal persistence are cross-language tested |
| BFF durable projection | `trading.controller.ts:138` accepts the internal DTO and calls service line 585 | `trading.module.ts` registers the controller/service/repository | repository lock at `order.repository.ts:104`; monotonic reconciliation at `trading.service.ts:605`; DTO relational contract is tested |
| PostgreSQL delivery | migration 036 creates the success ledger and migration 040 replaces the trigger | migrations are sequential and rerunnable in real-PostgreSQL tests | PK/FK/checks, lease fencing, retry backoff, MARKET nulls, average precedence and outbox sequencing are executable contracts |

Residual delivery semantics remain intentionally at-least-once across the final external-effect to
fenced-checkpoint crash window. BFF reconciliation and stable event identity close normal retry
duplicates; process death after event publication can still re-present a stable event ID and
downstream consumers must preserve idempotency.

## Formal review findings after R19

The fresh system review found four remaining correctness gaps and Terra independently found one
additional numeric-contract issue:

- a process restart could leave a persisted `SUBMITTING` execution intent with no decision event to
  republish it;
- a positive partial entry remained working without protective exits;
- spot stop updates lost the `STOP_LOSS_LIMIT` price/type distinction;
- Engine did not deterministically upgrade a terminal canceled/expired row to a full fill; and
- spot trade-weighted average prices could exceed the BFF/database scale-8 contract.

All findings were accepted. The partial-fill finding was locked as cancel-and-finalize rather than
incremental protection: persist progress, obtain one durable finalization lease, cancel the
remainder, perform a mandatory stable-client-ID terminal requery, persist the final quantity, and
only then arm exact exit coverage.

## R20 GREEN - terminal fidelity and canonical stop payloads

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r20.T49NTF/snapshot.json` (SHA-256
  `431d9e885d810850510038591b64f338036ca0b9da8dec14ad367d558a2113a1`).
- Receipt: `/tmp/online-trader-r20.T49NTF/receipt.json` (SHA-256
  `d4b0813c6025060b78fb5d031bae253b4a9dff5588e4a53f8b3037fd71acc1a5`).
- Primary ownership verification passed for exactly the Timescale adapter, Router order-update type,
  and migration 040; HEAD and protected files were unchanged.
- Engine now upgrades authoritative full fills over canceled/expired rows, Router JSON preserves the
  stop price, and the PostgreSQL trigger emits spot `STOP_LOSS_LIMIT` with separate limit and trigger
  prices.
- Primary focused GREEN passed the Router JSON/trigger tests, both parameterized real-PostgreSQL
  terminal-upgrade cases, and Engine stop-limit webhook normalization.

## R21 GREEN - scale-8 spot weighted averages

- Primary RED proved a nonterminating trade-weighted average crossed the Router/BFF boundary with
  more than eight fractional digits.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r21.7xwbH0/snapshot.json` (SHA-256
  `0e384e74aa7187aa08f1ff2a0ed95932c970d6b43d240f98bccfae8c73b92e83`).
- Receipt: `/tmp/online-trader-r21.7xwbH0/receipt.json` (SHA-256
  `353499cac427f1d9e7afa3a215b380fe14b715930f7b630400ffedfd81df102f`).
- Primary ownership verification passed for the single allowlisted spot reconciler. Only the
  weighted average is rounded to scale 8; immutable order price and trade quantities are unchanged.
- Primary focused GREEN passed.

## R22 GREEN - restart recovery for persisted execution intents

- Primary RED proved the runtime had no worker/API to recover a durable `SUBMITTING` request and no
  concurrent lease contract.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r22.lMNBRc/snapshot.json` (SHA-256
  `23870d4b0a09222b16d2745944360e4642672a5f6f69ff1cbecaf25c8db58b83`).
- Receipt: `/tmp/online-trader-r22.lMNBRc/receipt.json` (SHA-256
  `695793af0a0c24e6b18a02ef4b4df4c276efeb42f6a5ef1a9ba384e6c75835b4`).
- Primary ownership verification passed for the subscriber, Timescale adapter, and migration 041.
- Migration 041 adds a rerunnable recovery lease and attempt counter. The subscriber claims stale
  persisted intents with `FOR UPDATE SKIP LOCKED`, reconstructs a validated decision from the stored
  request, and re-enters the existing submission/idempotency boundary without requiring decision
  republish. ACK/rejection clears the lease.
- Primary focused unit and concurrent real-PostgreSQL lease GREEN passed; delegate affected evidence
  additionally passed `66` unit and `22` integration tests.

## R23 GREEN - durable cancel-and-finalize protection for partial entries

### R23a persistence and ordered event contract

- Ownership snapshot: `/tmp/online-trader-r23.laoppk/snapshot.json` (SHA-256
  `f86eae1a1e25f889ac45f36bd890f854a15aa3b6d38d709ef94fe2e00184505b`).
- Receipt: `/tmp/online-trader-r23.laoppk/receipt.json` (SHA-256
  `b3c0f95a1fe2cdabe0b65167877acf7a618218c914df5a1606dfd12b30e7c2be`).
- Primary ownership verification passed for exactly the bracket repository and migration 042.
- Migration 042 adds durable executed quantity and a fenced entry-finalization lease. The repository
  persists cumulative progress and the outbox emits ordered partial then terminal updates with the
  final protected quantity.
- Primary real-PostgreSQL outbox and complete storage-package GREEN passed.

### R23b orchestration

- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r23b.LTnX8X/snapshot.json` (SHA-256
  `387da4481db40d2bac8ab2e595fc006f2256ab587afbc585503895728fa96a7a`).
- Receipt: `/tmp/online-trader-r23b.LTnX8X/receipt.json` (SHA-256
  `f9d03d18535d1e760aa7aabb4b336806ab3f64fc766250f1f79daf25af1473dc`).
- Primary ownership verification passed for exactly the five changed orchestration files; HEAD and
  every protected file were unchanged. Complete finalizer/watcher/armer/replay/spot coverage
  inspection passed.
- Futures stream events and the shared spot/futures watcher now persist partial progress, claim one
  finalizer, cancel best-effort, require a terminal stable-ID query, persist the authoritative final
  state, and arm only that immutable quantity. Startup continues through the same watcher path, and
  immediate replay persists cumulative progress. Exact futures and fee/step-adjusted spot exit
  quantities are durable before placement claims.
- Primary focused futures/spot GREEN, ordered real-PostgreSQL partial-to-terminal GREEN, complete
  orders package, and complete storage package passed. The stale storage expectation was corrected
  test-only to assert canonical spot `STOP_LOSS_LIMIT` with both prices.

## Final candidate gates after R23 (2026-08-23 06:18 +07)

- Three consecutive affected runs passed without flake: Engine `123` unit and `40` real-PostgreSQL;
  Router complete `orders` and `storage` packages against PostgreSQL; and BFF `8` real-PostgreSQL
  reconciliation tests on every run.
- Full Engine non-integration: `1717 passed, 2 skipped, 44 deselected`; the two affected integration
  files passed `40/40` against the isolated database.
- Full Router with real PostgreSQL: every package passed. gofmt, `go vet ./...`, `go build ./...`, and
  `golangci-lint run ./...` passed.
- Full BFF: `46` suites / `434` tests passed. The relevant database suite passed `8/8`; retained Jest
  handles were bounded with `--forceExit` after complete passing results.
- The repository-wide BFF integration preset still has three legacy environment-dependent suites
  that require their own JWT/default-port service configuration; they fail before candidate behavior
  while the scoped database suite passes and are not used as acceptance evidence.
- Full UI under Node `22.22.3`: `97` files / `1380 passed, 1 skipped`. Lint retained the four existing
  warnings; Prettier, typecheck, and optimized build passed.
- Engine Ruff lint, changed-file Ruff format, and focused MyPy; BFF non-mutating ESLint, Prettier,
  TypeScript, contract synchronization, and direct Nest build; and `git diff --check` passed.
- Root `make ci` remains intentionally unused because its BFF target executes `eslint --fix`, which
  would violate the primary production-write boundary.

## R24 GREEN - durable claim-loss handling, recovery queue, and quantity fencing

- Primary RED covered a futures protective-leg claim loser, an active bracket older than the prior
  recovery lookback, and a quantity resize after placement ownership had been claimed.
- Luna role/model/effort: `luna_implementer` / `gpt-5.6-luna` / `max`.
- Ownership snapshot: `/tmp/online-trader-r24.TqmDd9/snapshot.json` (SHA-256
  `04952a79de8833c2ed656b8ff245548cc2296866431c176131271ab3d7589028`).
- Receipt: `/tmp/online-trader-r24.TqmDd9/receipt.json` (SHA-256
  `5d886f170f1b26b2cb52273008e0bd86971be7a9cda6e5f852072d3a60965214`).
- Primary ownership verification passed for exactly `leg_armer.go` and `bracket_repo.go`.
  Claim losers remain pending until reconciliation, all non-closed/non-failed brackets form the
  durable recovery queue, and quantity changes are fenced to unclaimed PLANNED/FAILED legs.

## R25 GREEN - persisted intent recovery bypasses live admission only

- Primary RED proved a stored SUBMITTING/AMBIGUOUS request could be blocked by present-time risk,
  readiness, confidence, duplicate, cooldown, or position admission even though exchange submission
  might already have happened.
- Snapshot: `/tmp/online-trader-r25.2zbEcv/snapshot.json` (SHA-256
  `65d52d5a6b2064798e843119f478840ef96a2c872276ed95cf0d23be650796cc`).
- Receipt: `/tmp/online-trader-r25.2zbEcv/receipt.json` (SHA-256
  `dbd7b786d0ed1d1c545738461c732e324618bbbd8e93dae989bbd68688acd79a`).
- Ownership verification passed for `router_execution_subscriber.py`. Recovery mode is available
  only for a validated existing SUBMITTING/AMBIGUOUS intent; new decisions retain every live gate,
  while recovery reuses the stored request and existing idempotent Router/ACK path.

## R26 GREEN - monotonic Router fill averages

- Primary real-PostgreSQL RED showed a delayed lower-quantity observation could overwrite the
  average attached to a larger durable cumulative fill.
- Snapshot: `/tmp/online-trader-r26.jh0B9q/snapshot.json` (SHA-256
  `cafec4bd4a66a19149e7564e2d660b62c2d46fa065cd34f366640d3c0dfe9788`).
- Receipt: `/tmp/online-trader-r26.jh0B9q/receipt.json` (SHA-256
  `acae78875f25b35eb6c0d4c98455cfd5e4a97af825a27400c7c8da9bb2dfaa2d`).
- Ownership verification passed for `bracket_repo.go`; positive averages may update only with an
  equal or larger cumulative quantity. Focused and full storage PostgreSQL tests passed.

## R27/R28 GREEN - same-status average correction and BFF projection repair

- Primary RED established that a strictly newer, exchange-backed, same-status PARTIALLY_FILLED or
  FILLED update with the same positive cumulative quantity must be allowed to correct its average
  without replaying a FILLED position delta.
- R27 snapshot `/tmp/online-trader-r27.6hNs22/snapshot.json` (SHA-256
  `5ce21f42b9d21584efdc986ded2bef69a9cf790a4e8a035a7e2b024c1c6e62b2`) and receipt
  `/tmp/online-trader-r27.6hNs22/receipt.json` (SHA-256
  `52fd3a042790ac4b9f7fe920be088c902a797cca77df1d26de39b39fbe5108e5`).
- R28 snapshot `/tmp/online-trader-r28.m8i3jK/snapshot.json` (SHA-256
  `aeff74795d897dab8534713367894e8c676612cfb3bd735f34f91cd1f11be2c1`) and receipt
  `/tmp/online-trader-r28.m8i3jK/receipt.json` (SHA-256
  `9dd19e7cb8ff0733c41711f0a026ad305149de4a16cacfe69d93d5ff91ff9f62`).
- Both ownership validations passed for the bounded BFF service changes. The interim cumulative-order
  position replay was later superseded by the authoritative snapshot design in R34.

## R29 GREEN - migration EOF normalization

- A static one-behavior oracle required migrations 038 and 039 to contain exactly one normal final
  newline with no SQL-token or semantic change.
- Snapshot: `/tmp/online-trader-r29.9jsDQl/snapshot.json` (SHA-256
  `19a1359c5dc7e975314fc00cecfad69f0ca7bd39aca042539716a24086df18c5`).
- Receipt: `/tmp/online-trader-r29.9jsDQl/receipt.json` (SHA-256
  `b9802e33b81b72fdff7def394b67ffadfa94bd7aea54a962b27424490d9edfd3`).
- Ownership verification passed; only the extra EOF line endings changed.

## R30 GREEN - inactive-venue recovery is fail closed

- Primary unit and real-PostgreSQL RED proved incomplete SUBMITTING/AMBIGUOUS intents outside the
  configured active venue were ignored at startup.
- Snapshot: `/tmp/online-trader-r30.AoZ1ll/snapshot.json` (SHA-256
  `8ba8d4a99cdff82280400fee8b106cb07252a915bc0c7248f3143e98692b2606`).
- Receipt: `/tmp/online-trader-r30.AoZ1ll/receipt.json` (SHA-256
  `3c79c67ee3e9d191e622ca2b85bed2a7d720e92157f498b09b730b20b5774472`).
- Ownership verification passed for the Timescale adapter and subscriber. Enabled execution now
  raises on incomplete intent state belonging to another venue rather than declaring startup safe.

## R31/R32 GREEN - bounded stable recovery paging and obsolete API removal

- Primary RED covered complete stable page traversal, a high-water mark excluding mid-pass inserts,
  bounded page size, and all callers using the page API.
- R31 snapshot `/tmp/online-trader-r31.JwA5fc/snapshot.json` (SHA-256
  `bedcaae6a21f4917f367bdbedc6487ce856bb5850f02f6f1ab65e6bdfacacc46`) and receipt
  `/tmp/online-trader-r31.JwA5fc/receipt.json` (SHA-256
  `bf33e3b36a5277785d32cde7d01189003bea6fb21f70f0d97e13e2d9c3c8a01a`).
- R32 snapshot `/tmp/online-trader-r32.BxEgFp/snapshot.json` (SHA-256
  `8c42cafb30a7f82dde5b5a9a7ea3904d752fe4a638a0b0af3a9f75009b9e16d8`) and receipt
  `/tmp/online-trader-r32.BxEgFp/receipt.json` (SHA-256
  `93a4495b7025e1bea24689df82a36dd893dd3d7b60f9eac0cb5925f9922a0055`).
- Both validators passed. Watcher, armer, and startup reconciliation use bounded tuple-cursor paging;
  the obsolete unbounded exported `LoadOpenBrackets` method is absent. Orders/storage tests passed.

## R33/R34 - rejected cumulative replay and authoritative position replacement

- R33/R33B explored rebuilding positions by replaying cumulative order snapshots. Although the
  exact-decimal implementation passed its local tests, review rejected the model because incomplete
  history and already-applied cumulative fills can double count or lose exposure. R33 snapshot
  `/tmp/online-trader-r33.a3QOT7/snapshot.json`; R33B snapshot
  `/tmp/online-trader-r33b.MUimEh/snapshot.json` (SHA-256
  `9ef0a676a60d7d7663fa607b1d0be056a73d4289aa4db28739a3caa1c7b266dd`) and receipt
  `/tmp/online-trader-r33b.MUimEh/receipt.json` (SHA-256
  `6a94244ddae2bcd032bf2b30c51f3ae6b42bf565118d988361467d90c14325a3`).
- The rejected design was superseded rather than accepted as the final contract.
- R34 replaced it with schema-qualified authoritative `positions` snapshots, serialized refresh per
  venue/symbol, and replay repair. It also scopes exchange ID ownership by venue and symbol across
  Engine, BFF, and migration 038, and removes the obsolete draft first-fill migration.
- R34 snapshot `/tmp/online-trader-r34.vLKsiH/snapshot.json`; final R34B snapshot
  `/tmp/online-trader-r34b.WgM6Vb/snapshot.json` (SHA-256
  `ac9c3627b9acdeabdd0d36c695c2e1727b5197d29adbceaa2f4ecf52bdc1f09c`) and receipt
  `/tmp/online-trader-r34b.WgM6Vb/receipt.json` (SHA-256
  `46ce5cb464067e986e6c860daef36b9180937e66da07747f4a5277973abd2f40`).
- Final ownership validation passed. Primary acceptance passed BFF `46` suites / `442` tests,
  BFF PostgreSQL `12/12`, and Engine full `1720` at that checkpoint.

## R35 GREEN - exchange observation-time fence

- Primary RED proved same-quantity average corrections needed exchange observation ordering and
  every live/replay/finalization caller needed to propagate the exchange timestamp.
- Snapshot: `/tmp/online-trader-r35.7GgmsM/snapshot.json` (SHA-256
  `01a831519026810e5048ec39727c28c1adc8e012edfd23ba72403e0610f3857d`).
- Receipt: `/tmp/online-trader-r35.7GgmsM/receipt.json` (SHA-256
  `b5d41f4569b8942dd14a2941a2cc171612cdbe1e9552a4581890472912c35f8c`).
- Ownership verification passed for seven Router files plus migration 043. Router stores monotonic
  cumulative quantity and observation-fenced averages; futures and spot REST/websocket/replay paths
  preserve exchange update time without local wall-clock substitution. Full Router tests and gates
  passed at that checkpoint.

## R36 GREEN - late authoritative full fill and same-quantity Engine correction

- Primary RED proved the Engine inbox parked a valid newer full fill after CANCELED/EXPIRED and the
  order projection froze a strictly newer same-quantity FILLED average correction.
- Snapshot: `/tmp/online-trader-r36.zCg8Fg/snapshot.json` (SHA-256
  `e02dc01d2bfa7163c282d26cb819bf22bc37dcde14f8ef240cf56afea52efa48`).
- Receipt: `/tmp/online-trader-r36.zCg8Fg/receipt.json` (SHA-256
  `6f8e4aca1982e6ed03ea4221ba5fb38b5a75e427ec5ffb7a17d9a8e5dd6b1a64`).
- Ownership verification passed for `order_update_inbox.py` and `timescale_adapter.py`. Terminal
  upgrades require a complete positive larger fill with present nondecreasing observation time;
  FILLED may correct only average/time at the same quantity with a strictly newer observation.
- Primary focused GREEN passed `38` unit and `3` real-PostgreSQL tests; the broader affected Engine
  files passed `60` unit and `45` integration tests.

## R37C/R37B GREEN - coherent observation tuple, first-fill chronology, and futures timestamp

- The first R37 handoff was rejected because the locked production allowlist omitted
  `app/router/internal/rest/types.go`. No partial implementation was accepted.
- R37C snapshot `/tmp/online-trader-r37c.RymEc9/snapshot.json` (SHA-256
  `3b27047249a72d9d072d48040f535a75395564bbaebce0462986ecd2178205c0`) and receipt
  `/tmp/online-trader-r37c.RymEc9/receipt.json` (SHA-256
  `4d046d3bdeb3bc1538a18b1d2cb39f8485a83dde92c4f40eb6704e37f1ccb125`) verified exact restoration
  of the three partially edited production files.
- R37B snapshot `/tmp/online-trader-r37b.camY68/snapshot.json` (SHA-256
  `747de91446a684ff74338a20fcb92797c0f69a2e128584e464d9518b4b447374`) and receipt
  `/tmp/online-trader-r37b.camY68/receipt.json` (SHA-256
  `608b5b37fe3e3d5c32fca24e2ebdb89556561d6c6de0ec82fe6c117cb1512b6e`) passed the ownership
  validator for exactly four production files.
- Finalization now chooses quantity, average, and timestamp from one coherent observation; a durable
  quantity without an equal observation preserves durable average/time. `orders.first_fill_ts` is
  set once on the true zero-to-positive transition. Futures placement decodes `transactTime` and
  uses exchange update-time fallback rather than wall clock.
- Primary focused GREEN passed all three locked contracts. A full Router run exposed only a test
  comparing equal timestamp instants with different `time.Location` values; the primary corrected
  that test-only assertion to compare the instant, after which the complete Router suite passed.

## R38 GREEN - preserve exchange time through the Router outbox

- Frozen-scope QCHECK found that Router stored `execution_observed_at` but migration 042 emitted
  database `CURRENT_TIMESTAMP`, allowing a delayed stale full fill to appear newer to Engine/BFF.
- Primary RED command:
  `TEST_DATABASE_URL=postgresql://trading_user:your_secure_password_here@localhost:55432/trading_platform_test go test ./internal/storage -run 'TestBracketRepo_UpdateLegExecutionProgressFencesSameQuantityAverageCorrectionsByObservationTime' -count=1`.
  It failed with expected exchange time `2026-03-21T20:06:00Z` and actual database arrival time
  `2026-08-23T05:48:12.104459Z`.
- Snapshot: `/tmp/online-trader-r38.dQ7hKz/snapshot.json` (SHA-256
  `c1e6fe0fe10d3d3b29063aacf0e37721be8e77f278a3f23f2aade39d1a841c34`).
- Receipt: `/tmp/online-trader-r38.dQ7hKz/receipt.json` (SHA-256
  `04b2cd6d602b9c377a1f35492c525f33d3f4858b514a2fe4baf1fe6155025d4d`).
- Ownership verification passed for exactly migration 043. Its replacement trigger function is
  byte-for-semantics equal to migration 042 except `update_time` is
  `COALESCE(NEW.execution_observed_at, CURRENT_TIMESTAMP)`. Migration 042 and all protected files
  remained unchanged; applying migration 043 twice passed.
- Primary focused GREEN and the full Router storage package passed against PostgreSQL.

## Frozen integrated QCHECK (2026-08-23 12:55 +07)

- Scope was frozen to the already-touched Engine, Router, BFF, and migrations 036-043 durable
  execution-success/order-update surface. No P0 or P1 finding remained after R38.
- Non-blocking P2 follow-up: Router currently accepts a larger cumulative quantity even when its
  exchange observation time is older. A `0.01 @ T6` partial followed by delayed `0.02 @ T4` can make
  Router terminal while Engine retains the newer partial and alert/event consumers observe FILLED.
  This is explicitly dispositioned as a post-PR follow-up under the user-authorized bounded stop
  rule; it does not expand this branch.
- No LOW finding. The review found no additional defect in ACK/projection atomicity, leased
  snapshot-before-order delivery, restart recovery, identity scoping, BFF position refresh
  serialization, migration ordering/rerunnability, or first-fill chronology.

## Final frozen-candidate gates (2026-08-23 13:04 +07)

- Full Engine non-integration: `1723 passed, 2 skipped, 45 deselected`; affected real-PostgreSQL
  integration files: `45/45`.
- Full Router with real PostgreSQL: every package passed.
- Full BFF: `46` suites / `442` tests; order-update PostgreSQL reconciliation: `12/12`.
- Full UI: `97` files / `1380 passed, 1 skipped`.
- Three consecutive affected repeats passed. Every repeat ran Engine `130` unit plus `45`
  real-PostgreSQL, Router `binance`/`orders`/`storage`, BFF `89` unit plus `12`
  real-PostgreSQL tests.
- Router gofmt, `go vet ./...`, `golangci-lint run ./...`, and `go build ./...` passed.
- BFF non-mutating ESLint, Prettier, TypeScript, contract synchronization, and direct Nest build
  passed. UI lint, Prettier, typecheck, and optimized production build passed with the same four
  pre-existing warnings.
- Engine Ruff check passed repository-wide; all `22` changed Python files pass Ruff format; the
  repository-prescribed focused MyPy command passed all `11` source files. The all-tree Ruff format
  check still reports three unchanged pre-existing files (`core/error_handling.py`,
  `monitoring/pipeline_health_service.py`, and `retest/__init__.py`); no candidate file is affected.
- `git diff --check` passed. The first three-repeat harness attempt used the Engine directory for a
  Go command and stopped before Router tests; it was discarded as a harness error and the complete
  three-run sequence restarted from run 1.
- Root `make ci` remains intentionally unused because it invokes BFF `eslint --fix`, violating the
  primary production-write boundary. Engine `python -m build` remains unavailable in the existing
  virtualenv because the pre-existing `build` module is absent; executable tests, lint, typecheck,
  Router/BFF/UI builds, migration reruns, and runtime wiring gates passed.

### Final wiring verification

| Component | Non-test call site | Registration/config load | Schema/contract match |
|---|---|---|---|
| Atomic Engine ACK | `router_execution_subscriber.py` builds projections and commits ACK | subscriber is constructed/start-drained from `main.py` | migration 036 ledger plus `orders`/`execution_intents`; rollback/replay PostgreSQL tests |
| Success delivery | subscriber claims SNAPSHOT before ORDER_PLACED and checkpoints with a lease fence | enabled execution startup begins the recovery/drain worker | migration 036 payload, sequence, lease, retry, and stable identity contracts |
| Router recovery/finalization | watcher, armer, replay, and startup reconciler persist then finalize cumulative entry execution | Router main constructs the concrete `BracketRepo` paths | migrations 042/043, stable client ID, bounded cursor, finalization lease, exact protective quantity |
| Exchange observation | Binance REST/websocket mapping passes exchange time to `UpdateLegExecutionProgress` | common spot/futures execution paths use the same repository | `bracket_legs.execution_observed_at`; migration 043 emits the accepted exchange time to outbox `update_time` |
| Engine order update | authenticated webhook claims inbox and performs the canonical projection update | FastAPI route uses initialized DB and event-bus services | terminal/quantity/time monotonicity, fixed-point decimals, venue+symbol identity, contiguous inbox delivery |
| BFF reconciliation | internal trading controller calls the keyed service/repository transaction | trading module registers controller, service, and repository | exact DTO, schema-qualified authoritative position snapshot, per-venue/symbol serialization |

## Review (2026-08-23 13:10 +07) - staged frozen working tree

### Reviewed

- Repo: `/Users/subhajlimanond/.codex/worktrees/online-trader-engine-durable-success-boundary`
- Branch: `codex/engine-durable-success-boundary`
- Scope: staged working tree versus `9ecd69dcd920b3ab2bb759559841c29e5a2fbb26`
- RepoPrompt deep staged snapshot: `2026-08-23/1308` (`76` files, `+14378/-961`) with focused
  final-review context across Engine, Router, BFF, migrations 036-043, and executable tests.
- Commands run: staged diff inventory/artifacts; targeted current-source reads; full Engine/Router/
  BFF/UI tests; real-PostgreSQL Engine/Router/BFF tests; three affected repeats; Ruff, MyPy, gofmt,
  go vet, golangci-lint, Go build, ESLint, Prettier, TypeScript, Nest/Next builds, migration reruns,
  and `git diff --check`.

### Findings

CRITICAL

- No findings.

HIGH

- No findings.

MEDIUM

- Non-blocking follow-up: a higher cumulative Router fill may be accepted even when its exchange
  observation time is older. `app/router/internal/storage/bracket_repo.go:277-299` advances quantity
  and can move `execution_observed_at` backward when quantity increases; migration 043 then emits
  that accepted observation. Engine admits the non-terminal inbox transition at
  `app/engine/execution/order_update_inbox.py:64-67`, while projection ordering at
  `app/engine/adapters/db/timescale_adapter.py:1710+` can retain the newer partial row and the route
  can still publish the stale FILLED event. Scenario: `0.01 @ T6` followed by delayed `0.02 @ T4`
  may leave Router terminal, Engine/BFF partial, and event consumers observing FILLED. Fix direction
  for a follow-up is an explicit larger-quantity/older-observation policy shared across Router,
  Engine, and BFF, with a real-PostgreSQL trigger-to-inbox regression. Disposition: accepted P2 under
  the user-authorized frozen-scope rule; it does not block this PR or expand this branch.

LOW

- No findings.

### Open Questions / Assumptions

- External success effects remain intentionally at-least-once across the final effect-to-checkpoint
  crash window; downstream consumers must deduplicate the stable event identity.
- This PR qualifies source and local database behavior. It does not authorize runtime activation,
  production deployment, or the separate readiness/U8-U14 program.
- The Engine all-tree formatter debt in three unchanged files and the UI's four existing warnings
  are outside the frozen candidate; every changed file and relevant build passes.

### Recommended Tests / Validation

- Completed: full Engine `1723`, Router all packages, BFF `442` plus PostgreSQL `12`, UI `1380` plus
  one skip, all builds/static checks, migration 043 applied twice, and three complete affected
  repeats (`130` Engine unit, `45` Engine PostgreSQL, Router binance/orders/storage, `89` BFF unit,
  `12` BFF PostgreSQL per repeat).
- Follow-up only: add the larger-quantity/older-observation cross-boundary regression when the shared
  policy is selected.

### Rollout Notes

- Apply migrations 036 through 043 in order before deploying the corresponding Engine/Router/BFF
  binaries. Migration 043 is additive and rerunnable and replaces only the bracket-leg outbox
  function's timestamp source.
- Preserve disabled/dark runtime state; this lifecycle ends at source merge, exact local-main
  landing, and post-merge local verification.

### Formal disposition

- Formal `g-check`: PASS for the frozen scope. No CRITICAL/HIGH/P0/P1 finding remains.
- The single MEDIUM/P2 is explicitly accepted as a non-blocking follow-up under the bounded
  completion rule. No production remediation is authorized or required in this branch.
