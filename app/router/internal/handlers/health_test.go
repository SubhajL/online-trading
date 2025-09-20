package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/models"
)

func TestHealthCheckHandler(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns 200 with health status", func(t *testing.T) {
		router := gin.New()
		startTime := time.Now().Add(-5 * time.Second) // Start time 5 seconds ago
		h := NewHealthHandlers("1.0.0", startTime)
		router.GET("/health", h.HealthCheck())

		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.HealthResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)

		assert.Equal(t, "healthy", resp.Status)
		assert.Equal(t, "1.0.0", resp.Version)
		assert.GreaterOrEqual(t, resp.Uptime, int64(5))
	})

	t.Run("includes correct uptime", func(t *testing.T) {
		startTime := time.Now().Add(-1 * time.Hour)
		router := gin.New()
		h := NewHealthHandlers("1.0.0", startTime)
		router.GET("/health", h.HealthCheck())

		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		var resp models.HealthResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)

		// Uptime should be approximately 1 hour (3600 seconds)
		assert.GreaterOrEqual(t, resp.Uptime, int64(3599))
		assert.LessOrEqual(t, resp.Uptime, int64(3601))
	})
}

func TestReadinessHandler(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns 200 when all checks pass", func(t *testing.T) {
		router := gin.New()

		checker := &mockReadinessChecker{
			checks: map[string]models.HealthCheck{
				"websocket": {Status: "healthy", Message: "Connected"},
				"database":  {Status: "healthy", Message: "Active"},
			},
			ready: true,
		}

		h := NewHealthHandlers("1.0.0", time.Now())
		router.GET("/ready", h.Readiness(checker))

		req := httptest.NewRequest("GET", "/ready", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.ReadinessResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)

		assert.True(t, resp.Ready)
		assert.Len(t, resp.Checks, 2)
		assert.Equal(t, "healthy", resp.Checks["websocket"].Status)
	})

	t.Run("returns 503 when not ready", func(t *testing.T) {
		router := gin.New()

		checker := &mockReadinessChecker{
			checks: map[string]models.HealthCheck{
				"websocket": {Status: "unhealthy", Message: "Connection failed", Error: "timeout"},
				"database":  {Status: "healthy", Message: "Active"},
			},
			ready: false,
		}

		h := NewHealthHandlers("1.0.0", time.Now())
		router.GET("/ready", h.Readiness(checker))

		req := httptest.NewRequest("GET", "/ready", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusServiceUnavailable, w.Code)

		var resp models.ReadinessResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)

		assert.False(t, resp.Ready)
		assert.Equal(t, "unhealthy", resp.Checks["websocket"].Status)
		assert.Equal(t, "timeout", resp.Checks["websocket"].Error)
	})

	t.Run("handles checker errors gracefully", func(t *testing.T) {
		router := gin.New()

		checker := &mockReadinessChecker{
			err: assert.AnError,
		}

		h := NewHealthHandlers("1.0.0", time.Now())
		router.GET("/ready", h.Readiness(checker))

		req := httptest.NewRequest("GET", "/ready", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusServiceUnavailable, w.Code)

		var resp models.ReadinessResponse
		err := json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)

		assert.False(t, resp.Ready)
	})
}

func TestMetricsHandler(t *testing.T) {
	gin.SetMode(gin.TestMode)

	t.Run("returns Prometheus metrics", func(t *testing.T) {
		router := gin.New()

		collector := &mockMetricsCollector{
			metrics: `# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health"} 100
`,
		}

		h := NewHealthHandlers("1.0.0", time.Now())
		router.GET("/metrics", h.Metrics(collector))

		req := httptest.NewRequest("GET", "/metrics", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)
		assert.Equal(t, "text/plain; charset=utf-8", w.Header().Get("Content-Type"))
		assert.Contains(t, w.Body.String(), "http_requests_total")
		assert.Contains(t, w.Body.String(), "counter")
	})

	t.Run("handles collector errors", func(t *testing.T) {
		router := gin.New()

		collector := &mockMetricsCollector{
			err: assert.AnError,
		}

		h := NewHealthHandlers("1.0.0", time.Now())
		router.GET("/metrics", h.Metrics(collector))

		req := httptest.NewRequest("GET", "/metrics", nil)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusInternalServerError, w.Code)
	})
}

// Mock implementations for testing
type mockReadinessChecker struct {
	checks map[string]models.HealthCheck
	ready  bool
	err    error
}

func (m *mockReadinessChecker) Check() (map[string]models.HealthCheck, bool, error) {
	if m.err != nil {
		return nil, false, m.err
	}
	return m.checks, m.ready, nil
}

type mockMetricsCollector struct {
	metrics string
	err     error
}

func (m *mockMetricsCollector) Collect() (string, error) {
	if m.err != nil {
		return "", m.err
	}
	return m.metrics, nil
}
