package metrics

import (
	"time"

	"github.com/gin-gonic/gin"
)

// MetricsCollectorInterface defines methods needed by the middleware
type MetricsCollectorInterface interface {
	RecordHTTPRequest(method, path string, status int)
	RecordHTTPDuration(method, endpoint string, duration float64)
}

// MetricsMiddleware creates a Gin middleware that collects HTTP metrics
func MetricsMiddleware(collector MetricsCollectorInterface) gin.HandlerFunc {
	return gin.HandlerFunc(func(c *gin.Context) {
		start := time.Now()

		// Process request
		c.Next()

		// Record metrics after request is processed
		duration := time.Since(start)
		method := c.Request.Method
		path := c.Request.URL.Path
		status := c.Writer.Status()

		// Record counter metric
		collector.RecordHTTPRequest(method, path, status)

		// Record histogram metric (duration in seconds)
		collector.RecordHTTPDuration(method, path, duration.Seconds())
	})
}