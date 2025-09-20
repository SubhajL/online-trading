package models

import (
	"fmt"
	"strings"
)

// CreateStreamRequest represents a request to create a new WebSocket stream
type CreateStreamRequest struct {
	Type          string   `json:"type" binding:"required,oneof=public user"`
	Subscriptions []string `json:"subscriptions,omitempty"` // For public streams
	AutoReconnect bool     `json:"auto_reconnect"`
	MaxReconnect  int      `json:"max_reconnect_attempts"`
}

// Validate validates the create stream request
func (r *CreateStreamRequest) Validate() error {
	if r.Type == "" {
		return fmt.Errorf("type is required")
	}
	if r.Type != "public" && r.Type != "user" {
		return fmt.Errorf("type must be 'public' or 'user'")
	}
	return nil
}

// SubscribeRequest represents a request to subscribe to market data streams
type SubscribeRequest struct {
	Symbol  string   `json:"symbol" binding:"required"`
	Streams []string `json:"streams" binding:"required,dive,oneof=depth ticker trades"`
}

// Validate validates the subscribe request
func (r *SubscribeRequest) Validate() error {
	if r.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if len(r.Streams) == 0 {
		return fmt.Errorf("at least one stream is required")
	}

	validStreams := map[string]bool{
		"depth":  true,
		"ticker": true,
		"trades": true,
	}

	for _, stream := range r.Streams {
		if !validStreams[stream] {
			return fmt.Errorf("invalid stream type: %s", stream)
		}
	}

	return nil
}

// Normalize normalizes the request data
func (r *SubscribeRequest) Normalize() {
	r.Symbol = strings.ToUpper(r.Symbol)
}

// UserDataRequest represents a request to subscribe to user data stream
type UserDataRequest struct {
	ListenKey string `json:"listen_key" binding:"required"`
}

// Validate validates the user data request
func (r *UserDataRequest) Validate() error {
	if r.ListenKey == "" {
		return fmt.Errorf("listen_key is required")
	}
	return nil
}

// UnsubscribeRequest represents a request to unsubscribe from streams
type UnsubscribeRequest struct {
	Symbol   string   `json:"symbol,omitempty"`
	Streams  []string `json:"streams,omitempty"`
	StreamID string   `json:"stream_id,omitempty"`
}

// Validate validates the unsubscribe request
func (r *UnsubscribeRequest) Validate() error {
	// Must have either (Symbol + Streams) OR StreamID
	hasSymbolStreams := r.Symbol != "" && len(r.Streams) > 0
	hasStreamID := r.StreamID != ""

	if !hasSymbolStreams && !hasStreamID {
		return fmt.Errorf("either symbol with streams or stream_id is required")
	}

	if hasSymbolStreams && hasStreamID {
		return fmt.Errorf("cannot specify both symbol/streams and stream_id")
	}

	if hasSymbolStreams {
		validStreams := map[string]bool{
			"depth":  true,
			"ticker": true,
			"trades": true,
		}

		for _, stream := range r.Streams {
			if !validStreams[stream] {
				return fmt.Errorf("invalid stream type: %s", stream)
			}
		}
	}

	return nil
}

// ConfigUpdateRequest represents a request to update configuration
type ConfigUpdateRequest struct {
	RateLimit      *int `json:"rate_limit,omitempty"`
	MaxConnections *int `json:"max_connections,omitempty"`
}

// Validate validates the configuration update request
func (r *ConfigUpdateRequest) Validate() error {
	if r.RateLimit != nil && *r.RateLimit <= 0 {
		return fmt.Errorf("rate limit must be positive")
	}
	if r.MaxConnections != nil && *r.MaxConnections <= 0 {
		return fmt.Errorf("max connections must be positive")
	}
	return nil
}
