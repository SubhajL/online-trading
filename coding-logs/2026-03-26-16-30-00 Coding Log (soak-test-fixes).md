# Soak Test Fixes — 5 Issues from 24-Hour Testnet Run

## Overview

Fixed 5 issues surfaced by the 24-hour testnet soak test (launched 2026-03-24T23:18:55Z, PID 42069). The soak ran 34+ hours (zombie due to `--keep-running`) and uncovered critical bugs in bracket order placement and soak infrastructure.

## Files Changed

| File                                         | Fix                                        | Language |
| -------------------------------------------- | ------------------------------------------ | -------- |
| `app/router/internal/orders/manager.go`      | Fix 1 (ID length) + Fix 2 (algo pre-check) | Go       |
| `app/router/internal/orders/manager_test.go` | Tests for fixes 1 & 2                      | Go       |
| `scripts/launch_testnet_soak.py`             | Fix 3 (caffeinate wrapper)                 | Python   |
| `scripts/run_testnet_soak.py`                | Fix 4 (timeout + dedup)                    | Python   |
| `tests/test_launch_testnet_soak.py`          | Tests for fix 3                            | Python   |
| `tests/test_run_testnet_soak.py`             | Tests for fix 4                            | Python   |

## Fix 1: FAILSAFE Client Order ID Exceeds 36-Char Binance Limit (CRITICAL)

### Problem

`generateClientOrderID(bracketID, "FAILSAFE")` produced 37-char IDs (`{8}_{8}_{19}` = 37). Binance regex: `^[a-zA-Z0-9-_]{1,36}$`. When entry filled but SL failed (MAX_NUM_ALGO_ORDERS), the failsafe market close also failed due to illegal ID length — leaving positions orphaned with no exit.

### Solution

- Truncate `orderType` suffix to max 4 chars: `FAILSAFE` → `FAIL`
- Use hex encoding for timestamp (10 hex chars vs 19 decimal)
- Added `atomic.Uint64` counter for uniqueness guarantee (nanosecond collisions on macOS)
- Max ID length: 31 chars (`{8}_{4}_{6}_{10}`)

### TDD Evidence

```
=== RUN   TestGenerateClientOrderID_AllSuffixesWithin36Chars/FAILSAFE
--- PASS (before fix: FAIL at 37 chars, after fix: PASS at 31 chars)
=== RUN   TestGenerateClientOrderID_Uniqueness
--- PASS (before fix: FAIL with nanosecond collisions, after fix: PASS with atomic seq)
```

### Tests

- `TestGenerateClientOrderID_AllSuffixesWithin36Chars` — table-driven across MAIN, SL, TP1, TP2, TP3, FAILSAFE
- `TestGenerateClientOrderID_Uniqueness` — 100 rapid calls produce 100 distinct IDs

## Fix 2: Algo Order Pre-Check Before Bracket Placement (CRITICAL)

### Problem

Engine's decision pipeline placed bracket orders without checking Binance's algo order count (5 per symbol). When slots filled, new SL placements failed with `MAX_NUM_ALGO_ORDERS` — triggering failsafe (which also failed due to Fix 1). Compose logs showed 26 occurrences.

### Solution

- New `countAlgoOrders(ctx, client, symbol)` helper counts open STOP_LOSS, STOP_LOSS_LIMIT, TAKE_PROFIT, TAKE_PROFIT_LIMIT orders
- Pre-check in `PlaceBracketOrder` before placement: rejects with clear error if count ≥ 5
- Degrades gracefully: logs warning and proceeds if exchange query fails

### Tests

- `TestCountAlgoOrders_CountsOnlyAlgoTypes` — table-driven: mixed types, all algo, no algo, empty

## Fix 3: Caffeinate Wrapper for macOS Sleep Prevention (HIGH)

### Problem

Docker services died ~16 hours into the soak, likely from macOS sleep. Soak runner (native Python) survived but Docker containers stopped.

### Solution

- `wrap_with_caffeinate(command)` prepends `["caffeinate", "-i", "--"]` on Darwin
- Wired into `launch_detached_soak()` before `Popen`
- No-op on non-Darwin platforms

### Tests

- `test_wrap_with_caffeinate_on_darwin` — mocks `sys.platform = "darwin"`, verifies prefix
- `test_wrap_with_caffeinate_skips_on_linux` — mocks `sys.platform = "linux"`, verifies passthrough

## Fix 4: Report Robustness — Timeout + Dedup (HIGH)

### Problem

1. `collect_compose_logs()` called `_run_command` without timeout — if Docker is dead, `docker-compose logs` hangs forever, preventing `report.json` from being written
2. `build_recommendations()` produced 9 identical entries for repeated smoke failures

### Solution

1. Added `timeout=120` to `collect_compose_logs()` with `TimeoutExpired` catch → records failure and continues
2. Added dedup via `seen` set in `build_recommendations()`

### Tests

- `test_build_recommendations_deduplicates_identical_entries` — 3 identical smoke failures → 1 recommendation
- `test_build_recommendations_preserves_distinct_entries` — 2 different failures → 2 recommendations

## Fix 5: Kill Zombie Soak Process (OPERATIONAL)

Confirmed PID 42069 was the soak runner via `ps -p 42069 -o pid,command`. Sent `kill 42069`, verified termination.

## Quality Gates

| Gate                          | Result              |
| ----------------------------- | ------------------- |
| Go build (`go build ./...`)   | PASS                |
| Go tests (`go test ./...`)    | 15/15 packages PASS |
| Python compile (`py_compile`) | PASS                |
| Python tests (soak suite)     | 25/25 PASS          |
| Ruff lint                     | PASS                |

## Wiring Verification

| Component                                 | Call Site (non-test)                                                                                     | Verified |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------- | -------- |
| `generateClientOrderID` (modified)        | `bracket.go:placeSpotBracket`, `bracket.go:placeFuturesBracket`, `bracket.go:closeUnsafeFilledSpotEntry` | YES      |
| `countAlgoOrders` (new)                   | `manager.go:PlaceBracketOrder` line ~300                                                                 | YES      |
| `algoOrderTypes` (new)                    | `manager.go:countAlgoOrders`                                                                             | YES      |
| `clientOrderIDSeq` (new)                  | `manager.go:generateClientOrderID`                                                                       | YES      |
| `wrap_with_caffeinate` (new)              | `launch_testnet_soak.py:launch_detached_soak`                                                            | YES      |
| `collect_compose_logs` timeout (modified) | `run_testnet_soak.py:run()`                                                                              | YES      |
| `build_recommendations` dedup (modified)  | `run_testnet_soak.py:_build_report_payload`                                                              | YES      |
