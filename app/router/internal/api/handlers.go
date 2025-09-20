package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"router/internal/orders"
)

// OrderManager defines the interface for order management
type OrderManager interface {
	PlaceBracketOrder(ctx context.Context, req *orders.PlaceBracketRequest) (*orders.PlaceBracketResponse, error)
	CancelOrder(ctx context.Context, req *orders.CancelRequest) error
	CloseAllPositions(ctx context.Context, req *orders.CloseAllRequest) error
	ReconcileOrder(ctx context.Context, clientOrderID string) error
}

// Handlers contains all HTTP handlers
type Handlers struct {
	orderManager OrderManager
	logger       zerolog.Logger
}

// NewHandlers creates new handlers instance
func NewHandlers(orderManager OrderManager, logger zerolog.Logger) *Handlers {
	return &Handlers{
		orderManager: orderManager,
		logger:       logger,
	}
}

// PlaceBracketHandler handles POST /place_bracket
func (h *Handlers) PlaceBracketHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	if r.Method != http.MethodPost {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Invalid method for place_bracket")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	var req orders.PlaceBracketRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.logger.Error().
			Err(err).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Failed to decode request body")
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	// Set default order type if not provided
	if req.OrderType == "" {
		if req.EntryPrice.IsZero() {
			req.OrderType = "MARKET"
		} else {
			req.OrderType = "LIMIT"
		}
	}

	// Log the bracket order request details
	h.logger.Info().
		Str("symbol", req.Symbol).
		Str("side", req.Side).
		Str("order_type", req.OrderType).
		Str("quantity", req.Quantity.String()).
		Str("entry_price", req.EntryPrice.String()).
		Int("tp_count", len(req.TakeProfitPrices)).
		Str("sl_price", req.StopLossPrice.String()).
		Bool("is_futures", req.IsFutures).
		Msg("Processing bracket order request")

	resp, err := h.orderManager.PlaceBracketOrder(r.Context(), &req)
	if err != nil {
		h.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("side", req.Side).
			Dur("duration", time.Since(start)).
			Msg("Failed to place bracket order")
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	h.logger.Info().
		Str("bracket_id", resp.BracketOrderID).
		Str("symbol", resp.Symbol).
		Str("side", resp.Side).
		Dur("duration", time.Since(start)).
		Msg("Bracket order placed successfully")

	writeJSON(w, http.StatusOK, resp)
}

// CancelHandler handles POST /cancel
func (h *Handlers) CancelHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	if r.Method != http.MethodPost {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Invalid method for cancel")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	var req orders.CancelRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.logger.Error().
			Err(err).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Failed to decode cancel request")
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	h.logger.Info().
		Str("symbol", req.Symbol).
		Int64("order_id", req.OrderID).
		Str("client_order_id", req.ClientOrderID).
		Msg("Processing cancel order request")

	if err := h.orderManager.CancelOrder(r.Context(), &req); err != nil {
		h.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Int64("order_id", req.OrderID).
			Dur("duration", time.Since(start)).
			Msg("Failed to cancel order")
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	h.logger.Info().
		Str("symbol", req.Symbol).
		Int64("order_id", req.OrderID).
		Dur("duration", time.Since(start)).
		Msg("Order canceled successfully")

	writeJSON(w, http.StatusOK, map[string]string{"status": "success"})
}

// CloseAllHandler handles POST /close_all
func (h *Handlers) CloseAllHandler(w http.ResponseWriter, r *http.Request) {
	start := time.Now()

	if r.Method != http.MethodPost {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Invalid method for close_all")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	var req orders.CloseAllRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.logger.Error().
			Err(err).
			Str("path", r.URL.Path).
			Str("remote_addr", r.RemoteAddr).
			Msg("Failed to decode close all request")
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return
	}

	h.logger.Info().
		Str("symbol", req.Symbol).
		Bool("is_futures", req.IsFutures).
		Msg("Processing close all positions request")

	if err := h.orderManager.CloseAllPositions(r.Context(), &req); err != nil {
		h.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Bool("is_futures", req.IsFutures).
			Dur("duration", time.Since(start)).
			Msg("Failed to close all positions")
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	h.logger.Info().
		Str("symbol", req.Symbol).
		Bool("is_futures", req.IsFutures).
		Dur("duration", time.Since(start)).
		Msg("All positions closed successfully")

	writeJSON(w, http.StatusOK, map[string]string{"status": "success"})
}

// HealthzHandler handles GET /healthz
func (h *Handlers) HealthzHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Msg("Invalid method for healthz")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Debug level logging for health checks to avoid spam
	h.logger.Debug().
		Str("path", r.URL.Path).
		Str("remote_addr", r.RemoteAddr).
		Msg("Health check requested")

	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "healthy",
		"service": "order-router",
	})
}

// ReadyzHandler handles GET /readyz
func (h *Handlers) ReadyzHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Msg("Invalid method for readyz")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Debug level logging for readiness checks to avoid spam
	h.logger.Debug().
		Str("path", r.URL.Path).
		Str("remote_addr", r.RemoteAddr).
		Msg("Readiness check requested")

	// TODO: Check actual readiness (Binance connectivity, etc.)
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ready",
		"service": "order-router",
	})
}

// Helper functions

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}

// ParseDecimalArray parses an array of decimal strings
func ParseDecimalArray(values []interface{}) ([]decimal.Decimal, error) {
	result := make([]decimal.Decimal, 0, len(values))
	for _, v := range values {
		str, ok := v.(string)
		if !ok {
			// Try float64
			if f, ok := v.(float64); ok {
				str = decimal.NewFromFloat(f).String()
			} else {
				continue
			}
		}
		d, err := decimal.NewFromString(str)
		if err != nil {
			return nil, err
		}
		result = append(result, d)
	}
	return result, nil
}
