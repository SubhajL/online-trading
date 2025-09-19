package websocket

import (
	"context"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestStreamManager_NewStreamManager(t *testing.T) {
	t.Run("creates new stream manager with default settings", func(t *testing.T) {
		sm := NewStreamManager("ws://example.com")

		assert.NotNil(t, sm)
		assert.Equal(t, "ws://example.com", sm.URL())
		assert.Equal(t, StateDisconnected, sm.State())
		assert.Empty(t, sm.ActiveSubscriptions())
	})

	t.Run("creates stream manager with custom options", func(t *testing.T) {
		sm := NewStreamManager("ws://example.com",
			WithAutoReconnect(true),
			WithMaxReconnectAttempts(10))

		assert.NotNil(t, sm)
		assert.Equal(t, "ws://example.com", sm.URL())
	})
}

func TestStreamManager_Connect(t *testing.T) {
	t.Run("establishes connection successfully", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		assert.Equal(t, StateConnected, sm.State())
	})

	t.Run("handles connection failure", func(t *testing.T) {
		sm := NewStreamManager("ws://invalid-url")
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()

		err := sm.Connect(ctx)
		assert.Error(t, err)
		assert.Equal(t, StateDisconnected, sm.State())
	})
}

func TestStreamManager_Subscribe(t *testing.T) {
	t.Run("subscribes to single stream successfully", func(t *testing.T) {
		subscriptionReceived := make(chan SubscriptionRequest, 1)
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}
				subscriptionReceived <- req

				// Send confirmation
				resp := SubscriptionResponse{
					Result: nil,
					ID:     req.ID,
				}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		err = sm.Subscribe(ctx, "btcusdt@depth")
		require.NoError(t, err)

		// Verify subscription request was sent
		select {
		case req := <-subscriptionReceived:
			assert.Equal(t, "SUBSCRIBE", req.Method)
			assert.Equal(t, []string{"btcusdt@depth"}, req.Params)
		case <-time.After(1 * time.Second):
			t.Fatal("Subscription request not received")
		}

		subscriptions := sm.ActiveSubscriptions()
		assert.Contains(t, subscriptions, "btcusdt@depth")
	})

	t.Run("subscribes to multiple streams", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}

				// Send confirmation
				resp := SubscriptionResponse{
					Result: nil,
					ID:     req.ID,
				}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		streams := []string{"btcusdt@depth", "ethusdt@ticker", "adausdt@depth"}
		err = sm.SubscribeMultiple(ctx, streams)
		require.NoError(t, err)

		subscriptions := sm.ActiveSubscriptions()
		for _, stream := range streams {
			assert.Contains(t, subscriptions, stream)
		}
	})

	t.Run("handles subscription errors", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}

				// Send error response
				resp := SubscriptionResponse{
					Result: nil,
					ID:     req.ID,
					Error: &struct {
						Code int    `json:"code"`
						Msg  string `json:"msg"`
					}{
						Code: -2011,
						Msg:  "Invalid symbol.",
					},
				}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		err = sm.Subscribe(ctx, "invalid@symbol")
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "Invalid symbol")

		subscriptions := sm.ActiveSubscriptions()
		assert.NotContains(t, subscriptions, "invalid@symbol")
	})

	t.Run("fails when not connected", func(t *testing.T) {
		sm := NewStreamManager("ws://example.com")
		ctx := context.Background()

		err := sm.Subscribe(ctx, "btcusdt@depth")
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not connected")
	})
}

func TestStreamManager_Unsubscribe(t *testing.T) {
	t.Run("unsubscribes from stream successfully", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}

				// Send confirmation
				resp := SubscriptionResponse{
					Result: nil,
					ID:     req.ID,
				}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		// Subscribe first
		err = sm.Subscribe(ctx, "btcusdt@depth")
		require.NoError(t, err)

		// Then unsubscribe
		err = sm.Unsubscribe(ctx, "btcusdt@depth")
		require.NoError(t, err)

		subscriptions := sm.ActiveSubscriptions()
		assert.NotContains(t, subscriptions, "btcusdt@depth")
	})

	t.Run("handles unsubscribe from non-existent stream", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		err = sm.Unsubscribe(ctx, "nonexistent@stream")
		assert.NoError(t, err) // Should not error for non-existent streams
	})
}

func TestStreamManager_MessageHandling(t *testing.T) {
	t.Run("routes messages to correct handlers", func(t *testing.T) {
		receivedMessages := make(map[string][]json.RawMessage)
		var mu sync.Mutex

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// Wait for subscription
			var req SubscriptionRequest
			conn.ReadJSON(&req)

			// Send confirmation
			resp := SubscriptionResponse{Result: nil, ID: req.ID}
			conn.WriteJSON(resp)

			// Send test messages
			messages := []StreamMessage{
				{
					Stream: "btcusdt@depth",
					Data:   json.RawMessage(`{"e":"depthUpdate","s":"BTCUSDT"}`),
				},
				{
					Stream: "ethusdt@ticker",
					Data:   json.RawMessage(`{"e":"24hrTicker","s":"ETHUSDT"}`),
				},
			}

			for _, msg := range messages {
				conn.WriteJSON(msg)
				time.Sleep(10 * time.Millisecond)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		// Set message handlers
		sm.SetDepthHandler(&mockStreamDepthHandler{
			onDepthUpdate: func(event *DepthUpdateEvent) error {
				mu.Lock()
				defer mu.Unlock()
				data, _ := json.Marshal(event)
				receivedMessages["depth"] = append(receivedMessages["depth"], data)
				return nil
			},
		})

		sm.SetTickerHandler(&mockStreamTickerHandler{
			onTickerUpdate: func(event *TickerEvent) error {
				mu.Lock()
				defer mu.Unlock()
				data, _ := json.Marshal(event)
				receivedMessages["ticker"] = append(receivedMessages["ticker"], data)
				return nil
			},
		})

		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		err = sm.SubscribeMultiple(ctx, []string{"btcusdt@depth", "ethusdt@ticker"})
		require.NoError(t, err)

		// Wait for messages
		time.Sleep(100 * time.Millisecond)

		mu.Lock()
		defer mu.Unlock()

		assert.Len(t, receivedMessages["depth"], 1)
		assert.Len(t, receivedMessages["ticker"], 1)
	})

	t.Run("handles malformed messages gracefully", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// Send malformed JSON
			conn.WriteMessage(websocket.TextMessage, []byte(`{"invalid json`))

			// Send valid message after malformed one
			validMsg := StreamMessage{
				Stream: "btcusdt@depth",
				Data:   json.RawMessage(`{"e":"depthUpdate","s":"BTCUSDT"}`),
			}
			conn.WriteJSON(validMsg)
		})
		defer server.Close()

		receivedCount := 0
		sm := NewStreamManager(getWebSocketURL(server.URL))
		sm.SetDepthHandler(&mockStreamDepthHandler{
			onDepthUpdate: func(event *DepthUpdateEvent) error {
				receivedCount++
				return nil
			},
		})

		ctx := context.Background()
		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		// Wait for messages
		time.Sleep(100 * time.Millisecond)

		// Should still receive the valid message despite malformed one
		assert.Equal(t, 1, receivedCount)
	})
}

func TestStreamManager_Reconnection(t *testing.T) {
	t.Run("resubscribes to active streams after reconnection", func(t *testing.T) {
		connectionCount := 0
		subscriptionCount := 0
		var mu sync.Mutex

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			mu.Lock()
			connectionCount++
			currentConnection := connectionCount
			mu.Unlock()

			if currentConnection == 1 {
				// First connection - handle subscription then close
				var req SubscriptionRequest
				conn.ReadJSON(&req)

				mu.Lock()
				subscriptionCount++
				mu.Unlock()

				resp := SubscriptionResponse{Result: nil, ID: req.ID}
				conn.WriteJSON(resp)

				time.Sleep(50 * time.Millisecond)
				return // Close connection to trigger reconnection
			} else {
				// Second connection - should receive resubscription
				var req SubscriptionRequest
				conn.ReadJSON(&req)

				mu.Lock()
				subscriptionCount++
				mu.Unlock()

				resp := SubscriptionResponse{Result: nil, ID: req.ID}
				conn.WriteJSON(resp)

				// Keep connection alive
				for {
					if _, _, err := conn.ReadMessage(); err != nil {
						return
					}
				}
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL),
			WithAutoReconnect(true),
			WithReconnectInterval(50*time.Millisecond))

		ctx := context.Background()
		err := sm.Connect(ctx)
		require.NoError(t, err)
		defer sm.Close()

		err = sm.Subscribe(ctx, "btcusdt@depth")
		require.NoError(t, err)

		// Wait for reconnection and resubscription
		time.Sleep(300 * time.Millisecond)

		mu.Lock()
		defer mu.Unlock()

		assert.GreaterOrEqual(t, connectionCount, 2, "Should have reconnected")
		assert.GreaterOrEqual(t, subscriptionCount, 2, "Should have resubscribed")

		// Verify subscription is still active
		subscriptions := sm.ActiveSubscriptions()
		assert.Contains(t, subscriptions, "btcusdt@depth")
	})
}

func TestStreamManager_Close(t *testing.T) {
	t.Run("closes connection and clears subscriptions", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}
				// Send confirmation
				resp := SubscriptionResponse{Result: nil, ID: req.ID}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		sm := NewStreamManager(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := sm.Connect(ctx)
		require.NoError(t, err)

		err = sm.Subscribe(ctx, "btcusdt@depth")
		require.NoError(t, err)

		// Verify subscription exists
		assert.Contains(t, sm.ActiveSubscriptions(), "btcusdt@depth")

		err = sm.Close()
		assert.NoError(t, err)

		assert.Equal(t, StateClosed, sm.State())
		assert.Empty(t, sm.ActiveSubscriptions())
	})
}

// Mock handlers with callback functions for testing
type mockStreamDepthHandler struct {
	onDepthUpdate func(*DepthUpdateEvent) error
}

func (m *mockStreamDepthHandler) HandleDepthUpdate(event *DepthUpdateEvent) error {
	if m.onDepthUpdate != nil {
		return m.onDepthUpdate(event)
	}
	return nil
}

type mockStreamTickerHandler struct {
	onTickerUpdate func(*TickerEvent) error
}

func (m *mockStreamTickerHandler) HandleTickerUpdate(event *TickerEvent) error {
	if m.onTickerUpdate != nil {
		return m.onTickerUpdate(event)
	}
	return nil
}