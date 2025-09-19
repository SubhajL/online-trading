package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"router/internal/models"
)

// ReadinessChecker interface for checking service readiness
type ReadinessChecker interface {
	Check() (map[string]models.HealthCheck, bool, error)
}

// MetricsCollector interface for collecting Prometheus metrics
type MetricsCollector interface {
	Collect() (string, error)
}

// HealthHandlers contains health check handlers
type HealthHandlers struct {
	version   string
	startTime time.Time
}

// NewHealthHandlers creates new health handlers
func NewHealthHandlers(version string, startTime time.Time) *HealthHandlers {
	return &HealthHandlers{
		version:   version,
		startTime: startTime,
	}
}

// HealthCheck returns a handler for health check endpoint
func (h *HealthHandlers) HealthCheck() gin.HandlerFunc {
	return func(c *gin.Context) {
		uptime := time.Since(h.startTime).Seconds()

		response := models.HealthResponse{
			Status:  "healthy",
			Version: h.version,
			Uptime:  int64(uptime),
		}

		c.JSON(http.StatusOK, response)
	}
}

// Readiness returns a handler for readiness check endpoint
func (h *HealthHandlers) Readiness(checker ReadinessChecker) gin.HandlerFunc {
	return func(c *gin.Context) {
		checks, ready, err := checker.Check()

		if err != nil {
			response := models.ReadinessResponse{
				Ready: false,
				Checks: map[string]models.HealthCheck{
					"error": {
						Status:  "unhealthy",
						Message: "Failed to check readiness",
						Error:   err.Error(),
					},
				},
			}
			c.JSON(http.StatusServiceUnavailable, response)
			return
		}

		response := models.ReadinessResponse{
			Ready:  ready,
			Checks: checks,
		}

		status := http.StatusOK
		if !ready {
			status = http.StatusServiceUnavailable
		}

		c.JSON(status, response)
	}
}

// Metrics returns a handler for Prometheus metrics endpoint
func (h *HealthHandlers) Metrics(collector MetricsCollector) gin.HandlerFunc {
	return func(c *gin.Context) {
		metrics, err := collector.Collect()
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
				"METRICS_ERROR",
				"Failed to collect metrics",
				c.GetString("request_id"),
			))
			return
		}

		c.Data(http.StatusOK, "text/plain; charset=utf-8", []byte(metrics))
	}
}
