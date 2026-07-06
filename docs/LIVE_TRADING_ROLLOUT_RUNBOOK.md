# Live Trading Rollout Runbook

This runbook defines the promotion path for this repo from research to real-money trading.

## Current Repo Status

- Current posture remains `testnet soak`, not `mainnet canary`.
- Do not promote while the soak runner can overrun without a final `report.json`.
- Do not promote while BFF schema/runtime gaps can crash the alert path.

## Global Change Routing Rule

Apply this rule before promoting from any stage below:

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - stay on `testnet soak`
    - fix it there
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - then `live paper/shadow`
    - then return to `testnet soak`

## Promotion Path

1. `backtest`
2. `live paper/shadow`
3. `testnet soak`
4. `mainnet canary`
5. `mainnet tiny-risk soak`
6. `progressive ramp`

## Stage 1: Backtest

### Goal

- Prove the strategy has enough quality to justify live validation.

### Entry Gate

- Strategy branch is frozen for the run.
- Data inputs, fees, and slippage assumptions are explicit.

### Commands

```bash
make test-engine
make test-level LEVEL=4
make lint-engine
```

### Go

- Backtest results remain acceptable after realistic fees and slippage.
- Drawdown, win/loss distribution, and walk-forward behavior are within plan.

### No-Go

- Results collapse after costs.
- Behavior only works on a narrow symbol or timeframe slice.
- There is obvious leakage or overfitting.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - do not restart from backtest only for that change
    - but do not skip `testnet soak` later
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - stay on `backtest`
    - do not promote until backtest is green again

## Stage 2: Live Paper / Shadow

### Goal

- Prove decision quality and runtime coherence on live market data without real execution risk.

### Entry Gate

- Latest backtest sign-off is green.
- Paper/live harness can run continuously.

### Commands

```bash
make paper-test
make paper-test-live
make paper-live
```

### Go

- Signals, sizing, and exits behave as expected on live data.
- Dashboards, alerts, and persisted state remain coherent for `3-7` days.

### No-Go

- Repeated stale-data or state-divergence incidents.
- Alerts, BFF views, or paper state do not converge.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - stay on `testnet soak`
    - do not promote on paper evidence alone
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - re-run `live paper/shadow`
    - then return to `testnet soak`

## Stage 3: Testnet Soak

### Goal

- Prove long-running execution plumbing, cancel/reconcile behavior, auth, and health handling.

### Entry Gate

- `EXECUTION_MODE=spot_testnet`
- `ROUTER_EXECUTION_ENV=testnet`
- `TRADING_MODE=spot`
- Required internal auth tokens are present.
- Required DB tables are present before launch.

### Commands

```bash
make test-preflight
make test-router
make test-bff
python3 scripts/launch_testnet_soak.py --duration-seconds 86400 --enable-order-smoke --keep-running
docker-compose -f docker-compose.dev.yml ps
curl -fsS http://localhost:8001/healthz
curl -fsS http://localhost:8002/api/health
```

### Go

- Full `24-72h` run completes with final `report.json`.
- Engine, router, and BFF stay healthy throughout the run.
- Order smoke place/cancel/reconcile stays within the pass bar.
- No auth drift, wrong-venue execution, or orphaned exits.

### No-Go

- Missing final `report.json`.
- Sustained unhealthy service state.
- Repeated order-smoke failures.
- Wrong venue, auth mismatch, state divergence, or missing schema.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - stay on `testnet soak`
    - fix it there
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - then `live paper/shadow`
    - then return to `testnet soak`

## Stage 4: Mainnet Canary

### Goal

- Validate real-money behavior with minimum notional and tight risk limits.

### Entry Gate

- Latest `testnet soak` has a clean final report.
- Kill switch and emergency-close drill were executed successfully.
- Symbol allowlist is reduced to the smallest practical set.

### Commands

```bash
make test-preflight
make ci
docker-compose -f docker-compose.dev.yml ps
curl -fsS http://localhost:8001/healthz
curl -fsS http://localhost:8002/api/health
```

### Go

- Real fills, fees, balances, and reconciled order states match expectations.
- One symbol, one strategy, and minimum notional all behave correctly.

### No-Go

- Any unexplained reject.
- Any wrong-size order.
- Any orphaned stop or take-profit.
- Any divergence between router, DB, and operator view.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - go back to `testnet soak`
    - do not keep promoting on prior canary evidence
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - then `live paper/shadow`
    - then return to `testnet soak`

## Stage 5: Mainnet Tiny-Risk Soak

### Goal

- Prove unattended mainnet stability at tiny exposure.

### Entry Gate

- Mainnet canary is signed off.
- Daily loss limit and hard kill switch are active.

### Commands

```bash
make test-preflight
docker-compose -f docker-compose.dev.yml ps
curl -fsS http://localhost:8001/healthz
curl -fsS http://localhost:8002/api/health
```

### Go

- `24-72h` unattended run completes without service crash, state drift, or manual intervention.

### No-Go

- Emergency-close flow is untrusted.
- Any service crash or unhealthy loop persists.
- Any reconciliation or alerting gap requires operator repair.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - go back to `testnet soak`
    - re-earn mainnet promotion
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - then `live paper/shadow`
    - then return to `testnet soak`

## Stage 6: Progressive Ramp

### Goal

- Increase risk and scope slowly only after repeated clean tiny-risk operation.

### Entry Gate

- Mainnet tiny-risk soak is signed off.
- Ramp plan changes only one axis at a time.

### Commands

```bash
make ci
make test-preflight
docker-compose -f docker-compose.dev.yml ps
```

### Go

- Exposure increases remain controlled and each new level completes a clean observation window.

### No-Go

- Size and scope both increase at once.
- There is any unresolved runtime incident from the prior level.

### Change Routing Rule

- If you changed execution, router, BFF, auth, persistence, health checks, cancel logic, or reconcile logic:
    - go back to `testnet soak`
    - rebuild runtime confidence there
- If you changed strategy, signals, sizing, risk model, or entry/exit logic:
    - go back to `backtest`
    - then `live paper/shadow`
    - then return to `testnet soak`

## Strict Go / No-Go Checklist

Use this before promoting to the next stage. Every row needs an owner, result, and sign-off.

| Gate                  | Command                                                                                                 | Expected Result                                    | Owner | Date/Time | Result       | Sign-Off |
| --------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------- | ----- | --------- | ------------ | -------- |
| Format                | `make format-check`                                                                                     | No formatting diffs                                |       |           | `GO / NO-GO` |          |
| Typecheck             | `make typecheck`                                                                                        | No type errors                                     |       |           | `GO / NO-GO` |          |
| Engine tests          | `make test-engine`                                                                                      | Pass                                               |       |           | `GO / NO-GO` |          |
| Router tests          | `make test-router`                                                                                      | Pass                                               |       |           | `GO / NO-GO` |          |
| BFF tests             | `make test-bff`                                                                                         | Pass                                               |       |           | `GO / NO-GO` |          |
| UI tests              | `make test-ui`                                                                                          | Pass                                               |       |           | `GO / NO-GO` |          |
| Preflight             | `make test-preflight`                                                                                   | Pass or approved warnings only                     |       |           | `GO / NO-GO` |          |
| Stack health          | `docker-compose -f docker-compose.dev.yml ps`                                                           | Core services healthy/up                           |       |           | `GO / NO-GO` |          |
| Router health         | `curl -fsS http://localhost:8001/healthz`                                                               | Success response                                   |       |           | `GO / NO-GO` |          |
| BFF health            | `curl -fsS http://localhost:8002/api/health`                                                            | Success response                                   |       |           | `GO / NO-GO` |          |
| Testnet soak artifact | `ls artifacts/testnet-soak/<run-id>/report.json`                                                        | Final report exists                                |       |           | `GO / NO-GO` |          |
| Soak result           | `cat artifacts/testnet-soak/<run-id>/report.json`                                                       | `overall_status: pass` and no unapproved incidents |       |           | `GO / NO-GO` |          |
| DB schema             | `psql "$DATABASE_URL" -c "select to_regclass('public.alerts'), to_regclass('public.alert_snapshots');"` | Required tables exist                              |       |           | `GO / NO-GO` |          |
| Emergency close       | Operator drill                                                                                          | Completed successfully                             |       |           | `GO / NO-GO` |          |
| Kill switch           | Operator drill                                                                                          | Completed successfully                             |       |           | `GO / NO-GO` |          |

## Stage Sign-Off Template

Copy this block for each promotion decision.

```text
Stage:
Target Promotion:
Build / Commit:
Run ID:
Owner:
Reviewer:
Date:

Backtest Status:
Paper / Shadow Status:
Testnet Soak Status:
Mainnet Canary Status:
Mainnet Tiny-Risk Soak Status:

Open Incidents:
Approved Warnings:
Rollback Trigger:

Final Decision: GO / NO-GO
Owner Sign-Off:
Reviewer Sign-Off:
```
