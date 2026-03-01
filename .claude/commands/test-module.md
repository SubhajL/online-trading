Run comprehensive tests for a specific module: $ARGUMENTS

## Test Execution

### Python Engine Module
If testing an engine module (e.g., `smc`, `decision`, `features`):

```bash
# Unit tests
pytest app/engine/tests/unit/test_$ARGUMENTS.py -v --tb=short

# With coverage
pytest app/engine/tests/unit/test_$ARGUMENTS.py -v --cov=app/engine/$ARGUMENTS --cov-report=term-missing

# Integration tests (if exist)
pytest app/engine/tests/integration/ -k "$ARGUMENTS" -v -m integration
```

### Go Router Module
If testing a router module (e.g., `orders`, `binance`, `filters`):

```bash
# Unit tests
go test -v ./internal/$ARGUMENTS/...

# With race detection
go test -v -race ./internal/$ARGUMENTS/...

# With coverage
go test -cover -coverprofile=coverage.out ./internal/$ARGUMENTS/...
```

### TypeScript Module
If testing a BFF or UI module:

```bash
# BFF tests
pnpm --filter @repo/bff test -- --testPathPattern="$ARGUMENTS"

# UI tests
pnpm --filter @repo/ui test -- $ARGUMENTS
```

## Post-Test Analysis

1. Review any failures - identify root cause
2. Check coverage - aim for >80%
3. Identify missing edge cases
4. Suggest additional tests if needed

## Quality Checks

After tests pass, also run:
- Linting: `make lint`
- Type checking: `make typecheck`
