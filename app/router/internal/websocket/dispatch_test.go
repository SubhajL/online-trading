package websocket

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestConnection_DispatchPreservesArrivalOrder(t *testing.T) {
	const messageCount = 50
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		for i := 0; i < messageCount; i++ {
			if err := conn.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("msg-%03d", i))); err != nil {
				return
			}
		}
		select {} // hold the connection open
	})
	defer server.Close()

	var mu sync.Mutex
	var received []string
	var firstDelay sync.Once
	done := make(chan struct{})

	conn := NewConnection(getWebSocketURL(server.URL))
	conn.SetMessageHandler(func(message []byte) {
		// A slow first handler would let go-per-message dispatch reorder;
		// serialized dispatch must still deliver in arrival order.
		firstDelay.Do(func() { time.Sleep(100 * time.Millisecond) })
		mu.Lock()
		received = append(received, string(message))
		if len(received) == messageCount {
			close(done)
		}
		mu.Unlock()
	})

	require.NoError(t, conn.Connect(context.Background()))
	defer func() { _ = conn.Close() }()

	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for messages")
	}

	expected := make([]string, messageCount)
	for i := range expected {
		expected[i] = fmt.Sprintf("msg-%03d", i)
	}
	mu.Lock()
	defer mu.Unlock()
	assert.Equal(t, expected, received)
}

func TestConnection_FullDispatchQueueBackpressuresWithoutDropping(t *testing.T) {
	const messageCount = 10
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		for i := 0; i < messageCount; i++ {
			if err := conn.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("m%d", i))); err != nil {
				return
			}
		}
		select {}
	})
	defer server.Close()

	gate := make(chan struct{})
	var handled atomic.Int64

	conn := NewConnection(getWebSocketURL(server.URL), WithDispatchBuffer(1))
	conn.SetMessageHandler(func([]byte) {
		<-gate
		handled.Add(1)
	})

	require.NoError(t, conn.Connect(context.Background()))
	defer func() { _ = conn.Close() }()

	// Handler blocked, buffer size 1: nothing may be dropped meanwhile.
	time.Sleep(200 * time.Millisecond)
	assert.Equal(t, int64(0), handled.Load())

	close(gate)
	require.Eventually(t, func() bool {
		return handled.Load() == messageCount
	}, 5*time.Second, 10*time.Millisecond, "all messages must survive backpressure")
}

func TestConnection_CloseTerminatesDispatch(t *testing.T) {
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		select {}
	})
	defer server.Close()

	conn := NewConnection(getWebSocketURL(server.URL))
	conn.SetMessageHandler(func([]byte) {})

	require.NoError(t, conn.Connect(context.Background()))
	require.NoError(t, conn.Close())

	select {
	case <-conn.dispatchStop:
	default:
		t.Fatal("dispatchStop must be closed after Close")
	}
}

func TestConnection_ReconnectHandlerFiresAfterSocketReconnect(t *testing.T) {
	var connCount atomic.Int64
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		n := connCount.Add(1)
		if n == 1 {
			_ = conn.Close() // kill the first connection to force a reconnect
			return
		}
		select {}
	})
	defer server.Close()

	var reconnects atomic.Int64
	conn := NewConnection(getWebSocketURL(server.URL),
		WithAutoReconnect(true),
		WithMaxReconnectAttempts(5),
		WithReconnectInterval(10*time.Millisecond),
	)
	conn.SetReconnectHandler(func() { reconnects.Add(1) })
	conn.SetMessageHandler(func([]byte) {})

	require.NoError(t, conn.Connect(context.Background()))
	defer func() { _ = conn.Close() }()

	require.Eventually(t, func() bool {
		return reconnects.Load() >= 1
	}, 5*time.Second, 10*time.Millisecond, "reconnect handler must fire after socket recovery")
}

func TestConnection_CloseDrainsQueuedMessages(t *testing.T) {
	const messageCount = 5
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		for i := 0; i < messageCount; i++ {
			if err := conn.WriteMessage(websocket.TextMessage, []byte(fmt.Sprintf("m%d", i))); err != nil {
				return
			}
		}
		select {}
	})
	defer server.Close()

	gate := make(chan struct{})
	var handled atomic.Int64

	conn := NewConnection(getWebSocketURL(server.URL), WithDispatchBuffer(messageCount))
	conn.SetMessageHandler(func([]byte) {
		<-gate
		handled.Add(1)
	})

	require.NoError(t, conn.Connect(context.Background()))
	time.Sleep(200 * time.Millisecond) // let all messages enqueue behind the gate
	require.NoError(t, conn.Close())
	close(gate)

	require.Eventually(t, func() bool {
		return handled.Load() == messageCount
	}, 5*time.Second, 10*time.Millisecond,
		"already-received fill events must be drained on close, never dropped")
}

func TestConnection_ReconnectHandlerNotFiredOnFirstConnect(t *testing.T) {
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		select {}
	})
	defer server.Close()

	var reconnects atomic.Int64
	conn := NewConnection(getWebSocketURL(server.URL), WithAutoReconnect(true))
	conn.SetReconnectHandler(func() { reconnects.Add(1) })
	conn.SetMessageHandler(func([]byte) {})

	require.NoError(t, conn.Connect(context.Background()))
	defer func() { _ = conn.Close() }()

	time.Sleep(150 * time.Millisecond)
	assert.Equal(t, int64(0), reconnects.Load())
}

func TestConnection_ConnectAfterCloseFailsLoudly(t *testing.T) {
	server := newMockWebSocketServer(t, func(conn *websocket.Conn) {
		select {}
	})
	defer server.Close()

	conn := NewConnection(getWebSocketURL(server.URL))
	require.NoError(t, conn.Connect(context.Background()))
	require.NoError(t, conn.Close())

	err := conn.Connect(context.Background())
	require.Error(t, err, "a closed connection has a dead dispatch loop; reuse must fail loudly")
}
