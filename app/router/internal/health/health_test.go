package health_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"

	"router/internal/health"
)

func TestBinanceConnectionHealthy(t *testing.T) {
	// Test successful Binance API connection
	checker := health.NewHealthChecker()
	client := health.GetTestBinanceClient()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	status := checker.CheckBinanceConnection(ctx, client)

	assert.Equal(t, health.StatusHealthy, status.Status)
	assert.Contains(t, status.Message, "Binance API is accessible")
	assert.Greater(t, status.LatencyMs, float64(0))
	assert.NotNil(t, status.LastCheck)
}

func TestBinanceConnectionWithRateLimit(t *testing.T) {
	if !health.IsCI() {
		t.Skip("Rate limit test only runs in CI with mocked client")
	}

	// Test Binance connection with rate limiting response
	checker := health.NewHealthChecker()

	// In CI, we can control the mock to simulate rate limiting
	client := &health.MockBinanceClient{
		PingFunc: func(ctx context.Context) error {
			return health.NewRateLimitError("rate limit exceeded")
		},
	}

	ctx := context.Background()
	status := checker.CheckBinanceConnection(ctx, client)

	assert.Equal(t, health.StatusDegraded, status.Status)
	assert.Contains(t, status.Message, "rate limit")
	assert.Greater(t, status.LatencyMs, float64(0))
}

func TestBinanceConnectionTimeout(t *testing.T) {
	// Test Binance connection timeout
	checker := health.NewHealthChecker()
	client := health.GetTestBinanceClient()

	// Use very short timeout to trigger timeout condition
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Millisecond)
	defer cancel()

	// Give context time to expire
	time.Sleep(2 * time.Millisecond)

	status := checker.CheckBinanceConnection(ctx, client)

	assert.Equal(t, health.StatusUnhealthy, status.Status)
	assert.Contains(t, status.Message, "timeout")
}

func TestRedisCacheLatency(t *testing.T) {
	// Test Redis cache performance check
	checker := health.NewHealthChecker()
	client := health.GetTestRedisClient()

	// Skip if Redis is not available
	ctx := context.Background()
	if err := client.Ping(ctx); err != nil {
		if os.Getenv("CI") != "true" {
			t.Skip("Redis not available")
		}
	}

	status := checker.CheckRedisCache(ctx, client)

	assert.Equal(t, health.StatusHealthy, status.Status)
	assert.Contains(t, status.Message, "Redis cache is responsive")
	assert.Greater(t, status.LatencyMs, float64(0))
	assert.Contains(t, status.Details, "memory_used_mb")
}

func TestRedisCacheHighLatency(t *testing.T) {
	if !health.IsCI() {
		t.Skip("High latency test requires mock control, only runs in CI")
	}

	// Test Redis with simulated high latency
	checker := health.NewHealthChecker()

	// In CI, use mock that simulates slow response
	client := &health.MockRedisClient{
		PingFunc: func(ctx context.Context) error {
			time.Sleep(100 * time.Millisecond)
			return nil
		},
		InfoFunc: func(ctx context.Context, section string) (string, error) {
			return "used_memory:104857600", nil
		},
	}

	ctx := context.Background()
	status := checker.CheckRedisCache(ctx, client)

	assert.Equal(t, health.StatusDegraded, status.Status)
	assert.Contains(t, status.Message, "high latency")
	assert.Greater(t, status.LatencyMs, float64(50))
}

func TestOrderProcessingPipeline(t *testing.T) {
	// Test order processing pipeline health
	checker := health.NewHealthChecker()

	// Simulate healthy pipeline
	ctx := context.Background()
	stats := health.OrderStats{
		TotalOrders:      1000,
		SuccessfulOrders: 995,
		FailedOrders:     5,
		AvgProcessingMs:  50,
	}

	status := checker.CheckOrderProcessing(ctx, stats)

	assert.Equal(t, health.StatusHealthy, status.Status)
	assert.Contains(t, status.Message, "Order processing pipeline operational")
	assert.Equal(t, float64(99.5), status.Details["success_rate"])
}

func TestOrderProcessingHighFailureRate(t *testing.T) {
	// Test order processing with high failure rate
	checker := health.NewHealthChecker()

	ctx := context.Background()
	stats := health.OrderStats{
		TotalOrders:      1000,
		SuccessfulOrders: 800,
		FailedOrders:     200,
		AvgProcessingMs:  100,
	}

	status := checker.CheckOrderProcessing(ctx, stats)

	assert.Equal(t, health.StatusUnhealthy, status.Status)
	assert.Contains(t, status.Message, "High order failure rate")
	assert.Equal(t, float64(80), status.Details["success_rate"])
}

func TestHealthAggregationWithFailures(t *testing.T) {
	// Test aggregating health status with partial failures
	checker := health.NewHealthChecker()

	binanceStatus := health.HealthStatus{
		Component: "binance",
		Status:    health.StatusHealthy,
		Message:   "OK",
	}

	redisStatus := health.HealthStatus{
		Component: "redis",
		Status:    health.StatusDegraded,
		Message:   "High latency",
	}

	orderStatus := health.HealthStatus{
		Component: "orders",
		Status:    health.StatusUnhealthy,
		Message:   "High failure rate",
	}

	report := checker.GetDetailedHealth([]health.HealthStatus{
		binanceStatus,
		redisStatus,
		orderStatus,
	})

	assert.Equal(t, health.StatusUnhealthy, report.OverallStatus)
	assert.Len(t, report.Components, 3)
	assert.Contains(t, report.Message, "System unhealthy")
	assert.NotNil(t, report.Timestamp)
}

func TestHealthEndpointHandler(t *testing.T) {
	// Test HTTP health endpoint
	checker := health.NewHealthChecker()
	handler := health.NewHealthHandler(checker)

	// Create test request
	req := httptest.NewRequest("GET", "/healthz", nil)
	w := httptest.NewRecorder()

	handler.HandleHealth(w, req)

	resp := w.Result()
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Verify response contains expected fields
	body := w.Body.String()
	assert.Contains(t, body, "status")
	assert.Contains(t, body, "healthy")
}

func TestDetailedHealthEndpoint(t *testing.T) {
	// Test detailed health status endpoint
	checker := health.NewHealthChecker()
	handler := health.NewHealthHandler(checker)

	// Create test request
	req := httptest.NewRequest("GET", "/health/status", nil)
	w := httptest.NewRecorder()

	handler.HandleDetailedStatus(w, req)

	resp := w.Result()
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	// Verify detailed response
	body := w.Body.String()
	assert.Contains(t, body, "overall_status")
	assert.Contains(t, body, "components")
	assert.Contains(t, body, "timestamp")
}