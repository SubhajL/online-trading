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

func TestClient_NewClient(t *testing.T) {
	t.Run("creates new client with default settings", func(t *testing.T) {
		client := NewClient()

		assert.NotNil(t, client)
		assert.Equal(t, DefaultBaseURL, client.BaseURL())
		assert.Equal(t, StateDisconnected, client.State())
	})

	t.Run("creates client with custom base URL", func(t *testing.T) {
		client := NewClient(WithBaseURL("wss://custom.example.com"))

		assert.Equal(t, "wss://custom.example.com", client.BaseURL())
	})

	t.Run("creates client with auto-reconnect enabled", func(t *testing.T) {
		client := NewClient(
			WithAutoReconnectClient(true),
			WithMaxReconnectAttemptsClient(10),
			WithReconnectIntervalClient(1*time.Second))

		assert.NotNil(t, client)
	})
}

func TestClient_Connect(t *testing.T) {
	t.Run("connects to public streams successfully", func(t *testing.T) {
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

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		assert.Equal(t, StateConnected, client.State())
	})

	t.Run("handles connection failure gracefully", func(t *testing.T) {
		client := NewClient(WithBaseURL("ws://invalid-url"))
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()

		err := client.Connect(ctx)
		assert.Error(t, err)
		assert.Equal(t, StateDisconnected, client.State())
	})
}

func TestClient_SubscribeToDepth(t *testing.T) {
	t.Run("subscribes to depth updates successfully", func(t *testing.T) {
		subscriptionReceived := make(chan SubscriptionRequest, 1)
		depthUpdates := make(chan *DepthUpdateEvent, 1)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// Handle subscription
			var req SubscriptionRequest
			conn.ReadJSON(&req)
			subscriptionReceived <- req

			// Send confirmation
			resp := SubscriptionResponse{Result: nil, ID: req.ID}
			conn.WriteJSON(resp)

			// Send depth update
			depthMsg := StreamMessage{
				Stream: "btcusdt@depth",
				Data:   json.RawMessage(`{"e":"depthUpdate","s":"BTCUSDT","U":1,"u":2,"b":[["50000","1.0"]],"a":[["51000","2.0"]]}`),
			}
			conn.WriteJSON(depthMsg)

			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		err = client.SubscribeToDepth(ctx, "BTCUSDT", func(event *DepthUpdateEvent) error {
			depthUpdates <- event
			return nil
		})
		require.NoError(t, err)

		// Verify subscription was sent
		select {
		case req := <-subscriptionReceived:
			assert.Equal(t, "SUBSCRIBE", req.Method)
			assert.Contains(t, req.Params, "btcusdt@depth")
		case <-time.After(1 * time.Second):
			t.Fatal("Subscription not received")
		}

		// Verify depth update was received
		select {
		case event := <-depthUpdates:
			assert.Equal(t, "depthUpdate", event.EventType)
			assert.Equal(t, "BTCUSDT", event.Symbol)
		case <-time.After(1 * time.Second):
			t.Fatal("Depth update not received")
		}
	})
}

func TestClient_SubscribeToTicker(t *testing.T) {
	t.Run("subscribes to ticker updates successfully", func(t *testing.T) {
		tickerUpdates := make(chan *TickerEvent, 1)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// Handle subscription
			var req SubscriptionRequest
			conn.ReadJSON(&req)

			// Send confirmation
			resp := SubscriptionResponse{Result: nil, ID: req.ID}
			conn.WriteJSON(resp)

			// Send ticker update
			tickerMsg := StreamMessage{
				Stream: "btcusdt@ticker",
				Data:   json.RawMessage(`{"e":"24hrTicker","s":"BTCUSDT","c":"50000","P":"2.5"}`),
			}
			conn.WriteJSON(tickerMsg)

			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		err = client.SubscribeToTicker(ctx, "BTCUSDT", func(event *TickerEvent) error {
			tickerUpdates <- event
			return nil
		})
		require.NoError(t, err)

		// Verify ticker update was received
		select {
		case event := <-tickerUpdates:
			assert.Equal(t, "24hrTicker", event.EventType)
			assert.Equal(t, "BTCUSDT", event.Symbol)
		case <-time.After(1 * time.Second):
			t.Fatal("Ticker update not received")
		}
	})
}

func TestClient_SubscribeToUserData(t *testing.T) {
	t.Run("subscribes to user data stream successfully", func(t *testing.T) {
		accountUpdates := make(chan *AccountUpdateEvent, 1)
		orderUpdates := make(chan *OrderUpdateEvent, 1)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// User data streams don't need subscription requests
			// Just send data immediately

			// Send account update
			accountMsg := StreamMessage{
				Stream: "test-listen-key",
				Data:   json.RawMessage(`{"e":"outboundAccountPosition","u":1234,"B":[{"a":"BTC","f":"1.0","l":"0.0"}]}`),
			}
			conn.WriteJSON(accountMsg)

			// Send order update
			orderMsg := StreamMessage{
				Stream: "test-listen-key",
				Data:   json.RawMessage(`{"e":"executionReport","s":"BTCUSDT","c":"test-order","S":"BUY","X":"FILLED"}`),
			}
			conn.WriteJSON(orderMsg)

			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		handler := &UserDataHandler{
			OnAccountUpdate: func(event *AccountUpdateEvent) error {
				accountUpdates <- event
				return nil
			},
			OnOrderUpdate: func(event *OrderUpdateEvent) error {
				orderUpdates <- event
				return nil
			},
		}

		err = client.SubscribeToUserData(ctx, "test-listen-key", handler)
		require.NoError(t, err)

		// Verify account update was received
		select {
		case event := <-accountUpdates:
			assert.Equal(t, "outboundAccountPosition", event.EventType)
		case <-time.After(1 * time.Second):
			t.Fatal("Account update not received")
		}

		// Verify order update was received
		select {
		case event := <-orderUpdates:
			assert.Equal(t, "executionReport", event.EventType)
			assert.Equal(t, "FILLED", event.OrderStatus)
		case <-time.After(1 * time.Second):
			t.Fatal("Order update not received")
		}
	})
}

func TestClient_MultipleSubscriptions(t *testing.T) {
	t.Run("handles multiple concurrent subscriptions", func(t *testing.T) {
		depthUpdates := make(chan string, 5)
		tickerUpdates := make(chan string, 5)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			// Handle multiple subscriptions
			for i := 0; i < 3; i++ {
				var req SubscriptionRequest
				conn.ReadJSON(&req)

				// Send confirmation
				resp := SubscriptionResponse{Result: nil, ID: req.ID}
				conn.WriteJSON(resp)
			}

			// Send test messages
			messages := []StreamMessage{
				{Stream: "btcusdt@depth", Data: json.RawMessage(`{"e":"depthUpdate","s":"BTCUSDT"}`)},
				{Stream: "ethusdt@depth", Data: json.RawMessage(`{"e":"depthUpdate","s":"ETHUSDT"}`)},
				{Stream: "btcusdt@ticker", Data: json.RawMessage(`{"e":"24hrTicker","s":"BTCUSDT"}`)},
			}

			for _, msg := range messages {
				conn.WriteJSON(msg)
				time.Sleep(10 * time.Millisecond)
			}

			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		// Subscribe to multiple depth streams
		err = client.SubscribeToDepth(ctx, "BTCUSDT", func(event *DepthUpdateEvent) error {
			depthUpdates <- event.Symbol
			return nil
		})
		require.NoError(t, err)

		err = client.SubscribeToDepth(ctx, "ETHUSDT", func(event *DepthUpdateEvent) error {
			depthUpdates <- event.Symbol
			return nil
		})
		require.NoError(t, err)

		// Subscribe to ticker
		err = client.SubscribeToTicker(ctx, "BTCUSDT", func(event *TickerEvent) error {
			tickerUpdates <- event.Symbol
			return nil
		})
		require.NoError(t, err)

		// Verify all updates are received
		receivedDepthSymbols := make(map[string]bool)
		for i := 0; i < 2; i++ {
			select {
			case symbol := <-depthUpdates:
				receivedDepthSymbols[symbol] = true
			case <-time.After(1 * time.Second):
				t.Fatal("Depth update not received")
			}
		}

		assert.True(t, receivedDepthSymbols["BTCUSDT"])
		assert.True(t, receivedDepthSymbols["ETHUSDT"])

		select {
		case symbol := <-tickerUpdates:
			assert.Equal(t, "BTCUSDT", symbol)
		case <-time.After(1 * time.Second):
			t.Fatal("Ticker update not received")
		}
	})
}

func TestClient_Unsubscribe(t *testing.T) {
	t.Run("unsubscribes from streams successfully", func(t *testing.T) {
		subscriptionCount := 0
		var mu sync.Mutex

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()

			for {
				var req SubscriptionRequest
				if err := conn.ReadJSON(&req); err != nil {
					return
				}

				mu.Lock()
				subscriptionCount++
				mu.Unlock()

				// Send confirmation
				resp := SubscriptionResponse{Result: nil, ID: req.ID}
				conn.WriteJSON(resp)
			}
		})
		defer server.Close()

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)
		defer client.Close()

		// Subscribe
		err = client.SubscribeToDepth(ctx, "BTCUSDT", func(event *DepthUpdateEvent) error {
			return nil
		})
		require.NoError(t, err)

		// Unsubscribe
		err = client.UnsubscribeFromDepth(ctx, "BTCUSDT")
		require.NoError(t, err)

		time.Sleep(100 * time.Millisecond)

		mu.Lock()
		count := subscriptionCount
		mu.Unlock()

		assert.Equal(t, 2, count) // 1 SUBSCRIBE + 1 UNSUBSCRIBE
	})
}

func TestClient_Close(t *testing.T) {
	t.Run("closes connection and cleans up resources", func(t *testing.T) {
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

		client := NewClient(WithBaseURL(getWebSocketURL(server.URL)))
		ctx := context.Background()

		err := client.Connect(ctx)
		require.NoError(t, err)

		err = client.SubscribeToDepth(ctx, "BTCUSDT", func(event *DepthUpdateEvent) error {
			return nil
		})
		require.NoError(t, err)

		err = client.Close()
		assert.NoError(t, err)

		assert.Equal(t, StateDisconnected, client.State())
		assert.Empty(t, client.ActiveSubscriptions())
	})
}
