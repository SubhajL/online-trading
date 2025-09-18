package websocket

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"
)

// DefaultBaseURL is the default Binance WebSocket base URL
const DefaultBaseURL = "wss://stream.binance.com:9443"

// Client provides a high-level interface for Binance WebSocket streams
type Client struct {
	baseURL     string
	streamMgr   *StreamManager
	connections map[string]*StreamManager // Multiple connections for different stream types
	connMu      sync.RWMutex

	// Connection options to pass to stream managers
	connOpts []ConnectionOption

	// Subscription handlers
	depthHandlers  map[string]func(*DepthUpdateEvent) error
	tickerHandlers map[string]func(*TickerEvent) error
	userHandlers   map[string]*UserDataHandler
	handlersMu     sync.RWMutex
}

// ClientOption configures the client
type ClientOption func(*Client)

// WithBaseURL sets the base WebSocket URL
func WithBaseURL(url string) ClientOption {
	return func(c *Client) {
		c.baseURL = url
	}
}

// Client option functions that forward to connection options

// WithAutoReconnectClient enables automatic reconnection for client
func WithAutoReconnectClient(enable bool) ClientOption {
	return func(c *Client) {
		if enable {
			c.connOpts = append(c.connOpts, WithAutoReconnect(true))
		} else {
			c.connOpts = append(c.connOpts, WithAutoReconnect(false))
		}
	}
}

// WithMaxReconnectAttemptsClient sets maximum reconnection attempts for client
func WithMaxReconnectAttemptsClient(attempts int) ClientOption {
	return func(c *Client) {
		c.connOpts = append(c.connOpts, WithMaxReconnectAttempts(attempts))
	}
}

// WithReconnectIntervalClient sets the reconnection interval for client
func WithReconnectIntervalClient(interval time.Duration) ClientOption {
	return func(c *Client) {
		c.connOpts = append(c.connOpts, WithReconnectInterval(interval))
	}
}

// UserDataHandler handles user data stream events
type UserDataHandler struct {
	OnAccountUpdate      func(*AccountUpdateEvent) error
	OnOrderUpdate        func(*OrderUpdateEvent) error
	OnListenKeyExpired   func() error
}

// HandleAccountUpdate implements UserStreamHandler
func (h *UserDataHandler) HandleAccountUpdate(event *AccountUpdateEvent) error {
	if h.OnAccountUpdate != nil {
		return h.OnAccountUpdate(event)
	}
	return nil
}

// HandleOrderUpdate implements UserStreamHandler
func (h *UserDataHandler) HandleOrderUpdate(event *OrderUpdateEvent) error {
	if h.OnOrderUpdate != nil {
		return h.OnOrderUpdate(event)
	}
	return nil
}

// HandleListenKeyExpired implements UserStreamHandler
func (h *UserDataHandler) HandleListenKeyExpired() error {
	if h.OnListenKeyExpired != nil {
		return h.OnListenKeyExpired()
	}
	return nil
}

// NewClient creates a new WebSocket client
func NewClient(opts ...ClientOption) *Client {
	client := &Client{
		baseURL:        DefaultBaseURL,
		connections:    make(map[string]*StreamManager),
		depthHandlers:  make(map[string]func(*DepthUpdateEvent) error),
		tickerHandlers: make(map[string]func(*TickerEvent) error),
		userHandlers:   make(map[string]*UserDataHandler),
	}

	for _, opt := range opts {
		opt(client)
	}

	return client
}

// BaseURL returns the base WebSocket URL
func (c *Client) BaseURL() string {
	return c.baseURL
}

// State returns the connection state of the main stream manager
func (c *Client) State() ConnectionState {
	c.connMu.RLock()
	defer c.connMu.RUnlock()

	if c.streamMgr == nil {
		return StateDisconnected
	}
	return c.streamMgr.State()
}

// Connect establishes the main WebSocket connection
func (c *Client) Connect(ctx context.Context, opts ...ConnectionOption) error {
	c.connMu.Lock()
	defer c.connMu.Unlock()

	if c.streamMgr == nil {
		// Create main stream manager for public streams
		url := c.baseURL + "/ws/stream"
		// Combine client options with any additional options passed to Connect
		allOpts := append(c.connOpts, opts...)
		c.streamMgr = NewStreamManager(url, allOpts...)
	}

	return c.streamMgr.Connect(ctx)
}

// Close closes all connections and cleans up resources
func (c *Client) Close() error {
	c.connMu.Lock()
	defer c.connMu.Unlock()

	var errs []error

	// Close main stream manager
	if c.streamMgr != nil {
		if err := c.streamMgr.Close(); err != nil {
			errs = append(errs, err)
		}
		c.streamMgr = nil
	}

	// Close all additional connections
	for key, mgr := range c.connections {
		if err := mgr.Close(); err != nil {
			errs = append(errs, fmt.Errorf("failed to close connection %s: %w", key, err))
		}
		delete(c.connections, key)
	}

	// Clear handlers
	c.handlersMu.Lock()
	c.depthHandlers = make(map[string]func(*DepthUpdateEvent) error)
	c.tickerHandlers = make(map[string]func(*TickerEvent) error)
	c.userHandlers = make(map[string]*UserDataHandler)
	c.handlersMu.Unlock()

	if len(errs) > 0 {
		return fmt.Errorf("errors during close: %v", errs)
	}
	return nil
}

// ActiveSubscriptions returns all active subscriptions across all connections
func (c *Client) ActiveSubscriptions() []string {
	c.connMu.RLock()
	defer c.connMu.RUnlock()

	var subscriptions []string

	if c.streamMgr != nil {
		subscriptions = append(subscriptions, c.streamMgr.ActiveSubscriptions()...)
	}

	for _, mgr := range c.connections {
		subscriptions = append(subscriptions, mgr.ActiveSubscriptions()...)
	}

	return subscriptions
}

// SubscribeToDepth subscribes to order book depth updates for a symbol
func (c *Client) SubscribeToDepth(ctx context.Context, symbol string, handler func(*DepthUpdateEvent) error) error {
	if c.streamMgr == nil {
		return fmt.Errorf("not connected")
	}

	// Normalize symbol to lowercase
	symbol = strings.ToLower(symbol)
	stream := symbol + "@depth"

	// Store handler
	c.handlersMu.Lock()
	c.depthHandlers[symbol] = handler
	c.handlersMu.Unlock()

	// Set up routing handler if not already set
	c.streamMgr.SetDepthHandler(&clientDepthHandler{client: c})

	return c.streamMgr.Subscribe(ctx, stream)
}

// SubscribeToTicker subscribes to 24hr ticker statistics for a symbol
func (c *Client) SubscribeToTicker(ctx context.Context, symbol string, handler func(*TickerEvent) error) error {
	if c.streamMgr == nil {
		return fmt.Errorf("not connected")
	}

	// Normalize symbol to lowercase
	symbol = strings.ToLower(symbol)
	stream := symbol + "@ticker"

	// Store handler
	c.handlersMu.Lock()
	c.tickerHandlers[symbol] = handler
	c.handlersMu.Unlock()

	// Set up routing handler if not already set
	c.streamMgr.SetTickerHandler(&clientTickerHandler{client: c})

	return c.streamMgr.Subscribe(ctx, stream)
}

// SubscribeToUserData subscribes to user data stream using a listen key
func (c *Client) SubscribeToUserData(ctx context.Context, listenKey string, handler *UserDataHandler) error {
	// Create a separate connection for user data
	c.connMu.Lock()
	userMgr, exists := c.connections[listenKey]
	if !exists {
		url := c.baseURL + "/ws/" + listenKey
		userMgr = NewStreamManager(url, c.connOpts...)
		c.connections[listenKey] = userMgr
	}
	c.connMu.Unlock()

	// Store handler
	c.handlersMu.Lock()
	c.userHandlers[listenKey] = handler
	c.handlersMu.Unlock()

	// Set up routing handler
	userMgr.SetUserStreamHandler(&clientUserStreamHandler{
		client:    c,
		listenKey: listenKey,
	})

	// Connect if not already connected
	if userMgr.State() != StateConnected {
		if err := userMgr.Connect(ctx); err != nil {
			return fmt.Errorf("failed to connect to user data stream: %w", err)
		}
	}

	return nil
}

// UnsubscribeFromDepth unsubscribes from depth updates for a symbol
func (c *Client) UnsubscribeFromDepth(ctx context.Context, symbol string) error {
	if c.streamMgr == nil {
		return fmt.Errorf("not connected")
	}

	// Normalize symbol to lowercase
	symbol = strings.ToLower(symbol)
	stream := symbol + "@depth"

	// Remove handler
	c.handlersMu.Lock()
	delete(c.depthHandlers, symbol)
	c.handlersMu.Unlock()

	return c.streamMgr.Unsubscribe(ctx, stream)
}

// UnsubscribeFromTicker unsubscribes from ticker updates for a symbol
func (c *Client) UnsubscribeFromTicker(ctx context.Context, symbol string) error {
	if c.streamMgr == nil {
		return fmt.Errorf("not connected")
	}

	// Normalize symbol to lowercase
	symbol = strings.ToLower(symbol)
	stream := symbol + "@ticker"

	// Remove handler
	c.handlersMu.Lock()
	delete(c.tickerHandlers, symbol)
	c.handlersMu.Unlock()

	return c.streamMgr.Unsubscribe(ctx, stream)
}

// UnsubscribeFromUserData unsubscribes from user data stream
func (c *Client) UnsubscribeFromUserData(ctx context.Context, listenKey string) error {
	c.connMu.Lock()
	userMgr, exists := c.connections[listenKey]
	if exists {
		delete(c.connections, listenKey)
	}
	c.connMu.Unlock()

	// Remove handler
	c.handlersMu.Lock()
	delete(c.userHandlers, listenKey)
	c.handlersMu.Unlock()

	if exists {
		return userMgr.Close()
	}
	return nil
}

// Handler implementations for routing events to user-provided handlers

type clientDepthHandler struct {
	client *Client
}

func (h *clientDepthHandler) HandleDepthUpdate(event *DepthUpdateEvent) error {
	h.client.handlersMu.RLock()
	handler, exists := h.client.depthHandlers[strings.ToLower(event.Symbol)]
	h.client.handlersMu.RUnlock()

	if exists && handler != nil {
		return handler(event)
	}
	return nil
}

type clientTickerHandler struct {
	client *Client
}

func (h *clientTickerHandler) HandleTickerUpdate(event *TickerEvent) error {
	h.client.handlersMu.RLock()
	handler, exists := h.client.tickerHandlers[strings.ToLower(event.Symbol)]
	h.client.handlersMu.RUnlock()

	if exists && handler != nil {
		return handler(event)
	}
	return nil
}

type clientUserStreamHandler struct {
	client    *Client
	listenKey string
}

func (h *clientUserStreamHandler) HandleAccountUpdate(event *AccountUpdateEvent) error {
	h.client.handlersMu.RLock()
	handler, exists := h.client.userHandlers[h.listenKey]
	h.client.handlersMu.RUnlock()

	if exists && handler != nil {
		return handler.HandleAccountUpdate(event)
	}
	return nil
}

func (h *clientUserStreamHandler) HandleOrderUpdate(event *OrderUpdateEvent) error {
	h.client.handlersMu.RLock()
	handler, exists := h.client.userHandlers[h.listenKey]
	h.client.handlersMu.RUnlock()

	if exists && handler != nil {
		return handler.HandleOrderUpdate(event)
	}
	return nil
}

func (h *clientUserStreamHandler) HandleListenKeyExpired() error {
	h.client.handlersMu.RLock()
	handler, exists := h.client.userHandlers[h.listenKey]
	h.client.handlersMu.RUnlock()

	if exists && handler != nil {
		return handler.HandleListenKeyExpired()
	}
	return nil
}