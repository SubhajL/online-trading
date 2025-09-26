# Router Health Check System

This package implements comprehensive health checks for the router service.

## Components Monitored

1. **Binance API Connection**
   - Checks API connectivity via Ping
   - Detects rate limiting (returns DEGRADED status)
   - Monitors connection latency
   - Optionally fetches exchange info

2. **Redis Cache**
   - Checks cache responsiveness
   - Monitors latency (>50ms triggers DEGRADED status)
   - Reports memory usage metrics

3. **Order Processing Pipeline**
   - Tracks order success/failure rates
   - Monitors average processing time
   - Triggers UNHEALTHY if success rate < 90%
   - Triggers DEGRADED if success rate < 95% or avg time > 200ms

## Health Status Levels

- **HEALTHY**: All components functioning normally
- **DEGRADED**: Components experiencing performance issues but still operational
- **UNHEALTHY**: Critical failures requiring intervention

## HTTP Endpoints

### Basic Health Check
```
GET /healthz
```
Returns simple health status for Kubernetes liveness probes.

### Detailed Health Status
```
GET /health/status
```
Returns comprehensive health report with component-level details:
- Overall system status
- Individual component health
- Performance metrics
- Timestamps

## Usage

```go
// Create health checker
checker := health.NewHealthChecker()

// Perform health checks
binanceStatus := checker.CheckBinanceConnection(ctx, binanceClient)
redisStatus := checker.CheckRedisCache(ctx, redisClient)

// Update order statistics
checker.UpdateOrderStats(stats)

// Get aggregated health report
statuses := checker.GetComponentStatuses()
report := checker.GetDetailedHealth(statuses)
```

## Integration with Router

The health check system integrates with the router's HTTP server to provide real-time monitoring capabilities. Health endpoints are automatically registered when the router starts.