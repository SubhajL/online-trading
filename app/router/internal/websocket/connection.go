package websocket

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// Connection represents a WebSocket connection with reconnection capabilities
type Connection struct {
	url     string
	state   ConnectionState
	stateMu sync.RWMutex

	// Connection options
	pingInterval         time.Duration
	pongTimeout          time.Duration
	writeTimeout         time.Duration
	readTimeout          time.Duration
	autoReconnect        bool
	maxReconnectAttempts int
	reconnectInterval    time.Duration

	// Pong tracking
	lastPongTime time.Time
	pongMu       sync.Mutex

	// WebSocket connection
	conn    *websocket.Conn
	connMu  sync.Mutex
	writeMu sync.Mutex // Protects writes to WebSocket

	// Message handling
	messageHandler func([]byte)
	handlerMu      sync.RWMutex

	// Control channels
	closeChan chan struct{}
	doneChan  chan struct{}
	doneOnce  sync.Once
	doneMutex sync.Mutex // Protects doneChan recreation

	// Reconnection state
	reconnectAttempts int
	reconnecting      bool
	reconnectMu       sync.Mutex
}

// ConnectionOption configures connection behavior
type ConnectionOption func(*Connection)

// WithPingInterval sets the ping interval
func WithPingInterval(interval time.Duration) ConnectionOption {
	return func(c *Connection) {
		c.pingInterval = interval
	}
}

// WithPongTimeout sets the pong timeout
func WithPongTimeout(timeout time.Duration) ConnectionOption {
	return func(c *Connection) {
		c.pongTimeout = timeout
	}
}

// WithWriteTimeout sets the write timeout
func WithWriteTimeout(timeout time.Duration) ConnectionOption {
	return func(c *Connection) {
		c.writeTimeout = timeout
	}
}

// WithReadTimeout sets the read timeout
func WithReadTimeout(timeout time.Duration) ConnectionOption {
	return func(c *Connection) {
		c.readTimeout = timeout
	}
}

// WithAutoReconnect enables automatic reconnection
func WithAutoReconnect(enable bool) ConnectionOption {
	return func(c *Connection) {
		c.autoReconnect = enable
	}
}

// WithMaxReconnectAttempts sets maximum reconnection attempts
func WithMaxReconnectAttempts(attempts int) ConnectionOption {
	return func(c *Connection) {
		c.maxReconnectAttempts = attempts
	}
}

// WithReconnectInterval sets the base reconnection interval
func WithReconnectInterval(interval time.Duration) ConnectionOption {
	return func(c *Connection) {
		c.reconnectInterval = interval
	}
}

// NewConnection creates a new WebSocket connection
func NewConnection(url string, opts ...ConnectionOption) *Connection {
	conn := &Connection{
		url:                  url,
		state:                StateDisconnected,
		pingInterval:         30 * time.Second,
		pongTimeout:          60 * time.Second,
		writeTimeout:         10 * time.Second,
		readTimeout:          60 * time.Second,
		autoReconnect:        false,
		maxReconnectAttempts: 5,
		reconnectInterval:    5 * time.Second,
		closeChan:            make(chan struct{}),
		doneChan:             make(chan struct{}),
	}

	for _, opt := range opts {
		opt(conn)
	}

	return conn
}

// URL returns the WebSocket URL
func (c *Connection) URL() string {
	return c.url
}

// State returns the current connection state
func (c *Connection) State() ConnectionState {
	c.stateMu.RLock()
	defer c.stateMu.RUnlock()
	return c.state
}

// setState sets the connection state
func (c *Connection) setState(state ConnectionState) {
	c.stateMu.Lock()
	defer c.stateMu.Unlock()
	c.state = state
}

// PingInterval returns the ping interval
func (c *Connection) PingInterval() time.Duration {
	return c.pingInterval
}

// PongTimeout returns the pong timeout
func (c *Connection) PongTimeout() time.Duration {
	return c.pongTimeout
}

// WriteTimeout returns the write timeout
func (c *Connection) WriteTimeout() time.Duration {
	return c.writeTimeout
}

// ReadTimeout returns the read timeout
func (c *Connection) ReadTimeout() time.Duration {
	return c.readTimeout
}

// Connect establishes the WebSocket connection
func (c *Connection) Connect(ctx context.Context) error {
	if c.State() == StateConnected {
		return fmt.Errorf("already connected")
	}

	c.setState(StateConnecting)

	// Reset channels for reconnection
	select {
	case <-c.closeChan:
		c.closeChan = make(chan struct{})
	default:
	}

	// Handle doneChan without resetting sync.Once
	c.doneMutex.Lock()
	select {
	case <-c.doneChan:
		// Create new done channel and reset once for next use
		c.doneChan = make(chan struct{})
		c.doneOnce = sync.Once{}
	default:
	}
	c.doneMutex.Unlock()

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}

	conn, _, err := dialer.DialContext(ctx, c.url, nil)
	if err != nil {
		c.setState(StateDisconnected)
		return fmt.Errorf("failed to connect to %s: %w", c.url, err)
	}

	c.connMu.Lock()
	c.conn = conn
	c.connMu.Unlock()

	// Set up pong handler before starting loops
	conn.SetPongHandler(func(string) error {
		c.pongMu.Lock()
		c.lastPongTime = time.Now()
		c.pongMu.Unlock()
		conn.SetReadDeadline(time.Now().Add(c.readTimeout))
		return nil
	})

	// Initialize pong time
	c.pongMu.Lock()
	c.lastPongTime = time.Now()
	c.pongMu.Unlock()

	// Set initial read deadline
	conn.SetReadDeadline(time.Now().Add(c.readTimeout))

	c.setState(StateConnected)

	// Start background goroutines
	go c.startPingLoop()
	go c.startReadLoop()

	return nil
}

// Send sends a message to the WebSocket
func (c *Connection) Send(ctx context.Context, data []byte) error {
	if c.State() != StateConnected {
		return fmt.Errorf("not connected")
	}

	c.connMu.Lock()
	conn := c.conn
	c.connMu.Unlock()

	if conn == nil {
		return fmt.Errorf("connection is nil")
	}

	// Use write mutex to prevent concurrent writes
	c.writeMu.Lock()
	defer c.writeMu.Unlock()

	// Set write deadline based on context and timeout
	deadline := time.Now().Add(c.writeTimeout)
	if ctxDeadline, ok := ctx.Deadline(); ok && ctxDeadline.Before(deadline) {
		deadline = ctxDeadline
	}
	conn.SetWriteDeadline(deadline)

	// Write message - SetWriteDeadline will handle timeout
	err := conn.WriteMessage(websocket.TextMessage, data)
	if err != nil {
		// Check if context was cancelled
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
			return err
		}
	}
	return nil
}

// Close closes the WebSocket connection
func (c *Connection) Close() error {
	currentState := c.State()
	if currentState == StateClosed {
		return nil
	}

	c.setState(StateClosed)

	// Signal shutdown
	select {
	case <-c.closeChan:
		// Already closed
	default:
		close(c.closeChan)
	}

	// Wait a moment for ongoing operations to complete
	time.Sleep(10 * time.Millisecond)

	c.connMu.Lock()
	conn := c.conn
	c.conn = nil
	c.connMu.Unlock()

	if conn != nil {
		// Send close frame (thread-safe) with timeout protection
		closeCtx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		done := make(chan bool, 1)

		go func() {
			c.writeMu.Lock()
			conn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""))
			c.writeMu.Unlock()
			done <- true
		}()

		select {
		case <-done:
		case <-closeCtx.Done():
			// Timeout, force close
		}
		cancel()

		conn.Close()
	}

	// Wait for goroutines to finish
	select {
	case <-c.doneChan:
	case <-time.After(1 * time.Second):
		// Timeout waiting for graceful shutdown
	}

	return nil
}

// SetMessageHandler sets the message handler function
func (c *Connection) SetMessageHandler(handler func([]byte)) {
	c.handlerMu.Lock()
	defer c.handlerMu.Unlock()
	c.messageHandler = handler
}

// startPingLoop sends periodic ping frames
func (c *Connection) startPingLoop() {
	defer func() {
		c.doneMutex.Lock()
		defer c.doneMutex.Unlock()
		c.doneOnce.Do(func() {
			select {
			case <-c.doneChan:
				// Already closed
			default:
				close(c.doneChan)
			}
		})
	}()

	ticker := time.NewTicker(c.pingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-c.closeChan:
			return
		case <-ticker.C:
			if c.State() != StateConnected {
				return
			}

			c.connMu.Lock()
			conn := c.conn
			c.connMu.Unlock()

			if conn == nil {
				return
			}

			// Check if we haven't received a pong in too long
			c.pongMu.Lock()
			timeSinceLastPong := time.Since(c.lastPongTime)
			c.pongMu.Unlock()

			if timeSinceLastPong > c.pongTimeout {
				c.handleConnectionError(fmt.Errorf("pong timeout: no pong received for %v", timeSinceLastPong))
				return
			}

			// Send ping (thread-safe)
			c.writeMu.Lock()
			conn.SetWriteDeadline(time.Now().Add(c.writeTimeout))
			err := conn.WriteMessage(websocket.PingMessage, nil)
			c.writeMu.Unlock()

			if err != nil {
				c.handleConnectionError(err)
				return
			}

			// If we've successfully sent a ping and the connection seems stable,
			// reset reconnection attempts (connection is considered stable)
			c.reconnectMu.Lock()
			if c.reconnectAttempts > 0 {
				c.reconnectAttempts = 0
				c.reconnecting = false
			}
			c.reconnectMu.Unlock()
		}
	}
}

// startReadLoop reads messages from WebSocket
func (c *Connection) startReadLoop() {
	defer func() {
		c.doneMutex.Lock()
		defer c.doneMutex.Unlock()
		c.doneOnce.Do(func() {
			select {
			case <-c.doneChan:
				// Already closed
			default:
				close(c.doneChan)
			}
		})
	}()

	for {
		select {
		case <-c.closeChan:
			return
		default:
		}

		if c.State() != StateConnected {
			return
		}

		c.connMu.Lock()
		conn := c.conn
		c.connMu.Unlock()

		if conn == nil {
			return
		}

		// Read message
		_, message, err := conn.ReadMessage()
		if err != nil {
			c.handleConnectionError(err)
			return
		}

		// Handle message
		c.handlerMu.RLock()
		handler := c.messageHandler
		c.handlerMu.RUnlock()

		if handler != nil {
			go handler(message)
		}
	}
}

// handleConnectionError handles connection errors and triggers reconnection
func (c *Connection) handleConnectionError(err error) {
	c.reconnectMu.Lock()
	defer c.reconnectMu.Unlock()

	if c.State() == StateClosed {
		return
	}

	// Check if reconnection is already in progress
	if c.reconnecting {
		return
	}

	if c.autoReconnect && c.reconnectAttempts < c.maxReconnectAttempts {
		c.reconnecting = true
		c.setState(StateReconnecting)
		go c.attemptReconnection()
	} else {
		c.setState(StateDisconnected)
	}
}

// attemptReconnection attempts to reconnect with exponential backoff
func (c *Connection) attemptReconnection() {
	defer func() {
		c.reconnectMu.Lock()
		c.reconnecting = false
		c.reconnectMu.Unlock()
	}()

	for {
		c.reconnectMu.Lock()
		if c.reconnectAttempts >= c.maxReconnectAttempts {
			c.reconnectMu.Unlock()
			break
		}
		c.reconnectAttempts++
		attempts := c.reconnectAttempts
		c.reconnectMu.Unlock()

		// Calculate backoff delay
		backoffDelay := c.reconnectInterval * time.Duration(1<<uint(attempts-1))
		maxDelay := 30 * time.Second
		if backoffDelay > maxDelay {
			backoffDelay = maxDelay
		}

		select {
		case <-c.closeChan:
			return
		case <-time.After(backoffDelay):
		}

		// Check if connection was closed during backoff
		if c.State() == StateClosed {
			return
		}

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		err := c.Connect(ctx)
		cancel()

		if err == nil {
			// Connection established - but don't reset attempts yet
			// Let the connection prove it's stable before declaring success
			return
		}

		// Continue loop to try again if we haven't exceeded max attempts
	}

	// All reconnection attempts failed
	c.setState(StateDisconnected)
}
