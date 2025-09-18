package models

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCreateStreamRequest(t *testing.T) {
	t.Run("validates required fields", func(t *testing.T) {
		req := CreateStreamRequest{}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "type is required")
	})

	t.Run("validates stream type", func(t *testing.T) {
		req := CreateStreamRequest{
			Type: "invalid",
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "type must be 'public' or 'user'")
	})

	t.Run("accepts valid public stream", func(t *testing.T) {
		req := CreateStreamRequest{
			Type:          "public",
			AutoReconnect: true,
			MaxReconnect:  5,
		}
		err := req.Validate()
		assert.NoError(t, err)
	})

	t.Run("accepts valid user stream", func(t *testing.T) {
		req := CreateStreamRequest{
			Type: "user",
		}
		err := req.Validate()
		assert.NoError(t, err)
	})

	t.Run("marshals to JSON correctly", func(t *testing.T) {
		req := CreateStreamRequest{
			Type:          "public",
			AutoReconnect: true,
			MaxReconnect:  10,
		}

		data, err := json.Marshal(req)
		require.NoError(t, err)

		var decoded CreateStreamRequest
		err = json.Unmarshal(data, &decoded)
		require.NoError(t, err)

		assert.Equal(t, req, decoded)
	})
}

func TestSubscribeRequest(t *testing.T) {
	t.Run("validates required symbol", func(t *testing.T) {
		req := SubscribeRequest{
			Streams: []string{"depth"},
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "symbol is required")
	})

	t.Run("validates required streams", func(t *testing.T) {
		req := SubscribeRequest{
			Symbol: "BTCUSDT",
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "at least one stream is required")
	})

	t.Run("validates stream types", func(t *testing.T) {
		req := SubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"invalid"},
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid stream type")
	})

	t.Run("accepts valid streams", func(t *testing.T) {
		req := SubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth", "ticker", "trades"},
		}
		err := req.Validate()
		assert.NoError(t, err)
	})

	t.Run("normalizes symbol to uppercase", func(t *testing.T) {
		req := SubscribeRequest{
			Symbol:  "btcusdt",
			Streams: []string{"depth"},
		}
		req.Normalize()
		assert.Equal(t, "BTCUSDT", req.Symbol)
	})
}

func TestUserDataRequest(t *testing.T) {
	t.Run("validates required listen key", func(t *testing.T) {
		req := UserDataRequest{}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "listen_key is required")
	})

	t.Run("accepts valid listen key", func(t *testing.T) {
		req := UserDataRequest{
			ListenKey: "pqia91ma19a5s61cv6a81va65sdf19v8a65a1a5s61cv6a81va65sdf19v8a65a1",
		}
		err := req.Validate()
		assert.NoError(t, err)
	})
}

func TestUnsubscribeRequest(t *testing.T) {
	t.Run("validates required fields", func(t *testing.T) {
		req := UnsubscribeRequest{}
		err := req.Validate()
		assert.Error(t, err)
	})

	t.Run("accepts symbol with streams", func(t *testing.T) {
		req := UnsubscribeRequest{
			Symbol:  "BTCUSDT",
			Streams: []string{"depth"},
		}
		err := req.Validate()
		assert.NoError(t, err)
	})

	t.Run("accepts stream ID", func(t *testing.T) {
		req := UnsubscribeRequest{
			StreamID: "stream-123",
		}
		err := req.Validate()
		assert.NoError(t, err)
	})
}

func TestConfigUpdateRequest(t *testing.T) {
	t.Run("validates rate limit range", func(t *testing.T) {
		req := ConfigUpdateRequest{
			RateLimit: intPtr(-1),
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "rate limit must be positive")
	})

	t.Run("validates max connections range", func(t *testing.T) {
		req := ConfigUpdateRequest{
			MaxConnections: intPtr(0),
		}
		err := req.Validate()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "max connections must be positive")
	})

	t.Run("accepts valid configuration", func(t *testing.T) {
		req := ConfigUpdateRequest{
			RateLimit:      intPtr(100),
			MaxConnections: intPtr(10),
		}
		err := req.Validate()
		assert.NoError(t, err)
	})

	t.Run("allows partial updates", func(t *testing.T) {
		req := ConfigUpdateRequest{
			RateLimit: intPtr(50),
		}
		err := req.Validate()
		assert.NoError(t, err)
	})
}

func intPtr(v int) *int {
	return &v
}