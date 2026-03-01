package health_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"

	"router/internal/health"
)

// Mock Binance client for testing
type mockBinanceClient struct {
	mock.Mock
}

func (m *mockBinanceClient) Ping(ctx context.Context) error {
	args := m.Called(ctx)
	return args.Error(0)
}

func (m *mockBinanceClient) GetExchangeInfo(ctx context.Context) (interface{}, error) {
	args := m.Called(ctx)
	return args.Get(0), args.Error(1)
}

// Mock Redis client for testing
type mockRedisClient struct {
	mock.Mock
}

func (m *mockRedisClient) Ping(ctx context.Context) error {
	args := m.Called(ctx)
	return args.Error(0)
}

func (m *mockRedisClient) Info(ctx context.Context, section string) (string, error) {
	args := m.Called(ctx, section)
	return args.String(0), args.Error(1)
}

func TestBinanceConnectionHealthy(t *testing.T) {
	// Test successful Binance API connection
	checker := health.NewHealthChecker()

	mockClient := new(mockBinanceClient)
	mockClient.On("Ping", mock.Anything).Return(nil)
	mockClient.On("GetExchangeInfo", mock.Anything).Return(map[string]interface{}{"symbols": []interface{}{}}, nil)

	ctx := context.Background()
	status := checker.CheckBinanceConnection(ctx, mockClient)

	assert.Equal(t, health.StatusHealthy, status.Status)
	assert.Contains(t, status.Message, "Binance API is accessible")
	assert.Greater(t, status.LatencyMs, float64(0))
	assert.NotNil(t, status.LastCheck)

	mockClient.AssertExpectations(t)
}

func TestBinanceConnectionWithRateLimit(t *testing.T) {
	// Test Binance connection with rate limiting response
	checker := health.NewHealthChecker()

	mockClient := new(mockBinanceClient)
	rateLimitErr := errors.New("rate limit exceeded")
	mockClient.On("Ping", mock.Anything).Return(rateLimitErr)

	ctx := context.Background()
	status := checker.CheckBinanceConnection(ctx, mockClient)

	assert.Equal(t, health.StatusDegraded, status.Status)
	assert.Contains(t, status.Message, "rate limit")
	assert.Greater(t, status.LatencyMs, float64(0))

	mockClient.AssertExpectations(t)
}

func TestBinanceConnectionTimeout(t *testing.T) {
	// Test Binance connection timeout
	checker := health.NewHealthChecker()

	mockClient := new(mockBinanceClient)

	// Simulate timeout by using a context with deadline
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Millisecond)
	defer cancel()

	// Delay the mock response to trigger timeout
	mockClient.On("Ping", mock.Anything).Return(context.DeadlineExceeded).Run(func(args mock.Arguments) {
		time.Sleep(10 * time.Millisecond)
	})

	status := checker.CheckBinanceConnection(ctx, mockClient)

	assert.Equal(t, health.StatusUnhealthy, status.Status)
	assert.Contains(t, status.Message, "timeout")
}

func TestRedisCacheLatency(t *testing.T) {
	// Test Redis cache performance check
	checker := health.NewHealthChecker()

	mockRedis := new(mockRedisClient)
	mockRedis.On("Ping", mock.Anything).Return(nil)
	mockRedis.On("Info", mock.Anything, "memory").Return("used_memory:104857600", nil)

	ctx := context.Background()
	status := checker.CheckRedisCache(ctx, mockRedis)

	assert.Equal(t, health.StatusHealthy, status.Status)
	assert.Contains(t, status.Message, "Redis cache is responsive")
	assert.Greater(t, status.LatencyMs, float64(0))
	assert.Contains(t, status.Details, "memory_used_mb")

	mockRedis.AssertExpectations(t)
}

func TestRedisCacheHighLatency(t *testing.T) {
	// Test Redis with high latency
	checker := health.NewHealthChecker()

	mockRedis := new(mockRedisClient)
	// Simulate slow response
	mockRedis.On("Ping", mock.Anything).Return(nil).Run(func(args mock.Arguments) {
		time.Sleep(100 * time.Millisecond)
	})
	mockRedis.On("Info", mock.Anything, "memory").Return("", nil)

	ctx := context.Background()
	status := checker.CheckRedisCache(ctx, mockRedis)

	assert.Equal(t, health.StatusDegraded, status.Status)
	assert.Contains(t, status.Message, "high latency")
	assert.Greater(t, status.LatencyMs, float64(50))

	mockRedis.AssertExpectations(t)
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
