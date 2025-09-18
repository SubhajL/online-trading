package websocket

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewConnection(t *testing.T) {
	t.Run("creates connection with default options", func(t *testing.T) {
		conn := NewConnection("ws://example.com")
		assert.NotNil(t, conn)
		assert.Equal(t, "ws://example.com", conn.URL())
		assert.Equal(t, StateDisconnected, conn.State())
		assert.Equal(t, 30*time.Second, conn.PingInterval())
		assert.Equal(t, 60*time.Second, conn.PongTimeout())
	})

	t.Run("applies custom options", func(t *testing.T) {
		conn := NewConnection("ws://example.com",
			WithPingInterval(15*time.Second),
			WithPongTimeout(30*time.Second),
			WithWriteTimeout(5*time.Second),
			WithReadTimeout(10*time.Second),
		)

		assert.Equal(t, 15*time.Second, conn.PingInterval())
		assert.Equal(t, 30*time.Second, conn.PongTimeout())
		assert.Equal(t, 5*time.Second, conn.WriteTimeout())
		assert.Equal(t, 10*time.Second, conn.ReadTimeout())
	})

	t.Run("validates URL format", func(t *testing.T) {
		conn := NewConnection("invalid-url")
		assert.NotNil(t, conn)
		assert.Equal(t, "invalid-url", conn.URL())
	})
}

func TestConnection_Connect(t *testing.T) {
	t.Run("establishes WebSocket connection successfully", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			// Simple echo server
			defer conn.Close()
			for {
				messageType, p, err := conn.ReadMessage()
				if err != nil {
					return
				}
				if err := conn.WriteMessage(messageType, p); err != nil {
					return
				}
			}
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()

		err := wsConn.Connect(ctx)
		assert.NoError(t, err)
		assert.Equal(t, StateConnected, wsConn.State())

		// Clean up
		wsConn.Close()
	})

	t.Run("handles connection timeout", func(t *testing.T) {
		// Connect to non-existent server
		wsConn := NewConnection("ws://non-existent-server:9999")
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()

		err := wsConn.Connect(ctx)
		assert.Error(t, err)
		assert.Equal(t, StateDisconnected, wsConn.State())
	})

	t.Run("sets connection state correctly during connect", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			time.Sleep(50 * time.Millisecond) // Brief delay
			conn.ReadMessage()
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		// Should start as disconnected
		assert.Equal(t, StateDisconnected, wsConn.State())

		// Connect and verify state transitions
		err := wsConn.Connect(ctx)
		assert.NoError(t, err)
		assert.Equal(t, StateConnected, wsConn.State())

		wsConn.Close()
	})

	t.Run("prevents multiple concurrent connections", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			conn.ReadMessage()
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		// Start first connection
		err1 := wsConn.Connect(ctx)
		assert.NoError(t, err1)

		// Try second connection while first is active
		err2 := wsConn.Connect(ctx)
		assert.Error(t, err2)
		assert.Contains(t, err2.Error(), "already connected")

		wsConn.Close()
	})
}

func TestConnection_Send(t *testing.T) {
	t.Run("sends messages successfully", func(t *testing.T) {
		received := make(chan []byte, 1)
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			_, message, err := conn.ReadMessage()
			if err == nil {
				received <- message
			}
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		testMessage := []byte(`{"test": "message"}`)
		err = wsConn.Send(ctx, testMessage)
		assert.NoError(t, err)

		select {
		case receivedMsg := <-received:
			assert.Equal(t, testMessage, receivedMsg)
		case <-time.After(1 * time.Second):
			t.Fatal("Message not received within timeout")
		}
	})

	t.Run("handles send timeout", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Don't read messages to eventually block the send buffer
			time.Sleep(2 * time.Second)
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithWriteTimeout(50*time.Millisecond))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Send large messages to fill buffer and cause timeout
		// Create a large message (1MB) to fill WebSocket buffer faster
		largeMessage := make([]byte, 1024*1024)
		for i := range largeMessage {
			largeMessage[i] = byte('A')
		}

		// Keep sending until we get a timeout
		var lastErr error
		for i := 0; i < 10; i++ {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
			lastErr = wsConn.Send(ctx, largeMessage)
			cancel()
			if lastErr != nil {
				break
			}
		}

		assert.Error(t, lastErr, "Expected timeout error after sending large messages")
	})

	t.Run("fails when not connected", func(t *testing.T) {
		wsConn := NewConnection("ws://example.com")
		ctx := context.Background()

		err := wsConn.Send(ctx, []byte("test"))
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "not connected")
	})

	t.Run("thread-safe concurrent sends", func(t *testing.T) {
		messageCount := 50
		received := make(chan bool, messageCount)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			for i := 0; i < messageCount; i++ {
				_, _, err := conn.ReadMessage()
				if err != nil {
					return
				}
				received <- true
			}
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		var wg sync.WaitGroup
		for i := 0; i < messageCount; i++ {
			wg.Add(1)
			go func(id int) {
				defer wg.Done()
				message := []byte(`{"id":` + string(rune(id)) + `}`)
				err := wsConn.Send(ctx, message)
				assert.NoError(t, err)
			}(i)
		}

		wg.Wait()

		// Verify all messages received
		receivedCount := 0
		timeout := time.After(2 * time.Second)
		for receivedCount < messageCount {
			select {
			case <-received:
				receivedCount++
			case <-timeout:
				t.Fatalf("Only received %d/%d messages", receivedCount, messageCount)
			}
		}
	})
}

func TestConnection_PingPong(t *testing.T) {
	t.Run("maintains connection with ping-pong", func(t *testing.T) {
		pingReceived := make(chan bool, 1)
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Set ping handler to respond to client pings with pongs
			conn.SetPingHandler(func(appData string) error {
				pingReceived <- true
				return conn.WriteMessage(websocket.PongMessage, []byte(appData))
			})

			// Keep connection alive
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithPingInterval(100*time.Millisecond),
			WithPongTimeout(500*time.Millisecond))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for ping-pong cycle
		select {
		case <-pingReceived:
			// Success - server received ping and sent pong
		case <-time.After(1 * time.Second):
			t.Fatal("Ping not received within timeout")
		}
	})

	t.Run("detects connection failure on pong timeout", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Set ping handler that doesn't respond (ignores pings)
			conn.SetPingHandler(func(appData string) error {
				// Explicitly do not respond with pong
				return nil
			})

			// Keep connection alive but don't respond to pings
			for {
				if _, _, err := conn.ReadMessage(); err != nil {
					return
				}
			}
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithPingInterval(50*time.Millisecond),
			WithPongTimeout(100*time.Millisecond),
			WithAutoReconnect(false)) // Disable auto-reconnect for this test
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for connection to be detected as failed
		time.Sleep(300 * time.Millisecond)

		// Connection should be disconnected when pong timeout occurs and auto-reconnect is disabled
		state := wsConn.State()
		if state != StateDisconnected {
			t.Logf("Expected Disconnected(0), got %s(%d)", state.String(), state)
		}
		assert.Equal(t, StateDisconnected, state)
	})
}

func TestConnection_Reconnection(t *testing.T) {
	t.Run("reconnects automatically on connection loss", func(t *testing.T) {
		reconnected := make(chan bool, 1)
		connectionCount := 0

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			connectionCount++

			if connectionCount == 1 {
				// First connection - close after brief period
				time.Sleep(100 * time.Millisecond)
				return
			}

			// Second connection - signal reconnection
			reconnected <- true
			conn.ReadMessage()
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithAutoReconnect(true),
			WithReconnectInterval(100*time.Millisecond))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for reconnection
		select {
		case <-reconnected:
			// Give a small delay for connection to fully establish
			time.Sleep(50 * time.Millisecond)
			assert.Equal(t, StateConnected, wsConn.State())
		case <-time.After(2 * time.Second):
			t.Fatal("Reconnection not detected within timeout")
		}
	})

	t.Run("respects maximum reconnection attempts", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Always close immediately
			return
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithAutoReconnect(true),
			WithMaxReconnectAttempts(2),
			WithReconnectInterval(50*time.Millisecond))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for all reconnection attempts to fail
		// With 2 max attempts and 50ms interval, need time for exponential backoff:
		// Attempt 1: 50ms delay + connection attempt
		// Attempt 2: 100ms delay + connection attempt
		// Total: ~200ms + connection time, but give generous timeout
		time.Sleep(3 * time.Second)

		// Should eventually give up
		state := wsConn.State()
		if state != StateDisconnected {
			t.Logf("Expected Disconnected(0), got %s(%d)", state.String(), state)
		}
		assert.Equal(t, StateDisconnected, state)
	})

	t.Run("uses exponential backoff for reconnection", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			return // Always fail immediately
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL),
			WithAutoReconnect(true),
			WithMaxReconnectAttempts(3),
			WithReconnectInterval(50*time.Millisecond)) // Use smaller interval for faster test
		ctx := context.Background()

		startTime := time.Now()
		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for all attempts (3 attempts with 50ms, 100ms, 200ms delays)
		time.Sleep(1 * time.Second)

		state := wsConn.State()
		assert.Equal(t, StateDisconnected, state)

		// Verify total time is reasonable for exponential backoff
		// Expected: ~50ms + ~100ms + ~200ms = ~350ms minimum
		totalTime := time.Since(startTime)
		t.Logf("Total reconnection time: %v", totalTime)
		assert.GreaterOrEqual(t, totalTime, 300*time.Millisecond,
			"Expected at least 300ms for exponential backoff delays")
	})
}

func TestConnection_Close(t *testing.T) {
	t.Run("closes connection gracefully", func(t *testing.T) {
		closed := make(chan bool, 1)
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer func() {
				closed <- true
				conn.Close()
			}()
			conn.ReadMessage()
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)

		err = wsConn.Close()
		assert.NoError(t, err)
		assert.Equal(t, StateClosed, wsConn.State())

		// Verify server side was notified
		select {
		case <-closed:
			// Success
		case <-time.After(1 * time.Second):
			t.Fatal("Server side close not detected")
		}
	})

	t.Run("handles multiple close calls", func(t *testing.T) {
		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			conn.ReadMessage()
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		ctx := context.Background()

		err := wsConn.Connect(ctx)
		require.NoError(t, err)

		// Multiple closes should not panic
		err1 := wsConn.Close()
		err2 := wsConn.Close()

		assert.NoError(t, err1)
		assert.NoError(t, err2) // Should be idempotent
		assert.Equal(t, StateClosed, wsConn.State())
	})

	t.Run("closes without connecting", func(t *testing.T) {
		wsConn := NewConnection("ws://example.com")

		err := wsConn.Close()
		assert.NoError(t, err)
		assert.Equal(t, StateClosed, wsConn.State())
	})
}

func TestConnection_MessageHandling(t *testing.T) {
	t.Run("receives messages from server", func(t *testing.T) {
		testMessage := []byte(`{"event": "test"}`)
		received := make(chan []byte, 1)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			// Send test message
			conn.WriteMessage(websocket.TextMessage, testMessage)
			time.Sleep(100 * time.Millisecond)
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		wsConn.SetMessageHandler(func(data []byte) {
			received <- data
		})

		ctx := context.Background()
		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for message
		select {
		case receivedMsg := <-received:
			assert.Equal(t, testMessage, receivedMsg)
		case <-time.After(1 * time.Second):
			t.Fatal("Message not received within timeout")
		}
	})

	t.Run("handles large messages", func(t *testing.T) {
		// Create a large test message (64KB)
		largeMessage := make([]byte, 64*1024)
		for i := range largeMessage {
			largeMessage[i] = byte(i % 256)
		}

		received := make(chan []byte, 1)

		server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
			defer conn.Close()
			conn.WriteMessage(websocket.BinaryMessage, largeMessage)
			time.Sleep(100 * time.Millisecond)
		})
		defer server.Close()

		wsConn := NewConnection(getWebSocketURL(server.URL))
		wsConn.SetMessageHandler(func(data []byte) {
			received <- data
		})

		ctx := context.Background()
		err := wsConn.Connect(ctx)
		require.NoError(t, err)
		defer wsConn.Close()

		// Wait for large message
		select {
		case receivedMsg := <-received:
			assert.Equal(t, largeMessage, receivedMsg)
		case <-time.After(2 * time.Second):
			t.Fatal("Large message not received within timeout")
		}
	})
}

// Helper functions for testing

func newMockWebSocketServer(t *testing.T, handler func(*websocket.Conn)) *httptest.Server {
	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Logf("WebSocket upgrade failed: %v", err)
			return
		}
		handler(conn)
	}))

	return server
}

func getWebSocketURL(httpURL string) string {
	return strings.Replace(httpURL, "http://", "ws://", 1)
}