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
	orders         map[string]*BracketOrder // bracket order ID -> order
	ordersByClient map[string]string        // client order ID -> bracket order ID
	mu             sync.RWMutex

	// Event emitter
	eventEmitter EventEmitter

	spotReconciler      spotOrderTracker
	spotExecutionLedger spotExecutionLedger

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

func (m *Manager) SetSpotReconciler(reconciler spotOrderTracker) {
	m.spotReconciler = reconciler
}

func (m *Manager) SetSpotExecutionLedger(ledger spotExecutionLedger) {
	m.spotExecutionLedger = ledger
}

func (m *Manager) trackSpotPlacementLeg(leg *binance.OrderResponse) {
	if m == nil || m.spotReconciler == nil || leg == nil {
		return
	}
	status := normalizeOrderStatus(leg.Status)
	if isTerminalOrderStatus(status) {
		return
	}
	m.spotReconciler.Track(SpotReconcileRequest{
		Symbol:        leg.Symbol,
		OrderID:       leg.OrderID,
		ClientOrderID: leg.ClientOrderID,
		Side:          leg.Side,
		OrderType:     leg.Type,
		Quantity:      leg.OrigQty,
		Price:         leg.Price,
		InitialStatus: status,
		ExecutedQty:   leg.ExecutedQty,
	})
}

func (m *Manager) trackSpotPlacementLegs(placement *bracketPlacementResult) {
	if m == nil || m.spotReconciler == nil || placement == nil {
		return
	}
	m.trackSpotPlacementLeg(placement.Main)
	for _, takeProfit := range placement.TakeProfits {
		m.trackSpotPlacementLeg(takeProfit)
	}
	m.trackSpotPlacementLeg(placement.StopLoss)
}

func (m *Manager) CancelOpenOrders(
	ctx context.Context,
	req *CancelOpenOrdersRequest,
) (*CancelOpenOrdersResponse, error) {
	if req == nil {
		return nil, fmt.Errorf("request is required")
	}
	if req.Scope != EmergencyScopeAll && req.Scope != EmergencyScopeSpot && req.Scope != EmergencyScopeFutures {
		return nil, fmt.Errorf("invalid scope: %s", req.Scope)
	}

	resp := &CancelOpenOrdersResponse{CanceledOrders: 0, Errors: nil}

	cancelForClient := func(client *binance.Client, symbols []string) {
		if client == nil {
			resp.Errors = append(resp.Errors, "client not configured")
			return
		}
		for _, symbol := range symbols {
			openOrders, err := client.GetOpenOrders(ctx, symbol)
			if err != nil {
				resp.Errors = append(resp.Errors, fmt.Sprintf("%s: list open orders failed: %v", symbol, err))
				continue
			}
			for _, order := range openOrders {
				if _, err := client.CancelOrder(ctx, symbol, order.OrderID); err != nil {
					resp.Errors = append(resp.Errors, fmt.Sprintf("%s: cancel order %d failed: %v", symbol, order.OrderID, err))
					continue
				}
				resp.CanceledOrders += 1
			}
		}
	}

	switch req.Scope {
	case EmergencyScopeSpot:
		cancelForClient(m.spotClient, req.Symbols)
	case EmergencyScopeFutures:
		cancelForClient(m.futuresClient, req.Symbols)
	case EmergencyScopeAll:
		cancelForClient(m.spotClient, req.Symbols)
		cancelForClient(m.futuresClient, req.Symbols)
	}

	return resp, nil
}

func (m *Manager) ClosePositions(
	ctx context.Context,
	req *ClosePositionsRequest,
) (*ClosePositionsResponse, error) {
	if req == nil {
		return nil, fmt.Errorf("request is required")
	}
	if req.Scope != EmergencyScopeAll && req.Scope != EmergencyScopeSpot && req.Scope != EmergencyScopeFutures {
		return nil, fmt.Errorf("invalid scope: %s", req.Scope)
	}

	resp := &ClosePositionsResponse{ClosedPositions: 0, Errors: nil}

	if req.Scope == EmergencyScopeSpot {
		resp.Errors = append(resp.Errors, "spot position closing not supported")
		return resp, nil
	}

	if m.futuresClient == nil {
		resp.Errors = append(resp.Errors, "futures client not configured")
		return resp, nil
	}

	account, err := m.futuresClient.GetFuturesAccountInfo(ctx)
	if err != nil {
		resp.Errors = append(resp.Errors, fmt.Sprintf("get futures account failed: %v", err))
		return resp, nil
	}

	allowedSymbols := map[string]struct{}{}
	if len(req.Symbols) > 0 {
		for _, s := range req.Symbols {
			allowedSymbols[s] = struct{}{}
		}
	}

	for _, p := range account.Positions {
		if p.PositionAmt.IsZero() {
			continue
		}
		if len(allowedSymbols) > 0 {
			if _, ok := allowedSymbols[p.Symbol]; !ok {
				continue
			}
		}

		side := "SELL"
		if p.PositionAmt.IsNegative() {
			side = "BUY"
		}

		_, placeErr := m.futuresClient.PlaceFuturesOrder(ctx, binance.FuturesOrderRequest{
			Symbol:        p.Symbol,
			Side:          side,
			Type:          "MARKET",
			Quantity:      decimal.Zero,
			ReduceOnly:    true,
			ClosePosition: true,
		})
		if placeErr != nil {
			resp.Errors = append(resp.Errors, fmt.Sprintf("%s: close position failed: %v", p.Symbol, placeErr))
			continue
		}

		resp.ClosedPositions += 1
	}

	return resp, nil
}

// PlaceBracketOrder places a bracket order with idempotency
func (m *Manager) PlaceBracketOrder(ctx context.Context, req *PlaceBracketRequest) (*PlaceBracketResponse, error) {
	// Validate request
	if err := m.validateBracketRequest(req); err != nil {
		return nil, fmt.Errorf("invalid bracket request: %w", err)
	}

	if req.ClientOrderIDs != nil && req.ClientOrderIDs.Main != "" {
		m.mu.RLock()
		bracketID, exists := m.ordersByClient[req.ClientOrderIDs.Main]
		var existing *BracketOrder
		if exists {
			existing = m.orders[bracketID]
		}
		m.mu.RUnlock()

		if exists && existing != nil {
			return &PlaceBracketResponse{
				BracketOrderID:     bracketID,
				ClientOrderIDs:     existing.ClientOrderIDs,
				Symbol:             existing.Symbol,
				Side:               existing.Side,
				Quantity:           existing.Quantity,
				StopLossLimitPrice: existing.StopLossLimitPrice,
				CreatedAt:          existing.CreatedAt,
			}, nil
		}
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

	var placement *bracketPlacementResult
	if req.IsFutures {
		placement, err = m.placeFuturesBracket(ctx, client, req, bracketID)
	} else {
		placement, err = m.placeSpotBracket(ctx, client, req, bracketID)
	}
	if placement != nil {
		bracket.ClientOrderIDs = placement.IDs
		bracket.StopLossLimitPrice = placement.StopLossLimitPrice
	}

	response.ClientOrderIDs = bracket.ClientOrderIDs
	response.StopLossLimitPrice = bracket.StopLossLimitPrice

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
	venue := "SPOT"
	if req.IsFutures {
		venue = "USD_M"
	}

	if placement != nil && placement.Main != nil {
		initialUpdate := &OrderUpdate{
			EventType:     "order_update.v1",
			Venue:         venue,
			Symbol:        req.Symbol,
			OrderID:       placement.Main.OrderID,
			ClientOrderID: bracket.ClientOrderIDs.Main,
			Status:        normalizeOrderStatus(placement.Main.Status),
			Side:          placement.Main.Side,
			OrderType:     placement.Main.Type,
			Price:         initialOrderUpdatePrice(req, placement.Main),
			Quantity:      orderUpdateQuantity(req.Quantity, placement.Main.OrigQty),
			ExecutedQty:   placement.Main.ExecutedQty,
			UpdateTime:    orderUpdateTimeFromMillis(placement.Main.TransactTime),
		}
		if !req.IsFutures && m.spotExecutionLedger != nil && placement.Main.ExecutedQty.GreaterThan(decimal.Zero) && len(placement.Main.Fills) > 0 {
			snapshot := SpotExecutionSnapshot{
				Symbol:        req.Symbol,
				OrderID:       placement.Main.OrderID,
				ClientOrderID: bracket.ClientOrderIDs.Main,
				Side:          placement.Main.Side,
				OrderType:     placement.Main.Type,
				Price:         initialUpdate.Price,
				Quantity:      initialUpdate.Quantity,
				ExecutedQty:   placement.Main.ExecutedQty,
				Status:        initialUpdate.Status,
				UpdateTime:    initialUpdate.UpdateTime,
				Trades:        make([]SpotExecutionTrade, 0, len(placement.Main.Fills)),
			}
			for _, fill := range placement.Main.Fills {
				snapshot.Trades = append(snapshot.Trades, SpotExecutionTrade{
					TradeID:         fill.TradeID,
					Price:           fill.Price,
					Quantity:        fill.Qty,
					Commission:      fill.Commission,
					CommissionAsset: fill.CommissionAsset,
					Time:            initialUpdate.UpdateTime,
				})
			}
			if err := m.spotExecutionLedger.PersistSpotExecution(ctx, snapshot); err != nil {
				m.logger.Error().
					Err(err).
					Str("symbol", snapshot.Symbol).
					Str("client_order_id", snapshot.ClientOrderID).
					Str("status", snapshot.Status).
					Msg("Failed to persist immediate spot execution snapshot")
			}
		}
		m.emitOrderUpdateWithLogging(ctx, initialUpdate)

		if !req.IsFutures && m.spotReconciler != nil {
			m.trackSpotPlacementLegs(placement)
		}
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
			venue := "SPOT"
			if bracket.Type == OrderTypeFutures {
				venue = "USD_M"
			}
			m.emitOrderUpdateWithLogging(ctx, &OrderUpdate{
				EventType:     "order_update.v1",
				Venue:         venue,
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
			})
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

	// For simplicity, try spot first, then futures.
	var (
		err   error
		venue string
	)
	if req.OrderID > 0 {
		if m.spotClient != nil {
			_, err = m.spotClient.CancelOrder(ctx, req.Symbol, req.OrderID)
			if err == nil {
				venue = "SPOT"
			}
		} else {
			err = fmt.Errorf("spot client not configured")
		}
		if err != nil && m.futuresClient != nil {
			// Try futures
			_, err = m.futuresClient.CancelOrder(ctx, req.Symbol, req.OrderID)
			if err == nil {
				venue = "USD_M"
			}
		}
	} else {
		return fmt.Errorf("order ID is required")
	}

	if err == nil {
		// Emit cancellation event
		m.emitOrderUpdateWithLogging(ctx, &OrderUpdate{
			EventType:     "order_update.v1",
			Venue:         venue,
			Symbol:        req.Symbol,
			OrderID:       req.OrderID,
			ClientOrderID: req.ClientOrderID,
			Status:        "CANCELED",
			UpdateTime:    time.Now(),
			Reason:        "User requested cancellation",
		})
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

	if req.ClientOrderIDs != nil {
		if req.ClientOrderIDs.Main == "" {
			return fmt.Errorf("client_order_ids.main is required")
		}
		if req.ClientOrderIDs.StopLoss == "" {
			return fmt.Errorf("client_order_ids.stop_loss is required")
		}
		if len(req.ClientOrderIDs.TakeProfits) != len(req.TakeProfitPrices) {
			return fmt.Errorf("client_order_ids.take_profits count must match take_profit_prices")
		}

		all := append([]string{req.ClientOrderIDs.Main, req.ClientOrderIDs.StopLoss}, req.ClientOrderIDs.TakeProfits...)
		seen := make(map[string]struct{}, len(all))
		for _, id := range all {
			if id == "" {
				return fmt.Errorf("client_order_ids values must be non-empty")
			}
			if len(id) > 36 {
				return fmt.Errorf("client_order_id too long: %d", len(id))
			}
			if _, ok := seen[id]; ok {
				return fmt.Errorf("duplicate client_order_id: %s", id)
			}
			seen[id] = struct{}{}
		}
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

// emitOrderUpdateWithLogging emits an order update and logs any errors.
// This ensures event emission failures are observable while not failing the order operation.
func (m *Manager) emitOrderUpdateWithLogging(ctx context.Context, update *OrderUpdate) {
	if m.eventEmitter == nil || update == nil {
		return
	}
	if err := m.eventEmitter.EmitOrderUpdate(ctx, update); err != nil {
		m.logger.Error().
			Err(err).
			Str("symbol", update.Symbol).
			Str("client_order_id", update.ClientOrderID).
			Str("event_type", update.EventType).
			Str("status", update.Status).
			Msg("failed to emit order update event")
	}
}

func initialOrderUpdatePrice(req *PlaceBracketRequest, response *binance.OrderResponse) decimal.Decimal {
	if response == nil {
		if req == nil {
			return decimal.Zero
		}
		return req.EntryPrice
	}

	totalQty := decimal.Zero
	totalNotional := decimal.Zero
	for _, fill := range response.Fills {
		if fill.Qty.LessThanOrEqual(decimal.Zero) {
			continue
		}
		totalQty = totalQty.Add(fill.Qty)
		totalNotional = totalNotional.Add(fill.Price.Mul(fill.Qty))
	}
	if totalQty.GreaterThan(decimal.Zero) {
		return totalNotional.Div(totalQty)
	}
	if response.Price.GreaterThan(decimal.Zero) {
		return response.Price
	}
	if req != nil {
		return req.EntryPrice
	}
	return decimal.Zero
}

func orderUpdateQuantity(fallback, quantity decimal.Decimal) decimal.Decimal {
	if quantity.GreaterThan(decimal.Zero) {
		return quantity
	}
	return fallback
}
