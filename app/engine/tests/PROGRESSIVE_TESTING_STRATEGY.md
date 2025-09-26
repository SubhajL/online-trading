# Progressive Testing Strategy

## Overview

The progressive testing strategy implements a 5-level testing hierarchy that ensures code quality while minimizing test execution time and resource usage. Tests are organized from fastest/simplest (Level 0) to slowest/most complex (Level 4).

## Test Levels

### Level 0: Import Tests (No Dependencies)
- **Purpose**: Verify no syntax errors or circular imports
- **Characteristics**:
  - No external dependencies
  - No mocking required
  - Instant execution (<1s)
- **Examples**:
  - `test_imports.py` - Verify all modules can be imported
  - Type definition validation
  - Module structure tests

### Level 1: Unit Tests (Mocked Dependencies)
- **Purpose**: Test individual functions and classes in isolation
- **Characteristics**:
  - All external dependencies mocked
  - Fast execution (1-5s)
  - High coverage of business logic
- **Examples**:
  - Algorithm tests (SMC math, indicators)
  - Data transformation tests
  - Pure function tests

### Level 2: Service Tests (Real DB/Redis)
- **Purpose**: Test service layer with real infrastructure
- **Characteristics**:
  - Uses real database connections
  - Uses real Redis connections
  - Tests transaction boundaries
  - Medium execution time (5-30s)
- **Examples**:
  - Database repository tests
  - Cache integration tests
  - Service boundary tests

### Level 3: Integration Tests (All Services)
- **Purpose**: Test complete system flows
- **Characteristics**:
  - Multiple services running
  - Full event flow testing
  - Real WebSocket connections
  - Slower execution (30s-2m)
- **Examples**:
  - End-to-end signal generation
  - Multi-symbol processing
  - Complete trading pipeline

### Level 4: End-to-End Tests (With UI)
- **Purpose**: Test complete user workflows
- **Characteristics**:
  - Browser automation
  - Full stack testing
  - API and UI verification
  - Slowest execution (2-10m)
- **Examples**:
  - Chart visualization tests
  - Alert notification tests
  - Complete user journeys

## Usage

### Command Line Interface

```bash
# Run all test levels (default)
python -m app.engine.tests.test_runner

# Run specific level
python -m app.engine.tests.test_runner --level 1

# Run range of levels
python -m app.engine.tests.test_runner --start 0 --end 2

# Continue on failure
python -m app.engine.tests.test_runner --no-stop-on-failure

# Run with coverage
python -m app.engine.tests.test_runner --coverage

# Run in parallel (for levels with multiple test files)
python -m app.engine.tests.test_runner --parallel

# Show test distribution
python -m app.engine.tests.test_runner --show-distribution
```

### In CI/CD Pipeline

```yaml
# GitHub Actions example
test:
  strategy:
    matrix:
      level: [0, 1, 2, 3, 4]
  steps:
    - name: Run Level ${{ matrix.level }} Tests
      run: |
        python -m app.engine.tests.test_runner \
          --level ${{ matrix.level }} \
          --coverage
```

### Pre-flight Checks

Before running any tests, the system performs pre-flight checks:

```bash
# Run pre-flight checks
python -m app.engine.preflight.run_checks

# Example output:
============================================================
PREFLIGHT CHECK RESULTS
============================================================

Overall Status: ✅ PASSED
Total Time: 2.45s

✅ All preflight checks passed! Ready to start services.
```

## Test Organization

### Directory Structure

```
app/engine/tests/
├── unit/                # Level 1 tests
│   ├── test_indicators.py
│   ├── test_smc_math.py
│   └── test_decision_logic.py
├── integration/         # Level 3 tests
│   ├── test_event_flow.py
│   ├── test_multi_symbol.py
│   └── test_websocket_recovery.py
├── e2e/                # Level 4 tests
│   └── test_trading_workflow.py
├── test_imports.py     # Level 0 test
└── test_runner.py      # Progressive test runner
```

### Test Categorization

Tests are automatically categorized based on:

1. **Directory location** (unit/, integration/, e2e/)
2. **Import patterns** (mocking libraries, external dependencies)
3. **File naming** (test_imports.py → Level 0)
4. **Code analysis** (WebSocket usage → Level 3+)

## Best Practices

### Writing Tests

1. **Keep tests at the lowest appropriate level**
   - If a test can be written with mocks, make it Level 1
   - Only use real infrastructure when testing infrastructure

2. **Use descriptive test names**
   ```python
   def test_smc_detects_bullish_choch_after_three_higher_lows():
       """Verify CHOCH detection with specific market structure."""
   ```

3. **Minimize test dependencies**
   - Each test should set up its own data
   - Use fixtures for common setup
   - Clean up after tests

### Test Data

1. **Level 0-1**: Use hardcoded test data
2. **Level 2**: Use test database with migrations
3. **Level 3-4**: Use Docker containers for services

### Performance

1. **Parallelize when possible**
   - Level 0-1 tests can run in parallel
   - Use pytest-xdist for parallel execution

2. **Cache expensive operations**
   - Docker images
   - Database schemas
   - Test fixtures

## Integration with Development Workflow

### Local Development

```bash
# Quick feedback during development
make test-unit  # Runs levels 0-1

# Before pushing
make test-integration  # Runs levels 0-3

# Full validation
make test-all  # Runs all levels
```

### Pull Request Checks

- Level 0-1: Required to pass
- Level 2-3: Required for service changes
- Level 4: Run nightly or on merge to main

### Monitoring Test Health

```bash
# Generate test report
python -m app.engine.tests.test_runner --show-distribution

# Example output:
Test Level Distribution
==================================================

Level 0: Import tests (no dependencies)
  Count: 1
  Examples:
    - app/engine/tests/test_imports.py

Level 1: Unit tests (mocked dependencies)
  Count: 45
  Showing first 3 of 45:
    - app/engine/tests/unit/test_indicators.py
    - app/engine/tests/unit/test_smc_algorithms.py
    - app/engine/tests/unit/test_decision_logic.py
    ...

Level 2: Service tests (real DB/Redis)
  Count: 8

Level 3: Integration tests (all services)
  Count: 12

Level 4: End-to-end tests (with UI)
  Count: 3

Total tests: 69
```

## Troubleshooting

### Common Issues

1. **Level 2 tests failing**: Check database/Redis connection
   ```bash
   make db-up  # Ensure infrastructure is running
   ```

2. **Level 3 tests timeout**: Increase timeout or check service health
   ```python
   config = RunConfig(pytest_args=["--timeout=300"])
   ```

3. **Level 4 tests flaky**: Add waits for UI elements
   ```python
   # Use explicit waits in Selenium/Playwright
   WebDriverWait(driver, 10).until(
       EC.presence_of_element_located((By.ID, "chart"))
   )
   ```

### Debug Mode

```bash
# Run with verbose output
python -m app.engine.tests.test_runner --level 2 --verbose

# Run single test file
pytest app/engine/tests/unit/test_smc_algorithms.py -v

# Run with debugger
pytest --pdb app/engine/tests/unit/test_failing.py
```

## Future Enhancements

1. **Automatic test level detection**
   - Analyze AST to determine optimal level
   - Suggest moving tests to lower levels

2. **Test impact analysis**
   - Run only tests affected by code changes
   - Integration with git diff

3. **Performance tracking**
   - Track test execution times
   - Alert on performance regressions

4. **Flaky test detection**
   - Automatically retry flaky tests
   - Report flakiness metrics