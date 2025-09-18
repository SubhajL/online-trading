package models

import (
	"time"
)

// StreamResponse represents information about an active stream
type StreamResponse struct {
	ID            string          `json:"id"`
	Type          string          `json:"type"`
	Status        string          `json:"status"`
	CreatedAt     time.Time       `json:"created_at"`
	Subscriptions []string        `json:"subscriptions,omitempty"`
	Metrics       *StreamMetrics  `json:"metrics,omitempty"`
}

// StreamMetrics contains metrics for a stream connection
type StreamMetrics struct {
	MessagesReceived int64     `json:"messages_received"`
	MessagesSent     int64     `json:"messages_sent"`
	BytesReceived    int64     `json:"bytes_received"`
	BytesSent        int64     `json:"bytes_sent"`
	ConnectedSince   time.Time `json:"connected_since"`
	LastActivity     time.Time `json:"last_activity"`
}

// SubscriptionResponse represents the result of a subscription request
type SubscriptionResponse struct {
	Success      bool      `json:"success"`
	Symbol       string    `json:"symbol,omitempty"`
	Streams      []string  `json:"streams,omitempty"`
	SubscribedAt time.Time `json:"subscribed_at,omitempty"`
	Error        string    `json:"error,omitempty"`
}

// ErrorResponse represents an API error response
type ErrorResponse struct {
	Error     string `json:"error"`
	Message   string `json:"message"`
	RequestID string `json:"request_id,omitempty"`
	Timestamp int64  `json:"timestamp"`
}

// NewErrorResponse creates a new error response
func NewErrorResponse(errorCode, message, requestID string) *ErrorResponse {
	return &ErrorResponse{
		Error:     errorCode,
		Message:   message,
		RequestID: requestID,
		Timestamp: time.Now().Unix(),
	}
}

// HealthResponse represents the health status of the service
type HealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
	Uptime  int64  `json:"uptime"`
}

// HealthCheck represents a single health check result
type HealthCheck struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
	Error   string `json:"error,omitempty"`
}

// ReadinessResponse represents the readiness status of the service
type ReadinessResponse struct {
	Ready  bool                   `json:"ready"`
	Checks map[string]HealthCheck `json:"checks"`
}

// ConfigResponse represents the current configuration
type ConfigResponse struct {
	RateLimit      int       `json:"rate_limit"`
	MaxConnections int       `json:"max_connections"`
	UpdatedAt      time.Time `json:"updated_at"`
}

// ListResponse represents a paginated list response
type ListResponse struct {
	Data     interface{} `json:"data"`
	Count    int         `json:"count"`
	Total    int         `json:"total"`
	Page     int         `json:"page"`
	PageSize int         `json:"page_size"`
}

// NewListResponse creates a new paginated list response
func NewListResponse(data interface{}, count, total, page, pageSize int) *ListResponse {
	return &ListResponse{
		Data:     data,
		Count:    count,
		Total:    total,
		Page:     page,
		PageSize: pageSize,
	}
}