# Performance Testing with Locust

This directory contains load testing scenarios for the trading platform using Locust.

## Installation

```bash
pip install locust
# or
pip install -r app/engine/requirements-dev.txt
```

## Quick Start

### 1. Run with Web UI

```bash
# Start Locust web interface
locust -f locustfile.py --host http://localhost:8001

# Open browser to http://localhost:8089
```

### 2. Run Headless with Script

```bash
# List available scenarios
python run_load_tests.py --list-scenarios

# Run a specific scenario
python run_load_tests.py --scenario normal-load

# Run with HTML report generation
python run_load_tests.py --scenario stress-candles --report

# Check if services are running
python run_load_tests.py --check-only
```

### 3. Run Specific Scenarios Directly

```bash
# Normal trading load (50 users)
locust --config locust_scenarios.conf --scenario-normal-load

# Peak load simulation (200 users)
locust --config locust_scenarios.conf --scenario-peak-load

# Stress test candle ingestion
locust --config locust_scenarios.conf --scenario-stress-candles

# Database performance test
locust --config locust_scenarios.conf --scenario-stress-database
```

## Available Test Scenarios

### Regular Load Tests (`locustfile.py`)

1. **Normal Load** - Simulates typical trading day with 50 concurrent users
   - Mixed trading operations
   - Health checks and monitoring
   - Expected: 100+ RPS, <500ms P95

2. **Peak Load** - Market open/close simulation with 200 users
   - High frequency trading patterns
   - Concurrent signal generation
   - Expected: 400+ RPS, <1000ms P95

3. **HFT Simulation** - High-frequency trading bots
   - Rapid market data queries
   - Minimal wait times
   - Expected: 500+ RPS, <50ms P95

### Stress Tests (`locust_engine_stress.py`)

1. **Candle Ingestion Stress** - Tests candle processing pipeline
   - Bulk candle uploads
   - Concurrent queries
   - Expected: 500+ candles/sec

2. **Decision Engine Stress** - Tests risk management under load
   - Concurrent decision requests
   - Risk limit enforcement
   - Expected: <100ms decision latency

3. **Database Stress** - TimescaleDB performance
   - Time-series queries
   - Complex aggregations
   - Expected: <300ms P95 for queries

4. **Burst Load** - Sudden traffic spikes
   - 300 user burst
   - Tests rate limiting
   - Expected: System stability

## Performance Targets

Based on system design, these are the performance targets:

| Component | Target Latency | Notes |
|-----------|---------------|-------|
| Candle → Signal | ≤500ms P95 | End-to-end from candle close |
| Decision → Order | ≤300ms P95 | Risk check to order placement |
| Health Check | ≤100ms | All components |
| WebSocket Message | ≤50ms | Market data delivery |

## Running Tests in CI/CD

```bash
# Run performance regression test
./run_load_tests.py --scenario normal-load

# Check exit code
if [ $? -eq 0 ]; then
    echo "Performance test passed"
else
    echo "Performance regression detected"
    exit 1
fi
```

## Analyzing Results

Results are saved in `reports/<scenario>_<timestamp>/`:

- `stats_stats.csv` - Detailed statistics per endpoint
- `stats_history.csv` - Time-series data
- `summary.json` - Pass/fail analysis
- `report.html` - Visual report (if --report flag used)

### Key Metrics to Monitor

1. **Requests per Second (RPS)** - Throughput
2. **Response Time Percentiles** - P50, P90, P95, P99
3. **Failure Rate** - Should be <1%
4. **Resource Usage** - CPU, Memory, DB connections

## Custom Scenarios

Create custom test scenarios by editing `locust_scenarios.conf`:

```ini
[scenario-custom]
users = 100
spawn-rate = 10
run-time = 5m
locustfile = locustfile.py
tags = custom-tags
```

## Troubleshooting

### Services Not Running

```bash
# Check if engine is running
curl http://localhost:8001/health/

# Check component health
curl http://localhost:8001/health/status
```

### High Failure Rate

- Check engine logs for errors
- Verify database connections
- Monitor system resources

### Slow Response Times

- Check database query performance
- Review concurrent connection limits
- Profile slow endpoints

## Best Practices

1. **Warm Up** - Run a small load before main test
2. **Monitor Resources** - Watch CPU, memory, DB during tests
3. **Incremental Load** - Start small, increase gradually
4. **Baseline Tests** - Establish performance baseline
5. **Regular Testing** - Run after significant changes

## Integration with Monitoring

During load tests, monitor:

- Prometheus metrics at http://localhost:8001/metrics/
- Grafana dashboards (if configured)
- Application logs for errors
- Database performance metrics