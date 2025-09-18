package websocket

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"sync/atomic"
	"time"
)

// StreamManager manages WebSocket streams and subscriptions
type StreamManager struct {
	conn               *Connection
	subscriptions      map[string]bool
	subscriptionsMu    sync.RWMutex
	requestID          int64
	pendingRequests    map[int]chan SubscriptionResponse
	pendingRequestsMu  sync.RWMutex

	// Connection state monitoring
	lastState        ConnectionState
	stateMu          sync.RWMutex
	stopMonitoring   chan struct{}
	monitoringActive bool

	// Message handlers
	depthHandler  DepthHandler
	tickerHandler TickerHandler
	userHandler   UserStreamHandler
	eventHandler  EventHandler
	handlersMu    sync.RWMutex
}

// NewStreamManager creates a new stream manager
func NewStreamManager(url string, opts ...ConnectionOption) *StreamManager {
	sm := &StreamManager{
		conn:            NewConnection(url, opts...),
		subscriptions:   make(map[string]bool),
		pendingRequests: make(map[int]chan SubscriptionResponse),
		lastState:       StateDisconnected,
		stopMonitoring:  make(chan struct{}),
	}

	// Set message handler to route incoming messages
	sm.conn.SetMessageHandler(sm.handleMessage)

	return sm
}

// URL returns the WebSocket URL
func (sm *StreamManager) URL() string {
	return sm.conn.URL()
}

// State returns the current connection state
func (sm *StreamManager) State() ConnectionState {
	return sm.conn.State()
}

// Connect establishes the WebSocket connection
func (sm *StreamManager) Connect(ctx context.Context) error {
	err := sm.conn.Connect(ctx)
	if err != nil {
		return err
	}

	// Start state monitoring if not already active
	sm.stateMu.Lock()
	if !sm.monitoringActive {
		sm.monitoringActive = true
		sm.lastState = StateConnected
		go sm.monitorConnectionState()
	}
	sm.stateMu.Unlock()

	// Resubscribe to active streams if any exist
	sm.subscriptionsMu.RLock()
	activeStreams := make([]string, 0, len(sm.subscriptions))
	for stream := range sm.subscriptions {
		activeStreams = append(activeStreams, stream)
	}
	sm.subscriptionsMu.RUnlock()

	if len(activeStreams) > 0 {
		// Clear current subscriptions and resubscribe
		sm.subscriptionsMu.Lock()
		sm.subscriptions = make(map[string]bool)
		sm.subscriptionsMu.Unlock()

		// Resubscribe to all previously active streams
		err = sm.SubscribeMultiple(ctx, activeStreams)
		if err != nil {
			return fmt.Errorf("failed to resubscribe to streams: %w", err)
		}
	}

	return nil
}

// Close closes the WebSocket connection and clears subscriptions
func (sm *StreamManager) Close() error {
	// Stop state monitoring
	sm.stateMu.Lock()
	if sm.monitoringActive {
		select {
		case <-sm.stopMonitoring:
			// Already closed
		default:
			close(sm.stopMonitoring)
		}
		sm.monitoringActive = false
	}
	sm.stateMu.Unlock()

	sm.subscriptionsMu.Lock()
	// Clear all subscriptions
	sm.subscriptions = make(map[string]bool)
	sm.subscriptionsMu.Unlock()

	sm.pendingRequestsMu.Lock()
	// Close all pending request channels
	for _, ch := range sm.pendingRequests {
		select {
		case <-ch:
			// Already closed
		default:
			close(ch)
		}
	}
	sm.pendingRequests = make(map[int]chan SubscriptionResponse)
	sm.pendingRequestsMu.Unlock()

	return sm.conn.Close()
}

// Subscribe subscribes to a single stream
func (sm *StreamManager) Subscribe(ctx context.Context, stream string) error {
	return sm.SubscribeMultiple(ctx, []string{stream})
}

// SubscribeMultiple subscribes to multiple streams
func (sm *StreamManager) SubscribeMultiple(ctx context.Context, streams []string) error {
	if sm.State() != StateConnected {
		return fmt.Errorf("not connected")
	}

	// Create subscription request
	requestID := int(atomic.AddInt64(&sm.requestID, 1))
	request := SubscriptionRequest{
		Method: "SUBSCRIBE",
		Params: streams,
		ID:     requestID,
	}

	// Create response channel
	responseChan := make(chan SubscriptionResponse, 1)
	sm.pendingRequestsMu.Lock()
	sm.pendingRequests[requestID] = responseChan
	sm.pendingRequestsMu.Unlock()

	// Send subscription request
	requestData, err := json.Marshal(request)
	if err != nil {
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return fmt.Errorf("failed to marshal subscription request: %w", err)
	}

	err = sm.conn.Send(ctx, requestData)
	if err != nil {
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return fmt.Errorf("failed to send subscription request: %w", err)
	}

	// Wait for response
	select {
	case response := <-responseChan:
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()

		if response.Error != nil {
			return fmt.Errorf("subscription failed: [%d] %s", response.Error.Code, response.Error.Msg)
		}

		// Mark streams as subscribed
		sm.subscriptionsMu.Lock()
		for _, stream := range streams {
			sm.subscriptions[stream] = true
		}
		sm.subscriptionsMu.Unlock()

		return nil
	case <-ctx.Done():
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return ctx.Err()
	}
}

// Unsubscribe unsubscribes from a stream
func (sm *StreamManager) Unsubscribe(ctx context.Context, stream string) error {
	return sm.UnsubscribeMultiple(ctx, []string{stream})
}

// UnsubscribeMultiple unsubscribes from multiple streams
func (sm *StreamManager) UnsubscribeMultiple(ctx context.Context, streams []string) error {
	if sm.State() != StateConnected {
		return fmt.Errorf("not connected")
	}

	// Filter to only unsubscribe from streams we're actually subscribed to
	sm.subscriptionsMu.RLock()
	subscribedStreams := make([]string, 0, len(streams))
	for _, stream := range streams {
		if sm.subscriptions[stream] {
			subscribedStreams = append(subscribedStreams, stream)
		}
	}
	sm.subscriptionsMu.RUnlock()

	if len(subscribedStreams) == 0 {
		return nil // Nothing to unsubscribe from
	}

	// Create unsubscription request
	requestID := int(atomic.AddInt64(&sm.requestID, 1))
	request := SubscriptionRequest{
		Method: "UNSUBSCRIBE",
		Params: subscribedStreams,
		ID:     requestID,
	}

	// Create response channel
	responseChan := make(chan SubscriptionResponse, 1)
	sm.pendingRequestsMu.Lock()
	sm.pendingRequests[requestID] = responseChan
	sm.pendingRequestsMu.Unlock()

	// Send unsubscription request
	requestData, err := json.Marshal(request)
	if err != nil {
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return fmt.Errorf("failed to marshal unsubscription request: %w", err)
	}

	err = sm.conn.Send(ctx, requestData)
	if err != nil {
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return fmt.Errorf("failed to send unsubscription request: %w", err)
	}

	// Wait for response
	select {
	case response := <-responseChan:
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()

		if response.Error != nil {
			return fmt.Errorf("unsubscription failed: [%d] %s", response.Error.Code, response.Error.Msg)
		}

		// Remove streams from subscriptions
		sm.subscriptionsMu.Lock()
		for _, stream := range subscribedStreams {
			delete(sm.subscriptions, stream)
		}
		sm.subscriptionsMu.Unlock()

		return nil
	case <-ctx.Done():
		sm.pendingRequestsMu.Lock()
		delete(sm.pendingRequests, requestID)
		sm.pendingRequestsMu.Unlock()
		return ctx.Err()
	}
}

// ActiveSubscriptions returns a copy of currently active subscriptions
func (sm *StreamManager) ActiveSubscriptions() []string {
	sm.subscriptionsMu.RLock()
	defer sm.subscriptionsMu.RUnlock()

	subscriptions := make([]string, 0, len(sm.subscriptions))
	for stream := range sm.subscriptions {
		subscriptions = append(subscriptions, stream)
	}

	return subscriptions
}

// SetDepthHandler sets the depth update handler
func (sm *StreamManager) SetDepthHandler(handler DepthHandler) {
	sm.handlersMu.Lock()
	defer sm.handlersMu.Unlock()
	sm.depthHandler = handler
}

// SetTickerHandler sets the ticker update handler
func (sm *StreamManager) SetTickerHandler(handler TickerHandler) {
	sm.handlersMu.Lock()
	defer sm.handlersMu.Unlock()
	sm.tickerHandler = handler
}

// SetUserStreamHandler sets the user stream handler
func (sm *StreamManager) SetUserStreamHandler(handler UserStreamHandler) {
	sm.handlersMu.Lock()
	defer sm.handlersMu.Unlock()
	sm.userHandler = handler
}

// SetEventHandler sets the generic event handler
func (sm *StreamManager) SetEventHandler(handler EventHandler) {
	sm.handlersMu.Lock()
	defer sm.handlersMu.Unlock()
	sm.eventHandler = handler
}

// handleMessage processes incoming WebSocket messages
func (sm *StreamManager) handleMessage(data []byte) {
	// First, try to parse as a subscription response
	var subResponse SubscriptionResponse
	if err := json.Unmarshal(data, &subResponse); err == nil && subResponse.ID != 0 {
		// This is a subscription response
		sm.pendingRequestsMu.RLock()
		if responseChan, exists := sm.pendingRequests[subResponse.ID]; exists {
			select {
			case responseChan <- subResponse:
			default:
				// Channel is full or closed
			}
		}
		sm.pendingRequestsMu.RUnlock()
		return
	}

	// Try to parse as a stream message
	var streamMsg StreamMessage
	if err := json.Unmarshal(data, &streamMsg); err != nil {
		// Malformed message, ignore
		return
	}

	// Route message based on stream type
	sm.routeStreamMessage(&streamMsg)
}

// routeStreamMessage routes stream messages to appropriate handlers
func (sm *StreamManager) routeStreamMessage(msg *StreamMessage) {
	sm.handlersMu.RLock()
	defer sm.handlersMu.RUnlock()

	// Parse the event type from the data
	var eventData map[string]interface{}
	if err := json.Unmarshal(msg.Data, &eventData); err != nil {
		return
	}

	eventType, ok := eventData["e"].(string)
	if !ok {
		return
	}

	// Route based on event type
	switch eventType {
	case "depthUpdate":
		if sm.depthHandler != nil {
			var event DepthUpdateEvent
			if err := json.Unmarshal(msg.Data, &event); err == nil {
				sm.depthHandler.HandleDepthUpdate(&event)
			}
		}
	case "24hrTicker":
		if sm.tickerHandler != nil {
			var event TickerEvent
			if err := json.Unmarshal(msg.Data, &event); err == nil {
				sm.tickerHandler.HandleTickerUpdate(&event)
			}
		}
	case "outboundAccountPosition", "outboundAccountInfo":
		if sm.userHandler != nil {
			var event AccountUpdateEvent
			if err := json.Unmarshal(msg.Data, &event); err == nil {
				sm.userHandler.HandleAccountUpdate(&event)
			}
		}
	case "executionReport":
		if sm.userHandler != nil {
			var event OrderUpdateEvent
			if err := json.Unmarshal(msg.Data, &event); err == nil {
				sm.userHandler.HandleOrderUpdate(&event)
			}
		}
	case "listenKeyExpired":
		if sm.userHandler != nil {
			sm.userHandler.HandleListenKeyExpired()
		}
	default:
		// Use generic event handler for unknown event types
		if sm.eventHandler != nil {
			sm.eventHandler.HandleEvent(eventType, msg.Data)
		}
	}
}

// monitorConnectionState monitors connection state changes and triggers resubscription
func (sm *StreamManager) monitorConnectionState() {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-sm.stopMonitoring:
			return
		case <-ticker.C:
			currentState := sm.conn.State()

			sm.stateMu.Lock()
			lastState := sm.lastState
			sm.lastState = currentState
			sm.stateMu.Unlock()

			// Check if we've reconnected (transition from non-connected to connected)
			if lastState != StateConnected && currentState == StateConnected {
				sm.handleReconnection()
			}
		}
	}
}

// handleReconnection handles automatic resubscription after reconnection
func (sm *StreamManager) handleReconnection() {
	sm.subscriptionsMu.RLock()
	activeStreams := make([]string, 0, len(sm.subscriptions))
	for stream := range sm.subscriptions {
		activeStreams = append(activeStreams, stream)
	}
	sm.subscriptionsMu.RUnlock()

	if len(activeStreams) > 0 {
		// Clear current subscriptions and resubscribe
		sm.subscriptionsMu.Lock()
		sm.subscriptions = make(map[string]bool)
		sm.subscriptionsMu.Unlock()

		// Resubscribe to all previously active streams
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		sm.SubscribeMultiple(ctx, activeStreams)
	}
}