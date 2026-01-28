package health

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Health status constants
const (
	StatusHealthy   = "healthy"
	StatusDegraded  = "degraded"
	StatusUnhealthy = "unhealthy"
)

// HealthStatus represents the health of a single component
type HealthStatus struct {
	Component string                 `json:"component"`
	Status    string                 `json:"status"`
	Message   string                 `json:"message"`
	LatencyMs float64                `json:"latency_ms"`
	Details   map[string]interface{} `json:"details,omitempty"`
	LastCheck time.Time              `json:"last_check"`
}

// HealthReport represents the overall system health
type HealthReport struct {
	OverallStatus string                  `json:"overall_status"`
	Message       string                  `json:"message"`
	Timestamp     time.Time               `json:"timestamp"`
	Components    map[string]HealthStatus `json:"components"`
}

// OrderStats tracks order processing statistics
type OrderStats struct {
	TotalOrders      int64   `json:"total_orders"`
	SuccessfulOrders int64   `json:"successful_orders"`
	FailedOrders     int64   `json:"failed_orders"`
	AvgProcessingMs  float64 `json:"avg_processing_ms"`
}

// BinanceClient interface for health checks
type BinanceClient interface {
	Ping(ctx context.Context) error
	GetExchangeInfo(ctx context.Context) (interface{}, error)
}

// RedisClient interface for health checks
type RedisClient interface {
	Ping(ctx context.Context) error
	Info(ctx context.Context, section string) (string, error)
}

// HealthChecker performs health checks on system components
type HealthChecker struct {
	mu              sync.RWMutex
	componentStatus map[string]HealthStatus
	orderStats      OrderStats
}

// NewHealthChecker creates a new health checker instance
func NewHealthChecker() *HealthChecker {
	return &HealthChecker{
		componentStatus: make(map[string]HealthStatus),
	}
}

// CheckBinanceConnection checks Binance API connectivity
func (h *HealthChecker) CheckBinanceConnection(ctx context.Context, client BinanceClient) HealthStatus {
	start := time.Now()
	status := HealthStatus{
		Component: "binance",
		LastCheck: time.Now(),
		Details:   make(map[string]interface{}),
	}

	// Check if context is already cancelled
	select {
	case <-ctx.Done():
		status.Status = StatusUnhealthy
		status.Message = "Health check timeout"
		status.LatencyMs = time.Since(start).Seconds() * 1000
		return status
	default:
	}

	// Ping Binance API
	err := client.Ping(ctx)
	latency := time.Since(start)
	status.LatencyMs = latency.Seconds() * 1000

	if err != nil {
		if strings.Contains(err.Error(), "rate limit") {
			status.Status = StatusDegraded
			status.Message = "Binance API rate limited"
			status.Details["error"] = err.Error()
		} else if strings.Contains(err.Error(), "context deadline exceeded") {
			status.Status = StatusUnhealthy
			status.Message = "Binance API connection timeout"
		} else {
			status.Status = StatusUnhealthy
			status.Message = fmt.Sprintf("Binance API error: %v", err)
		}
	} else {
		status.Status = StatusHealthy
		status.Message = "Binance API is accessible"

		// Try to get exchange info for additional details only if context is still valid
		select {
		case <-ctx.Done():
			// Context cancelled, skip extra check
		default:
			if info, err := client.GetExchangeInfo(ctx); err == nil && info != nil {
				status.Details["exchange_info"] = "available"
			}
		}
	}

	// Store status
	h.mu.Lock()
	h.componentStatus["binance"] = status
	h.mu.Unlock()

	return status
}

// CheckRedisCache checks Redis cache health and performance
func (h *HealthChecker) CheckRedisCache(ctx context.Context, client RedisClient) HealthStatus {
	start := time.Now()
	status := HealthStatus{
		Component: "redis",
		LastCheck: time.Now(),
		Details:   make(map[string]interface{}),
	}

	// Ping Redis
	err := client.Ping(ctx)
	latency := time.Since(start)
	status.LatencyMs = latency.Seconds() * 1000

	if err != nil {
		status.Status = StatusUnhealthy
		status.Message = fmt.Sprintf("Redis error: %v", err)
	} else {
		// Check latency
		if status.LatencyMs > 50 {
			status.Status = StatusDegraded
			status.Message = fmt.Sprintf("Redis cache responsive but high latency: %.2fms", status.LatencyMs)
		} else {
			status.Status = StatusHealthy
			status.Message = "Redis cache is responsive"
		}

		// Get memory info
		if info, err := client.Info(ctx, "memory"); err == nil {
			// Parse memory info
			lines := strings.Split(info, "\n")
			for _, line := range lines {
				if strings.HasPrefix(line, "used_memory:") {
					parts := strings.Split(line, ":")
					if len(parts) == 2 {
						if memBytes, err := strconv.ParseInt(strings.TrimSpace(parts[1]), 10, 64); err == nil {
							status.Details["memory_used_mb"] = float64(memBytes) / (1024 * 1024)
						}
					}
				}
			}
		}
	}

	// Store status
	h.mu.Lock()
	h.componentStatus["redis"] = status
	h.mu.Unlock()

	return status
}

// CheckOrderProcessing checks order processing pipeline health
func (h *HealthChecker) CheckOrderProcessing(ctx context.Context, stats OrderStats) HealthStatus {
	start := time.Now()
	status := HealthStatus{
		Component: "orders",
		LastCheck: time.Now(),
		Details:   make(map[string]interface{}),
		LatencyMs: time.Since(start).Seconds() * 1000,
	}

	// Calculate success rate
	var successRate float64
	if stats.TotalOrders > 0 {
		successRate = float64(stats.SuccessfulOrders) / float64(stats.TotalOrders) * 100
	}

	status.Details["total_orders"] = stats.TotalOrders
	status.Details["successful_orders"] = stats.SuccessfulOrders
	status.Details["failed_orders"] = stats.FailedOrders
	status.Details["success_rate"] = successRate
	status.Details["avg_processing_ms"] = stats.AvgProcessingMs

	// Determine health based on success rate and processing time
	if successRate < 90 {
		status.Status = StatusUnhealthy
		status.Message = fmt.Sprintf("High order failure rate: %.1f%% success", successRate)
	} else if successRate < 95 || stats.AvgProcessingMs > 200 {
		status.Status = StatusDegraded
		status.Message = fmt.Sprintf("Order processing degraded: %.1f%% success, %.1fms avg", successRate, stats.AvgProcessingMs)
	} else {
		status.Status = StatusHealthy
		status.Message = "Order processing pipeline operational"
	}

	// Store status
	h.mu.Lock()
	h.componentStatus["orders"] = status
	h.orderStats = stats
	h.mu.Unlock()

	return status
}

// UpdateOrderStats updates the order processing statistics
func (h *HealthChecker) UpdateOrderStats(stats OrderStats) {
	h.mu.Lock()
	h.orderStats = stats
	h.mu.Unlock()
}

// GetDetailedHealth aggregates all component health statuses
func (h *HealthChecker) GetDetailedHealth(statuses []HealthStatus) HealthReport {
	report := HealthReport{
		Timestamp:  time.Now(),
		Components: make(map[string]HealthStatus),
	}

	// Aggregate statuses
	hasUnhealthy := false
	hasDegraded := false

	for _, status := range statuses {
		report.Components[status.Component] = status

		switch status.Status {
		case StatusUnhealthy:
			hasUnhealthy = true
		case StatusDegraded:
			hasDegraded = true
		}
	}

	// Determine overall status
	if hasUnhealthy {
		report.OverallStatus = StatusUnhealthy
		report.Message = "System unhealthy - one or more critical components failed"
	} else if hasDegraded {
		report.OverallStatus = StatusDegraded
		report.Message = "System degraded but operational"
	} else {
		report.OverallStatus = StatusHealthy
		report.Message = "All systems operational"
	}

	return report
}

// GetComponentStatuses returns current status of all components
func (h *HealthChecker) GetComponentStatuses() []HealthStatus {
	h.mu.RLock()
	defer h.mu.RUnlock()

	statuses := make([]HealthStatus, 0, len(h.componentStatus))
	for _, status := range h.componentStatus {
		statuses = append(statuses, status)
	}

	return statuses
}

// HealthHandler handles HTTP health check endpoints
type HealthHandler struct {
	checker *HealthChecker
}

// NewHealthHandler creates a new health handler
func NewHealthHandler(checker *HealthChecker) *HealthHandler {
	return &HealthHandler{checker: checker}
}

// HandleHealth handles basic health check endpoint
func (h *HealthHandler) HandleHealth(w http.ResponseWriter, r *http.Request) {
	// Basic health check - just return OK if service is up
	response := map[string]string{
		"status": "healthy",
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(response); err != nil {
		return
	}
}

// HandleDetailedStatus handles detailed health status endpoint
func (h *HealthHandler) HandleDetailedStatus(w http.ResponseWriter, r *http.Request) {
	statuses := h.checker.GetComponentStatuses()
	report := h.checker.GetDetailedHealth(statuses)

	statusCode := http.StatusOK
	if report.OverallStatus == StatusUnhealthy {
		statusCode = http.StatusServiceUnavailable
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)
	if err := json.NewEncoder(w).Encode(report); err != nil {
		return
	}
}
