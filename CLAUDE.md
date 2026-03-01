# Online Trading Platform

## Overview

- **Type**: Modular monolith with three runtime processes
- **Stack**: Python (FastAPI) | Go (Gin) | TypeScript (NestJS/Next.js)
- **Architecture**: Event-driven async pipeline, in-memory pub/sub, separate order router
- **Latency Target**: ≤700-900ms p95 from candle close → order POST

This CLAUDE.md is the **authoritative source** for development guidelines.
Subdirectories contain specialized CLAUDE.md files that extend these rules.

---

## Universal Development Rules

### Code Quality (MUST)

- **MUST** follow TDD: scaffold stub → write failing test → implement
- **MUST** name functions with existing domain vocabulary for consistency
- **MUST** use `import type { … }` for type-only imports (TypeScript)
- **MUST** prefer branded `type`s for IDs: `type UserId = Brand<string, 'UserId'>`
- **MUST** run pre-commit hooks before committing
- **MUST NOT** commit secrets, API keys, or tokens
- **MUST NOT** use `any` type without explicit justification
- **MUST NOT** bypass TypeScript errors with `@ts-ignore`
- **MUST NOT** push directly to main branch

### Best Practices (SHOULD)

- **SHOULD** prefer simple, composable, testable functions over classes
- **SHOULD** default to `type`; use `interface` only when merging is required
- **SHOULD NOT** add comments except for critical caveats; rely on self-explanatory code
- **SHOULD NOT** extract a new function unless reused elsewhere or drastically improves readability

### Testing Rules (MUST)

- **T-1 (MUST)** Colocate unit tests: `*.spec.ts` (TS), `test_*.py` (Python), `*_test.go` (Go)
- **T-2 (MUST)** Separate pure-logic unit tests from DB-touching integration tests
- **T-3 (MUST)** Test the entire structure in one assertion when possible
- **T-4 (SHOULD)** Prefer integration tests over heavy mocking
- **T-5 (SHOULD)** Unit-test complex algorithms thoroughly
- **T-6 (SHOULD)** Use property-based testing (fast-check) for invariants

### Quality Gates (MUST)

```bash
# Before ANY PR - all must pass
make lint && make typecheck && make test
```

---

## Core Commands

### Development

```bash
# Complete setup (Python venv, Node deps, Go deps, git hooks)
make setup

# Start all services with hot reload
make dev

# Individual service development
make dev-engine    # Python engine (uvicorn, port 8000)
make dev-router    # Go router (port 8001)
make dev-bff       # NestJS BFF (port 8002)
make dev-ui        # Next.js UI (port 3000)
```

### Database

```bash
make db-up         # Start PostgreSQL + Redis
make db-migrate    # Run Alembic migrations
make db-reset      # Reset database (WARNING: destroys data)
```

### Testing

```bash
make test          # Run all tests
make test-engine   # Python engine tests (pytest)
make test-router   # Go router tests
make test-bff      # NestJS BFF tests (jest)
make test-ui       # Next.js UI tests (vitest)
make test-coverage # Generate coverage reports
```

### Code Quality

```bash
make lint          # Lint all languages
make lint-fix      # Auto-fix linting issues
make format        # Format all code
make typecheck     # Type check all languages
make security-check # Security scans (bandit, gosec, npm audit)
```

### Building

```bash
make build         # Build all components
make build-docker  # Build Docker images
make prod-build    # Production build
```

---

## Project Structure

### Applications

- **`app/engine/`** → Python trading engine ([see app/engine/CLAUDE.md](app/engine/CLAUDE.md))
  - Single process with async in-memory event bus
  - FastAPI for health/metrics endpoints
  - AsyncIO tasks per (symbol × timeframe) pipeline

- **`app/router/`** → Go order router ([see app/router/CLAUDE.md](app/router/CLAUDE.md))
  - Separate process for order safety and idempotency
  - Handles Spot and USD-M Futures APIs
  - Exchange info caching for rounding rules

- **`app/bff/`** → NestJS Backend-for-Frontend ([see app/bff/CLAUDE.md](app/bff/CLAUDE.md))
  - REST + WebSocket APIs
  - Bridges UI to engine/router

- **`app/ui/`** → Next.js frontend ([see app/ui/CLAUDE.md](app/ui/CLAUDE.md))
  - Lightweight Charts for visualization
  - Real-time WebSocket updates

### Contracts

- **`contracts/`** → JSONSchema event contracts
  - `candles.v1` - OHLCV data from Binance WebSocket
  - `features.v1` - Technical indicators (EMA, RSI, MACD, ATR, BB)
  - `smc_events.v1` - Smart Money Concepts signals (CHOCH, BOS)
  - `zones.v1` - Order blocks and fair value gaps
  - `signals_raw.v1` - Candidate trading signals
  - `decision.v1` - Final trading decisions with position sizing
  - `order_update.v1` - Order status updates from router

### Infrastructure

- **`infra/`** → Docker configs (Redis, Prometheus, Grafana, pgAdmin)
- **`.github/workflows/`** → CI/CD pipelines
- **`scripts/`** → Utility scripts (codegen, integration setup)

---

## Quick Find Commands

### Code Navigation

```bash
# Find Python function definition
rg -n "^def |^async def " app/engine/

# Find Go function definition
rg -n "^func " app/router/

# Find TypeScript component
rg -n "export (function|const) " app/bff/src app/ui/src

# Find event handler
rg -n "subscribe|publish|emit" app/engine/
```

### Testing

```bash
# Find all test files
fd -e py -g "test_*.py" app/engine/
fd -e go -g "*_test.go" app/router/
fd -e ts -g "*.spec.ts" app/bff/ app/ui/

# Run specific test file
pytest app/engine/tests/unit/test_file.py -v
go test -v ./internal/package/...
pnpm --filter @repo/bff test -- --testPathPattern="file.spec"
```

### Dependency Analysis

```bash
# Python dependencies
pip show <package>
rg "import.*<package>" app/engine/

# Go dependencies
go mod why <package>

# Node dependencies
pnpm why <package>
```

---

## Security Guidelines

### Secrets Management

- **NEVER** commit tokens, API keys, or credentials
- Use `.env` for local secrets (already in .gitignore)
- Use environment variables for CI/CD secrets
- PII must be redacted in logs
- Separate Spot/Futures API keys: `BINANCE_SPOT_*` and `BINANCE_FUTURES_*`

### Sensitive Files (DO NOT EDIT without review)

- `.env`, `.env.production`, `.env.local`
- `credentials.json`, `secrets.*`
- Any file containing API keys or tokens

### Safe Operations (CONFIRM before running)

- `git push --force` (especially to main)
- `rm -rf` on directories
- `docker system prune --all --force`
- Database drops or resets
- Production deployments

---

## Git Workflow

### Branch Naming

- Feature: `feature/description`
- Bugfix: `fix/issue-description`
- Service: `svc/service-name`

### Commit Messages (Conventional Commits)

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`

**MUST NOT** refer to Claude or Anthropic in commit messages.

### PR Requirements

- All CI checks must pass (lint, typecheck, test)
- Squash commits on merge
- Delete branches after merge

---

## Event Flow Architecture

```
Binance WS → Ingest (k.x==true) → candles.v1
                    ↓
             Features → features.v1
                    ↓
                SMC → smc_events.v1 + zones.v1
                    ↓
              Retest → signals_raw.v1
                    ↓
             Decision → decision.v1
                    ↓
         Router (Go) → Binance REST → order_update.v1
```

### Critical Implementation Details

1. **WebSocket Handling**: Only emit candle when `k.x == true` (closed)
2. **Idempotency**: Every order includes unique `newClientOrderId`
3. **Database Keys**: `(venue, symbol, tf, open_time)` for candles
4. **Risk Limits**: 0.5% fixed-fractional per trade, ATR-scaled
5. **Futures**: Max 3× leverage, ReduceOnly TPs, STOP_MARKET SL

---

## Performance Targets

| Metric | Target |
|--------|--------|
| Candle close → signals | ≤500ms p95 |
| Decision → Router POST | ≤300ms p95 |
| REST backfill after disconnect | <5s |
| UI chart redraw | <150ms |

---

## Database Schema

TimescaleDB hypertables for time-series data:

- `candles` - OHLCV data with automatic partitioning
- `indicators` - Technical indicator values
- `smc_events` - Structure breaks and change of character
- `zones` - Supply/demand zones and order blocks
- `orders` - Order history with status tracking
- `positions` - Current and historical positions

---

## Available Tools

### Code Search Rules (MUST)

- **MUST** use `mcp__auggie-mcp__codebase-retrieval` (Augment) as the **primary tool** for semantic code search
- **MUST** prefer Augment for: finding implementations, understanding architecture, locating features, exploring unfamiliar code
- **MUST NOT** use Bash `grep`/`rg` or the Grep tool for semantic code understanding
- **SHOULD** use Grep only for exact string matching (error messages, config values, literal text)
- **SHOULD** use Grep for finding all references to a known identifier

**Good Augment queries:**
- "Where is user authentication implemented?"
- "How does the event bus publish messages?"
- "What tests exist for the order router?"

**Use Grep instead for:**
- `"TODO"` - exact string search
- `"class OrderRouter"` - known identifier lookup
- `"error: connection refused"` - error message search

### Standard Tools

- `rg` (ripgrep) for exact string/regex search only
- `git`, `gh` (GitHub CLI)
- `pnpm`, `npm` for Node.js
- `go` for Go projects
- `python`, `pytest` for Python
- `docker`, `docker-compose`

### Tool Permissions

- Read any file
- Write code files
- Run tests, linters, type checkers
- Edit `.env` files (WARNING shown)
- Force push (BLOCKED - ask first)
- Delete databases (ask first)

---

## Remember Shortcuts

Quick commands the user may invoke:

| Command | Action |
|---------|--------|
| `qnew` | Understand CLAUDE.md best practices, follow CONTEXT.md architecture |
| `qplan` | Analyze codebase for consistency, minimal changes, code reuse |
| `qcode` | Implement plan, run tests, prettier, typecheck, lint |
| `qcheck` | Skeptical review: functions + tests + implementation checklists |
| `qcheckf` | Review functions only |
| `qcheckt` | Review tests only |
| `qux` | Output UX test scenarios sorted by priority |
| `qgit` | Add, commit (Conventional Commits), push |

---

## Writing Functions Best Practices

Checklist for evaluating functions:

1. Can you read and easily follow what it's doing?
2. Does it have very high cyclomatic complexity?
3. Are there common data structures that would simplify it?
4. Any unused parameters?
5. Any unnecessary type casts that can move to arguments?
6. Is it easily testable without mocking core features?
7. Any hidden untested dependencies?
8. Is the name the best choice? (brainstorm 3 alternatives)

**SHOULD NOT** refactor out a function unless:
- Reused in multiple places
- Only way to unit-test otherwise untestable logic
- Original is extremely hard to follow

---

## Writing Tests Best Practices

Checklist for evaluating tests:

1. Parameterize inputs; no unexplained literals (42, "foo")
2. Test can fail for a real defect (no trivial asserts)
3. Description states exactly what the expect verifies
4. Compare to pre-computed expectations, not function output
5. Follow same lint/type/style rules as prod code
6. Express invariants (commutativity, idempotence) via property tests
7. Group tests: `describe(functionName, () => ...)`
8. Use `expect.any(...)` for variable IDs
9. Strong assertions: `toEqual(1)` not `toBeGreaterThanOrEqual(1)`
10. Test edge cases, realistic input, unexpected input, boundaries
11. Don't test conditions caught by type checker

---

## Specialized Context

When working in specific directories, refer to their CLAUDE.md:

- Engine development: [app/engine/CLAUDE.md](app/engine/CLAUDE.md)
- Router development: [app/router/CLAUDE.md](app/router/CLAUDE.md)
- BFF development: [app/bff/CLAUDE.md](app/bff/CLAUDE.md)
- UI development: [app/ui/CLAUDE.md](app/ui/CLAUDE.md)

For detailed architecture diagrams and system design, see [CONTEXT.md](CONTEXT.md).

These files provide detailed, context-specific guidance.
