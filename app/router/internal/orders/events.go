package orders

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/rs/zerolog"
)

// HTTPEventEmitter emits events via HTTP POST
type HTTPEventEmitter struct {
	url    string
	client *http.Client
}

// NewHTTPEventEmitter creates a new HTTP event emitter
func NewHTTPEventEmitter(url string) *HTTPEventEmitter {
	return &HTTPEventEmitter{
		url: url,
		client: &http.Client{
			Timeout: 5 * time.Second,
		},
	}
}

// EmitOrderUpdate emits an order update event
func (e *HTTPEventEmitter) EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error {
	if e.url == "" {
		// No URL configured, skip emission
		return nil
	}

	// Marshal update to JSON
	data, err := json.Marshal(update)
	if err != nil {
		return fmt.Errorf("failed to marshal order update: %w", err)
	}

	// Create request
	req, err := http.NewRequestWithContext(ctx, "POST", e.url, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	// Send request
	resp, err := e.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to send order update: %w", err)
	}
	defer resp.Body.Close()

	// Check response
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	return nil
}

// LogEventEmitter logs events for debugging
type LogEventEmitter struct {
	logger zerolog.Logger
}

// NewLogEventEmitter creates a new log event emitter
func NewLogEventEmitter(logger zerolog.Logger) *LogEventEmitter {
	return &LogEventEmitter{logger: logger}
}

// EmitOrderUpdate logs order updates
func (e *LogEventEmitter) EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error {
	e.logger.Info().
		Str("event_type", update.EventType).
		Str("symbol", update.Symbol).
		Int64("order_id", update.OrderID).
		Str("client_order_id", update.ClientOrderID).
		Str("status", update.Status).
		Str("side", update.Side).
		Str("order_type", update.OrderType).
		Str("price", update.Price.String()).
		Str("quantity", update.Quantity.String()).
		Str("executed_qty", update.ExecutedQty.String()).
		Time("update_time", update.UpdateTime).
		Str("reason", update.Reason).
		Msg("Order update event")
	return nil
}