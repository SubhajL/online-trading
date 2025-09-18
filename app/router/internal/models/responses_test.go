package models

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestStreamResponse(t *testing.T) {
	t.Run("marshals to JSON correctly", func(t *testing.T) {
		now := time.Now()
		resp := StreamResponse{
			ID:            "stream-123",
			Type:          "public",
			Status:        "connected",
			CreatedAt:     now,
			Subscriptions: []string{"btcusdt@depth", "ethusdt@ticker"},
			Metrics: &StreamMetrics{
				MessagesReceived: 1000,
				MessagesSent:     50,
				BytesReceived:    100000,
				BytesSent:        5000,
				ConnectedSince:   now,
				LastActivity:     now.Add(1 * time.Minute),
			},
		}

		data, err := json.Marshal(resp)
		require.NoError(t, err)

		var decoded StreamResponse
		err = json.Unmarshal(data, &decoded)
		require.NoError(t, err)

		assert.Equal(t, resp.ID, decoded.ID)
		assert.Equal(t, resp.Status, decoded.Status)
		assert.Equal(t, resp.Subscriptions, decoded.Subscriptions)
		assert.NotNil(t, decoded.Metrics)
	})
}

func TestSubscriptionResponse(t *testing.T) {
	t.Run("creates success response", func(t *testing.T) {
		resp := SubscriptionResponse{
			Success:       true,
			Symbol:        "BTCUSDT",
			Streams:       []string{"depth", "ticker"},
			SubscribedAt:  time.Now(),
		}

		assert.True(t, resp.Success)
		assert.Equal(t, "BTCUSDT", resp.Symbol)
		assert.Len(t, resp.Streams, 2)
	})

	t.Run("creates error response", func(t *testing.T) {
		resp := SubscriptionResponse{
			Success: false,
			Error:   "Invalid symbol",
		}

		assert.False(t, resp.Success)
		assert.Equal(t, "Invalid symbol", resp.Error)
	})
}

func TestErrorResponse(t *testing.T) {
	t.Run("creates error with all fields", func(t *testing.T) {
		err := NewErrorResponse("VALIDATION_ERROR", "Invalid request", "req-123")

		assert.Equal(t, "VALIDATION_ERROR", err.Error)
		assert.Equal(t, "Invalid request", err.Message)
		assert.Equal(t, "req-123", err.RequestID)
		assert.Greater(t, err.Timestamp, int64(0))
	})

	t.Run("marshals to JSON correctly", func(t *testing.T) {
		err := NewErrorResponse("NOT_FOUND", "Stream not found", "req-456")

		data, marshalErr := json.Marshal(err)
		require.NoError(t, marshalErr)

		var decoded ErrorResponse
		unmarshalErr := json.Unmarshal(data, &decoded)
		require.NoError(t, unmarshalErr)

		assert.Equal(t, err.Error, decoded.Error)
		assert.Equal(t, err.Message, decoded.Message)
		assert.Equal(t, err.RequestID, decoded.RequestID)
	})
}

func TestHealthResponse(t *testing.T) {
	t.Run("creates health response", func(t *testing.T) {
		resp := HealthResponse{
			Status:  "healthy",
			Version: "1.0.0",
			Uptime:  1000,
		}

		assert.Equal(t, "healthy", resp.Status)
		assert.Equal(t, "1.0.0", resp.Version)
		assert.Equal(t, int64(1000), resp.Uptime)
	})
}

func TestReadinessResponse(t *testing.T) {
	t.Run("creates ready response", func(t *testing.T) {
		resp := ReadinessResponse{
			Ready: true,
			Checks: map[string]HealthCheck{
				"websocket": {
					Status:  "healthy",
					Message: "Connected",
				},
				"database": {
					Status:  "healthy",
					Message: "Connection pool active",
				},
			},
		}

		assert.True(t, resp.Ready)
		assert.Len(t, resp.Checks, 2)
		assert.Equal(t, "healthy", resp.Checks["websocket"].Status)
	})

	t.Run("creates not ready response", func(t *testing.T) {
		resp := ReadinessResponse{
			Ready: false,
			Checks: map[string]HealthCheck{
				"websocket": {
					Status:  "unhealthy",
					Message: "Connection failed",
					Error:   "timeout",
				},
			},
		}

		assert.False(t, resp.Ready)
		assert.Equal(t, "unhealthy", resp.Checks["websocket"].Status)
		assert.Equal(t, "timeout", resp.Checks["websocket"].Error)
	})
}

func TestConfigResponse(t *testing.T) {
	t.Run("creates config response", func(t *testing.T) {
		resp := ConfigResponse{
			RateLimit:      100,
			MaxConnections: 10,
			UpdatedAt:      time.Now(),
		}

		assert.Equal(t, 100, resp.RateLimit)
		assert.Equal(t, 10, resp.MaxConnections)
		assert.NotZero(t, resp.UpdatedAt)
	})
}

func TestListResponse(t *testing.T) {
	t.Run("creates paginated list response", func(t *testing.T) {
		streams := []StreamResponse{
			{ID: "stream-1", Status: "connected"},
			{ID: "stream-2", Status: "connected"},
		}

		resp := NewListResponse(streams, 2, 10, 1, 10)

		assert.Len(t, resp.Data, 2)
		assert.Equal(t, 2, resp.Count)
		assert.Equal(t, 10, resp.Total)
		assert.Equal(t, 1, resp.Page)
		assert.Equal(t, 10, resp.PageSize)
	})

	t.Run("marshals generic data correctly", func(t *testing.T) {
		data := []map[string]string{
			{"id": "1", "name": "test1"},
			{"id": "2", "name": "test2"},
		}

		resp := NewListResponse(data, 2, 5, 1, 10)

		jsonData, err := json.Marshal(resp)
		require.NoError(t, err)

		var decoded ListResponse
		err = json.Unmarshal(jsonData, &decoded)
		require.NoError(t, err)

		assert.Equal(t, 2, decoded.Count)
		assert.Equal(t, 5, decoded.Total)
	})
}