# Testnet Sanity Runbook — Spot OCO Exits (C5) & Startup Reconciler (C6)

**Date**: 2026-07-06
**Applies to**: `app/router` order-lifecycle campaign, deliverables C5 (#197) + C6 (#198), flag-wired by C7 (#199)
**Purpose**: A short, manual, human-in-the-loop walkthrough that proves — against Binance spot **testnet** — that a deferred bracket arms its exits as an OCO pair on entry fill (C5) and that the startup reconciler repairs open brackets and gates readiness across a crash (C6). Run this as a confidence check **before** committing to the 7-day automated soak.

---

## TL;DR

1. Bring up the dev stack against testnet (`make dev`) with `BRACKET_LEGS_ON_FILL=true` (already the default in `docker-compose.dev.yml` after C7).
2. Place **one deferred spot bracket** with `scripts/place_test_bracket.py` — the UI cannot do this (see "Why not the UI").
3. Watch the bracket advance `RESERVED → ENTRY_PLACED → ENTRY_FILLED → LEGS_PLACED` and its OCO exits appear — in Postgres and on the `/soak` panel.
4. Kill the router mid-flight, restart it, and confirm the reconciler settles the bracket and `/readyz` flips `503 → 200`.

Pass criteria are the checklist at the end.

---

## Why not the UI

The UI order form → BFF `POST /trading/orders` path **cannot** exercise C5/C6. The BFF omits `client_order_ids` when it calls the router's `/place_bracket` (`app/bff/src/router-client/router-client.service.ts`), and the router only defers exits and reserves a durable `brackets` row when `client_order_ids.main` is set (`app/router/internal/orders/manager.go` `spotLegsDeferred`). Without it, exits place synchronously and no bracket row is persisted — nothing for the watcher or reconciler to act on. So this runbook drives the router directly, with `client_order_ids` set, via the helper script.

---

## 0. Prerequisites

- Binance **spot testnet** API key/secret (create at <https://testnet.binance.vision>).
- Docker + the repo's `make` targets.
- A funded testnet spot balance in the quote asset (USDT) for the symbol you use.

### Environment profile (`.env`)

| Variable                                           | Value          | Why                                                                                          |
| -------------------------------------------------- | -------------- | -------------------------------------------------------------------------------------------- |
| `EXECUTION_MODE`                                   | `spot_testnet` | Engine-side execution lock (part of the soak-validated profile; the router does not read it) |
| `ROUTER_EXECUTION_ENV`                             | `testnet`      | Router forces testnet base URLs in code — its own testnet lock                               |
| `TRADING_MODE`                                     | `spot`         | Enables the spot client                                                                      |
| `BRACKET_LEGS_ON_FILL`                             | `true`         | Defers exits → spot OCO on fill (C5). Default in dev compose after C7                        |
| `SPOT_RECONCILIATION_ENABLED`                      | `true`         | Periodic spot reconciler                                                                     |
| `I_UNDERSTAND_LIVE_TRADING`                        | _unset_        | Safety interlock — must stay unset                                                           |
| `BINANCE_SPOT_API_KEY` / `BINANCE_SPOT_SECRET_KEY` | _testnet keys_ | (or the legacy `BINANCE_API_KEY` / `BINANCE_SECRET_KEY`)                                     |
| `SECURITY_REQUIRED_API_KEY`                        | _a token_      | Router requires it; the router fatals at boot if empty                                       |
| `ROUTER_API_KEY`                                   | **same token** | The BFF/soak/helper send this; **must equal** `SECURITY_REQUIRED_API_KEY`                    |

> The automated soak (`scripts/run_testnet_soak.py`) validates this whole profile via `validate_soak_environment`; this runbook uses the same variables.

---

## 1. Bring up the stack

```bash
make dev            # docker compose -f docker-compose.dev.yml up --build (runs in the foreground)
```

> `make dev` runs in the foreground; open a **second terminal** for the `logs` / `exec` / `kill` / `up -d router` steps below.

Wait until the router is up, then confirm the deferred-legs + reconciler stack booted:

```bash
docker compose -f docker-compose.dev.yml logs router | grep -E \
  "Durable bracket reservations enabled|spot exits placed as OCO|Entry fill watcher started|Startup reconciliation complete"
```

All four lines should be present. On a fresh DB the reconciler sweeps zero brackets — that is expected.

Confirm readiness lifted:

```bash
curl -s localhost:8001/readyz          # {"status":"ready"} once the startup pass completed
```

---

## 2. Place a deferred spot bracket (C5)

```bash
export SECURITY_REQUIRED_API_KEY=<your token>   # or ROUTER_API_KEY
app/engine/.venv/bin/python scripts/place_test_bracket.py --symbol BTCUSDT --notional-usdt 25
```

The helper fetches a testnet reference price, builds a resting LIMIT BUY bracket **with `client_order_ids`**, POSTs it, and prints the response plus the leg ids to watch. Expect:

- `status` `200` and **`legs_pending_trigger: true`** in the response (the helper warns loudly if it is not — that means the flag or `DATABASE_URL` is missing).
- The entry rests below market, so it fills within seconds to minutes depending on testnet flow.

### Observe C5

Watch the bracket row advance (pgAdmin at `localhost:5050`, or psql):

```bash
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U trading_user -d trading_platform -c \
  "SELECT status, entry_client_order_id FROM brackets ORDER BY created_at DESC LIMIT 3;"

docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U trading_user -d trading_platform -c \
  "SELECT role, tp_index, client_order_id, status FROM bracket_legs \
   WHERE bracket_id = (SELECT bracket_id FROM brackets ORDER BY created_at DESC LIMIT 1) \
   ORDER BY role, tp_index;"
```

**C5 pass**: the bracket goes `ENTRY_PLACED → ENTRY_FILLED → LEGS_PLACED`, and the TP/SL legs go `PLANNED → PLACED` once the entry fills. On the exchange the two exit orders form one OCO list (the sibling auto-cancels when either fills).

You can also open the **`/soak` panel** in the UI (`localhost:3000/soak`) — readiness shows _Ready_ and the reconcile counters reflect the last startup pass. (The panel is read-only; it does not trigger a pass.)

---

## 3. Simulate a crash and verify the reconciler (C6)

The interesting C6 window is a crash **after the entry fills but before the watcher arms the exits**. With a 2s poll that window is short, so the most reliable manual test is: place the bracket, let the entry fill, kill the router before/while it arms, then restart.

```bash
docker compose -f docker-compose.dev.yml kill router      # hard stop
# ... entry may fill on the exchange while the router is down ...
docker compose -f docker-compose.dev.yml up -d router      # restart
```

On restart the router holds `/readyz` at `503` while the startup reconciler runs, then flips to `200`:

```bash
# Immediately after restart, expect 503 "reconciling", then 200 "ready"
for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code} " localhost:8001/readyz; sleep 1; done; echo
```

Inspect the reconcile result read-only (no side effects), or trigger an on-demand pass:

```bash
# Read-only: last completed pass (added in the soak/health-panel PR).
# GET nests the counters under `.summary`: {has_run, last_run_at, summary:{unrepaired_legs, errors, …}}
curl -s -H "X-API-Key: $SECURITY_REQUIRED_API_KEY" localhost:8001/internal/reconcile | jq

# On-demand: run a pass now (mutating; 409 if one is already in flight).
# POST returns the summary counters at the top level.
curl -s -X POST -H "X-API-Key: $SECURITY_REQUIRED_API_KEY" localhost:8001/internal/reconcile | jq
```

**C6 pass**: after restart the bracket is repaired — its exits are recorded/settled (not left `PLANNED`/`PLACING`), the reconcile summary shows `unrepaired_legs: 0` and `errors: 0`, no duplicate exit orders exist on the exchange, and `/readyz` reached `200`. The `/soak` panel reflects the same counters.

---

## Pass / fail checklist

Carry these into the soak sign-off. **Fail** on any unticked box.

- [ ] All four router startup markers present (durable reservations, spot OCO on fill, watcher started, reconciliation complete).
- [ ] Helper response had `legs_pending_trigger: true` (exits genuinely deferred).
- [ ] Bracket advanced `ENTRY_FILLED → LEGS_PLACED`; TP/SL legs reached `PLACED`.
- [ ] Exactly one OCO list per TP slice on the exchange; sibling auto-cancelled on the other's fill (no orphan, no duplicate).
- [ ] **`GET /api/v3/orderList` returns a _completed_ list by `origClientOrderId`** — the C5/C6 recovery paths treat a confirmed `-2013` as safe-to-retry, so if a filled list read as "absent" a re-POST could double-sell. Verify once: place OCO, let it complete, query it.
- [ ] Duplicate `listClientOrderId` and price-relation rejections return `-2010` with the expected messages (the router's matchers depend on the text).
- [ ] After a mid-flight kill + restart, the reconciler settles the bracket with `unrepaired_legs: 0`, `errors: 0`, and **no double placement**.
- [ ] `/readyz` observed `503 → 200` across the restart.

---

## Cleanup

```bash
# Cancel any resting testnet orders for the symbol, then stop the stack
curl -s -X POST -H "X-API-Key: $SECURITY_REQUIRED_API_KEY" \
  -d '{"scope":"SPOT","symbols":["BTCUSDT"]}' localhost:8001/cancel_open_orders | jq
make dev-stop
```

Testnet balances and orders are disposable; no production data is touched.
