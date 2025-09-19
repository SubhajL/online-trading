package orders

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"router/internal/binance"
)

// Manager manages order lifecycle with idempotency
type Manager struct {
	spotClient    *binance.Client
	futuresClient *binance.Client

	// Order tracking
	orders      map[string]*BracketOrder // bracket order ID -> order
	ordersByClient map[string]string       // client order ID -> bracket order ID
	mu          sync.RWMutex

	// Event emitter
	eventEmitter EventEmitter

	// Logger
	logger zerolog.Logger
}

// EventEmitter defines interface for emitting order events
type EventEmitter interface {
	EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error
}

// NewManager creates a new order manager
func NewManager(spotClient, futuresClient *binance.Client, eventEmitter EventEmitter, logger zerolog.Logger) *Manager {
	return &Manager{
		spotClient:     spotClient,
		futuresClient:  futuresClient,
		orders:         make(map[string]*BracketOrder),
		ordersByClient: make(map[string]string),
		eventEmitter:   eventEmitter,
		logger:         logger,
	}
}

// PlaceBracketOrder places a bracket order with idempotency
func (m *Manager) PlaceBracketOrder(ctx context.Context, req *PlaceBracketRequest) (*PlaceBracketResponse, error) {
	// Validate request
	if err := m.validateBracketRequest(req); err != nil {
		return nil, fmt.Errorf("invalid bracket request: %w", err)
	}

	// Select client
	client := m.spotClient
	orderType := OrderTypeSpot
	if req.IsFutures {
		client = m.futuresClient
		orderType = OrderTypeFutures
	}

	// Round prices and quantities
	roundedQty, err := client.RoundQuantity(ctx, req.Symbol, req.Quantity)
	if err != nil {
		return nil, fmt.Errorf("failed to round quantity: %w", err)
	}
	req.Quantity = roundedQty

	if !req.EntryPrice.IsZero() {
		roundedPrice, err := client.RoundPrice(ctx, req.Symbol, req.EntryPrice)
		if err != nil {
			return nil, fmt.Errorf("failed to round entry price: %w", err)
		}
		req.EntryPrice = roundedPrice
	}

	// Round TP prices
	for i, tp := range req.TakeProfitPrices {
		rounded, err := client.RoundPrice(ctx, req.Symbol, tp)
		if err != nil {
			return nil, fmt.Errorf("failed to round TP price %d: %w", i, err)
		}
		req.TakeProfitPrices[i] = rounded
	}

	// Round SL price
	roundedSL, err := client.RoundPrice(ctx, req.Symbol, req.StopLossPrice)
	if err != nil {
		return nil, fmt.Errorf("failed to round SL price: %w", err)
	}
	req.StopLossPrice = roundedSL

	// Validate notional
	if err := client.ValidateNotional(ctx, req.Symbol, req.EntryPrice, req.Quantity); err != nil {
		return nil, fmt.Errorf("notional validation failed: %w", err)
	}

	// Generate bracket order ID
	bracketID := uuid.New().String()

	// Create bracket order
	bracket := &BracketOrder{
		ID:               bracketID,
		Symbol:           req.Symbol,
		Type:             orderType,
		Side:             req.Side,
		Quantity:         req.Quantity,
		EntryPrice:       req.EntryPrice,
		TakeProfitPrices: req.TakeProfitPrices,
		StopLossPrice:    req.StopLossPrice,
		CreatedAt:        time.Now(),
		UpdatedAt:        time.Now(),
	}

	// Place the bracket orders
	response := &PlaceBracketResponse{
		BracketOrderID: bracketID,
		Symbol:         req.Symbol,
		Side:           req.Side,
		Quantity:       req.Quantity,
		CreatedAt:      bracket.CreatedAt,
	}

	if req.IsFutures {
		bracket.ClientOrderIDs, err = m.placeFuturesBracket(ctx, client, req, bracketID)
	} else {
		bracket.ClientOrderIDs, err = m.placeSpotBracket(ctx, client, req, bracketID)
	}

	response.ClientOrderIDs = bracket.ClientOrderIDs

	// Handle bracket order errors
	if err != nil {
		if bracketErr, ok := err.(*BracketOrderError); ok {
			// Check if main order failed (critical error)
			if bracketErr.HasCriticalError() {
				return nil, fmt.Errorf("failed to place bracket order: %w", err)
			}
			// Main order succeeded but some orders failed
			response.PartialFailure = true
			for _, orderErr := range bracketErr.Errors {
				response.Errors = append(response.Errors, fmt.Sprintf("%s: %v", orderErr.OrderType, orderErr.Error))
			}
		} else {
			// Non-bracket error
			return nil, fmt.Errorf("failed to place bracket order: %w", err)
		}
	}

	// Store order (only store successfully placed order IDs)
	m.mu.Lock()
	m.orders[bracketID] = bracket
	if bracket.ClientOrderIDs.Main != "" {
		m.ordersByClient[bracket.ClientOrderIDs.Main] = bracketID
	}
	for _, tpID := range bracket.ClientOrderIDs.TakeProfits {
		if tpID != "" {
			m.ordersByClient[tpID] = bracketID
		}
	}
	if bracket.ClientOrderIDs.StopLoss != "" {
		m.ordersByClient[bracket.ClientOrderIDs.StopLoss] = bracketID
	}
	m.mu.Unlock()

	// Emit order update
	if m.eventEmitter != nil {
		update := &OrderUpdate{
			EventType:     "order_update.v1",
			Symbol:        req.Symbol,
			ClientOrderID: bracket.ClientOrderIDs.Main,
			Status:        "NEW",
			Side:          req.Side,
			OrderType:     req.OrderType,
			Price:         req.EntryPrice,
			Quantity:      req.Quantity,
			ExecutedQty:   decimal.Zero,
			UpdateTime:    time.Now(),
		}
		_ = m.eventEmitter.EmitOrderUpdate(ctx, update)
	}

	return response, nil
}

// ReconcileOrder updates order status from exchange
func (m *Manager) ReconcileOrder(ctx context.Context, clientOrderID string) error {
	m.mu.RLock()
	bracketID, exists := m.ordersByClient[clientOrderID]
	m.mu.RUnlock()

	if !exists {
		return fmt.Errorf("order not found: %s", clientOrderID)
	}

	m.mu.RLock()
	bracket := m.orders[bracketID]
	m.mu.RUnlock()

	// Select client
	client := m.spotClient
	if bracket.Type == OrderTypeFutures {
		client = m.futuresClient
	}

	// Get open orders
	orders, err := client.GetOpenOrders(ctx, bracket.Symbol)
	if err != nil {
		return fmt.Errorf("failed to get open orders: %w", err)
	}

	// Update status based on exchange data
	for _, order := range orders {
		if order.ClientOrderID == clientOrderID {
			// Emit update if status changed
			if m.eventEmitter != nil {
				update := &OrderUpdate{
					EventType:     "order_update.v1",
					Symbol:        order.Symbol,
					OrderID:       order.OrderID,
					ClientOrderID: order.ClientOrderID,
					Status:        order.Status,
					Side:          order.Side,
					OrderType:     order.Type,
					Price:         order.Price,
					Quantity:      order.OrigQty,
					ExecutedQty:   order.ExecutedQty,
					UpdateTime:    time.Now(),
				}
				_ = m.eventEmitter.EmitOrderUpdate(ctx, update)
			}
			break
		}
	}

	return nil
}

// CancelOrder cancels an order
func (m *Manager) CancelOrder(ctx context.Context, req *CancelRequest) error {
	if req.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}

	// Determine which client to use based on symbol
	// For simplicity, try spot first, then futures
	var err error
	if req.OrderID > 0 {
		err = m.spotClient.CancelOrder(ctx, req.Symbol, req.OrderID)
		if err != nil {
			// Try futures
			err = m.futuresClient.CancelOrder(ctx, req.Symbol, req.OrderID)
		}
	} else {
		return fmt.Errorf("order ID is required")
	}

	if err == nil && m.eventEmitter != nil {
		// Emit cancellation event
		update := &OrderUpdate{
			EventType:     "order_update.v1",
			Symbol:        req.Symbol,
			OrderID:       req.OrderID,
			ClientOrderID: req.ClientOrderID,
			Status:        "CANCELED",
			UpdateTime:    time.Now(),
			Reason:        "User requested cancellation",
		}
		_ = m.eventEmitter.EmitOrderUpdate(ctx, update)
	}

	return err
}

// validateBracketRequest validates bracket order request
func (m *Manager) validateBracketRequest(req *PlaceBracketRequest) error {
	if req.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if req.Side != "BUY" && req.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", req.Side)
	}
	if req.Quantity.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("quantity must be positive")
	}
	if len(req.TakeProfitPrices) == 0 {
		return fmt.Errorf("at least one take profit price is required")
	}
	if req.StopLossPrice.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("stop loss price must be positive")
	}

	// Validate price relationships
	if req.Side == "BUY" {
		// For buy orders: SL < entry < TP
		if !req.EntryPrice.IsZero() && req.StopLossPrice.GreaterThanOrEqual(req.EntryPrice) {
			return fmt.Errorf("stop loss must be below entry for buy orders")
		}
		for i, tp := range req.TakeProfitPrices {
			if !req.EntryPrice.IsZero() && tp.LessThanOrEqual(req.EntryPrice) {
				return fmt.Errorf("take profit %d must be above entry for buy orders", i+1)
			}
		}
	} else {
		// For sell orders: TP < entry < SL
		if !req.EntryPrice.IsZero() && req.StopLossPrice.LessThanOrEqual(req.EntryPrice) {
			return fmt.Errorf("stop loss must be above entry for sell orders")
		}
		for i, tp := range req.TakeProfitPrices {
			if !req.EntryPrice.IsZero() && tp.GreaterThanOrEqual(req.EntryPrice) {
				return fmt.Errorf("take profit %d must be below entry for sell orders", i+1)
			}
		}
	}

	return nil
}

// generateClientOrderID generates a unique client order ID
func (m *Manager) generateClientOrderID(bracketID, orderType string) string {
	return fmt.Sprintf("%s_%s_%d", bracketID[:8], orderType, time.Now().UnixNano())
}