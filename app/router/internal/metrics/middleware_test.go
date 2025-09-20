package metrics

import (
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// MockCollector implements MetricsCollectorInterface for testing
type MockCollector struct {
	HTTPRequests  map[string]int
	HTTPDurations map[string][]float64
}

func NewMockCollector() *MockCollector {
	return &MockCollector{
		HTTPRequests:  make(map[string]int),
		HTTPDurations: make(map[string][]float64),
	}
}

func (m *MockCollector) RecordHTTPRequest(method, path string, status int) {
	key := method + ":" + path + ":" + strconv.Itoa(status)
	m.HTTPRequests[key]++
}

func (m *MockCollector) RecordHTTPDuration(method, endpoint string, duration float64) {
	key := method + ":" + endpoint
	m.HTTPDurations[key] = append(m.HTTPDurations[key], duration)
}

func TestMetricsMiddleware_RecordsHTTPMetrics(t *testing.T) {
	collector := NewMockCollector()

	// Setup Gin
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(MetricsMiddleware(collector))

	// Add test route
	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// Make request
	req, _ := http.NewRequest("GET", "/test", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, req)

	// Verify response
	assert.Equal(t, http.StatusOK, recorder.Code)

	// Verify metrics were recorded
	assert.Equal(t, 1, collector.HTTPRequests["GET:/test:200"])
	assert.Len(t, collector.HTTPDurations["GET:/test"], 1)
	assert.True(t, collector.HTTPDurations["GET:/test"][0] > 0)
}

func TestMetricsMiddleware_RecordsErrorStatus(t *testing.T) {
	collector := NewMockCollector()

	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(MetricsMiddleware(collector))

	// Add test route that returns error
	router.GET("/error", func(c *gin.Context) {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "test error"})
	})

	// Make request
	req, _ := http.NewRequest("GET", "/error", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, req)

	// Verify response
	assert.Equal(t, http.StatusInternalServerError, recorder.Code)

	// Verify metrics were recorded with correct status
	assert.Equal(t, 1, collector.HTTPRequests["GET:/error:500"])
}

func TestMetricsMiddleware_RecordsMultipleRequests(t *testing.T) {
	collector := NewMockCollector()

	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(MetricsMiddleware(collector))

	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// Make multiple requests
	for i := 0; i < 5; i++ {
		req, _ := http.NewRequest("GET", "/test", nil)
		recorder := httptest.NewRecorder()
		router.ServeHTTP(recorder, req)
		require.Equal(t, http.StatusOK, recorder.Code)
	}

	// Verify metrics
	assert.Equal(t, 5, collector.HTTPRequests["GET:/test:200"])
	assert.Len(t, collector.HTTPDurations["GET:/test"], 5)
}

func TestMetricsMiddleware_RecordsDifferentMethods(t *testing.T) {
	collector := NewMockCollector()

	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(MetricsMiddleware(collector))

	router.GET("/test", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"method": "GET"})
	})
	router.POST("/test", func(c *gin.Context) {
		c.JSON(http.StatusCreated, gin.H{"method": "POST"})
	})

	// Make GET request
	req1, _ := http.NewRequest("GET", "/test", nil)
	recorder1 := httptest.NewRecorder()
	router.ServeHTTP(recorder1, req1)

	// Make POST request
	req2, _ := http.NewRequest("POST", "/test", nil)
	recorder2 := httptest.NewRecorder()
	router.ServeHTTP(recorder2, req2)

	// Verify metrics
	assert.Equal(t, 1, collector.HTTPRequests["GET:/test:200"])
	assert.Equal(t, 1, collector.HTTPRequests["POST:/test:201"])
	assert.Len(t, collector.HTTPDurations["GET:/test"], 1)
	assert.Len(t, collector.HTTPDurations["POST:/test"], 1)
}

func TestMetricsMiddleware_MeasuresDuration(t *testing.T) {
	collector := NewMockCollector()

	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(MetricsMiddleware(collector))

	// Add route with artificial delay
	router.GET("/slow", func(c *gin.Context) {
		time.Sleep(10 * time.Millisecond)
		c.JSON(http.StatusOK, gin.H{"status": "slow"})
	})

	// Make request
	req, _ := http.NewRequest("GET", "/slow", nil)
	recorder := httptest.NewRecorder()
	router.ServeHTTP(recorder, req)

	// Verify duration was measured (should be at least 10ms)
	durations := collector.HTTPDurations["GET:/slow"]
	require.Len(t, durations, 1)
	assert.True(t, durations[0] >= 0.01, "Expected duration >= 0.01s, got %f", durations[0])
}
