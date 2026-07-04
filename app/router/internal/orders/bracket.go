package orders

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"
	"router/internal/binance"
)

type bracketPlacementResult struct {
	IDs                ClientOrderIDs
	Main               *binance.OrderResponse
	TakeProfits        []*binance.OrderResponse
	StopLoss           *binance.OrderResponse
	FailsafeClose      *binance.OrderResponse
	StopLossLimitPrice decimal.Decimal
}

// placeSpotBracket places a bracket order for spot trading
func (m *Manager) placeSpotBracket(ctx context.Context, client *binance.Client, req *PlaceBracketRequest, bracketID string) (*bracketPlacementResult, error) {
	result := &bracketPlacementResult{
		IDs: ClientOrderIDs{
			TakeProfits: make([]string, len(req.TakeProfitPrices)),
		},
		TakeProfits: make([]*binance.OrderResponse, len(req.TakeProfitPrices)),
	}
	plannedIDs := m.plannedClientOrderIDs(req, bracketID)

	// Create error aggregator
	bracketErr := NewBracketOrderError(bracketID, req.Symbol)

	// 1. Place main order
	mainOrderID := plannedIDs.Main
	mainOrder := binance.SpotOrderRequest{
		Symbol:           req.Symbol,
		Side:             req.Side,
		Type:             getOrderType(req.OrderType, req.EntryPrice),
		Quantity:         req.Quantity,
		Price:            req.EntryPrice,
		TimeInForce:      "GTC",
		NewClientOrderID: mainOrderID,
	}

	mainResp, err := client.PlaceSpotOrder(ctx, mainOrder)
	if err != nil {
		bracketErr.Add("MAIN", err)
		// Return immediately if main order fails as it's critical
		return result, bracketErr
	}
	result.IDs.Main = mainOrderID
	result.Main = mainResp

	// 2. Place take profit orders (as limit orders)
	// For spot, we can place these immediately
	tpStep, err := client.StepSize(ctx, req.Symbol)
	if err != nil {
		return result, fmt.Errorf("failed to resolve step size: %w", err)
	}
	tpQuantities := splitTakeProfitQuantities(req.Quantity, len(req.TakeProfitPrices), tpStep)
	for i, tpPrice := range req.TakeProfitPrices {
		tpID := plannedIDs.TakeProfits[i]
		tpQuantity := tpQuantities[i]

		tpOrder := binance.SpotOrderRequest{
			Symbol:           req.Symbol,
			Side:             getOppositeSide(req.Side),
			Type:             "LIMIT",
			Quantity:         tpQuantity,
			Price:            tpPrice,
			TimeInForce:      "GTC",
			NewClientOrderID: tpID,
		}

		tpResp, err := client.PlaceSpotOrder(ctx, tpOrder)
		if err != nil {
			bracketErr.Add(fmt.Sprintf("TP%d", i+1), err)
			m.logger.Error().
				Err(err).
				Str("symbol", req.Symbol).
				Str("tp_id", tpID).
				Int("tp_index", i+1).
				Msg("Failed to place take profit order")
		} else {
			result.IDs.TakeProfits[i] = tpID
			result.TakeProfits[i] = tpResp
		}
	}

	// 3. Place stop loss order using STOP_LOSS_LIMIT
	slID := plannedIDs.StopLoss

	// For STOP_LOSS_LIMIT:
	// - stopPrice is the trigger price
	// - price is the limit price (slightly worse than stop to ensure fill)
	tickSize := decimal.Zero
	if info, err := client.GetSymbolInfo(ctx, req.Symbol); err == nil && info != nil && info.TickSize.IsPositive() {
		tickSize = info.TickSize
	}
	slLimitPrice := stopLossLimitPriceForSpotBracket(req.StopLossPrice, req.Side, tickSize)
	result.StopLossLimitPrice = slLimitPrice

	slOrder := binance.SpotOrderRequest{
		Symbol:           req.Symbol,
		Side:             getOppositeSide(req.Side),
		Type:             "STOP_LOSS_LIMIT",
		Quantity:         req.Quantity,
		Price:            slLimitPrice,      // Limit price
		StopPrice:        req.StopLossPrice, // Trigger price
		TimeInForce:      "GTC",
		NewClientOrderID: slID,
	}

	slResp, err := client.PlaceSpotOrder(ctx, slOrder)
	if err != nil {
		bracketErr.Add("SL", err)
		m.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("sl_id", slID).
			Msg("Failed to place stop loss order")
	} else {
		result.IDs.StopLoss = slID
		result.StopLoss = slResp
	}

	// Log successful placement
	m.logger.Info().
		Str("symbol", req.Symbol).
		Str("bracket_id", bracketID).
		Int64("main_order_id", mainResp.OrderID).
		Str("side", req.Side).
		Str("quantity", req.Quantity.String()).
		Bool("has_errors", bracketErr.HasErrors()).
		Msg("Placed spot bracket order")

	// Return aggregated errors if any
	if bracketErr.HasCriticalError() {
		m.failClosedSpotBracket(ctx, client, req, bracketID, result, bracketErr)
	}
	if bracketErr.HasErrors() {
		return result, bracketErr
	}

	return result, nil
}

// placeFuturesBracket places a bracket order for futures trading
func (m *Manager) placeFuturesBracket(ctx context.Context, client *binance.Client, req *PlaceBracketRequest, bracketID string) (*bracketPlacementResult, error) {
	result := &bracketPlacementResult{
		IDs: ClientOrderIDs{
			TakeProfits: make([]string, len(req.TakeProfitPrices)),
		},
		TakeProfits: make([]*binance.OrderResponse, len(req.TakeProfitPrices)),
	}
	plannedIDs := m.plannedClientOrderIDs(req, bracketID)

	// Create error aggregator
	bracketErr := NewBracketOrderError(bracketID, req.Symbol)

	// 1. Place main order
	mainOrderID := plannedIDs.Main
	mainOrder := binance.FuturesOrderRequest{
		Symbol:           req.Symbol,
		Side:             req.Side,
		Type:             getOrderType(req.OrderType, req.EntryPrice),
		Quantity:         req.Quantity,
		Price:            req.EntryPrice,
		TimeInForce:      "GTC",
		NewClientOrderID: mainOrderID,
		ReduceOnly:       false, // Opening position
	}

	mainResp, err := client.PlaceFuturesOrder(ctx, mainOrder)
	if err != nil {
		bracketErr.Add("MAIN", err)
		// Return immediately if main order fails as it's critical
		return result, bracketErr
	}
	result.IDs.Main = mainOrderID
	result.Main = mainResp

	// 2. Place take profit orders with ReduceOnly
	tpStep, err := client.StepSize(ctx, req.Symbol)
	if err != nil {
		return result, fmt.Errorf("failed to resolve step size: %w", err)
	}
	tpQuantities := splitTakeProfitQuantities(req.Quantity, len(req.TakeProfitPrices), tpStep)
	for i, tpPrice := range req.TakeProfitPrices {
		tpID := plannedIDs.TakeProfits[i]
		tpQuantity := tpQuantities[i]

		tpOrder := binance.FuturesOrderRequest{
			Symbol:           req.Symbol,
			Side:             getOppositeSide(req.Side),
			Type:             "LIMIT",
			Quantity:         tpQuantity,
			Price:            tpPrice,
			TimeInForce:      "GTC",
			NewClientOrderID: tpID,
			ReduceOnly:       true, // TP orders reduce position
		}

		tpResp, err := client.PlaceFuturesOrder(ctx, tpOrder)
		if err != nil {
			bracketErr.Add(fmt.Sprintf("TP%d", i+1), err)
			m.logger.Error().
				Err(err).
				Str("symbol", req.Symbol).
				Str("tp_id", tpID).
				Int("tp_index", i+1).
				Msg("Failed to place futures take profit order")
		} else {
			result.IDs.TakeProfits[i] = tpID
			result.TakeProfits[i] = tpResp
		}
	}

	// 3. Place stop loss order using STOP_MARKET
	slID := plannedIDs.StopLoss
	slOrder := binance.FuturesOrderRequest{
		Symbol:           req.Symbol,
		Side:             getOppositeSide(req.Side),
		Type:             "STOP_MARKET",
		Quantity:         decimal.Zero,
		StopPrice:        req.StopLossPrice, // Stop trigger price
		TimeInForce:      "GTC",
		NewClientOrderID: slID,
		ReduceOnly:       true, // SL reduces position
		ClosePosition:    true, // Close entire position on stop
	}

	slResp, err := client.PlaceFuturesOrder(ctx, slOrder)
	if err != nil {
		bracketErr.Add("SL", err)
		m.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("sl_id", slID).
			Msg("Failed to place futures stop loss order")
	} else {
		result.IDs.StopLoss = slID
		result.StopLoss = slResp
	}

	// Log successful placement
	m.logger.Info().
		Str("symbol", req.Symbol).
		Str("bracket_id", bracketID).
		Int64("main_order_id", mainResp.OrderID).
		Str("side", req.Side).
		Str("quantity", req.Quantity.String()).
		Bool("has_errors", bracketErr.HasErrors()).
		Msg("Placed futures bracket order")

	// Return aggregated errors if any
	if bracketErr.HasErrors() {
		return result, bracketErr
	}

	return result, nil
}

func (m *Manager) failClosedSpotBracket(
	ctx context.Context,
	client *binance.Client,
	req *PlaceBracketRequest,
	bracketID string,
	result *bracketPlacementResult,
	bracketErr *BracketOrderError,
) {
	if result == nil || result.Main == nil {
		return
	}

	m.cancelSpotProtectiveOrders(ctx, client, req.Symbol, result.TakeProfits, bracketErr)

	mainExecutedQty := result.Main.ExecutedQty
	mainStatus := normalizeOrderStatus(result.Main.Status)
	if mainStatus == "NEW" || mainStatus == "PARTIALLY_FILLED" {
		cancelResp, err := client.CancelOrder(ctx, req.Symbol, result.Main.OrderID)
		if err != nil {
			bracketErr.Add("CANCEL_MAIN", err)
			m.logger.Error().
				Err(err).
				Str("symbol", req.Symbol).
				Int64("order_id", result.Main.OrderID).
				Msg("Failed to cancel unsafe main spot order")
		} else {
			if cancelResp != nil {
				mainExecutedQty = cancelResp.ExecutedQty
				mainStatus = normalizeOrderStatus(cancelResp.Status)
			}
			m.logger.Warn().
				Str("symbol", req.Symbol).
				Int64("order_id", result.Main.OrderID).
				Msg("Canceled unsafe main spot order")
		}
		if err != nil || mainStatus == "NEW" || mainStatus == "PARTIALLY_FILLED" {
			currentOrder, getErr := client.GetOrder(ctx, req.Symbol, result.Main.OrderID)
			if getErr == nil && currentOrder != nil {
				mainExecutedQty = currentOrder.ExecutedQty
				mainStatus = normalizeOrderStatus(currentOrder.Status)
			}
		}
	}

	if result.Main != nil {
		result.Main.Status = mainStatus
		result.Main.ExecutedQty = mainExecutedQty
	}
	if mainStatus == "FILLED" || mainStatus == "PARTIALLY_FILLED" || mainExecutedQty.GreaterThan(decimal.Zero) {
		result.FailsafeClose = m.closeUnsafeFilledSpotEntry(ctx, client, req, bracketID, mainExecutedQty, bracketErr)
	}
}

func (m *Manager) cancelSpotProtectiveOrders(
	ctx context.Context,
	client *binance.Client,
	symbol string,
	orders []*binance.OrderResponse,
	bracketErr *BracketOrderError,
) {
	for i, order := range orders {
		if order == nil || order.OrderID <= 0 {
			continue
		}
		if _, err := client.CancelOrder(ctx, symbol, order.OrderID); err != nil {
			bracketErr.Add(fmt.Sprintf("CANCEL_TP%d", i+1), err)
			m.logger.Error().
				Err(err).
				Str("symbol", symbol).
				Int64("order_id", order.OrderID).
				Int("tp_index", i+1).
				Msg("Failed to cancel unsafe take profit order")
			continue
		}
		m.logger.Warn().
			Str("symbol", symbol).
			Int64("order_id", order.OrderID).
			Int("tp_index", i+1).
			Msg("Canceled unsafe take profit order")
	}
}

func (m *Manager) closeUnsafeFilledSpotEntry(
	ctx context.Context,
	client *binance.Client,
	req *PlaceBracketRequest,
	bracketID string,
	executedQty decimal.Decimal,
	bracketErr *BracketOrderError,
) *binance.OrderResponse {
	if executedQty.LessThanOrEqual(decimal.Zero) {
		return nil
	}

	closeOrder := binance.SpotOrderRequest{
		Symbol:           req.Symbol,
		Side:             getOppositeSide(req.Side),
		Type:             "MARKET",
		Quantity:         executedQty,
		NewClientOrderID: m.generateClientOrderID(bracketID, "FAILSAFE"),
	}

	resp, err := client.PlaceSpotOrder(ctx, closeOrder)
	if err != nil {
		bracketErr.Add("FAILSAFE", err)
		m.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("side", closeOrder.Side).
			Str("quantity", executedQty.String()).
			Msg("Failed to close unsafe filled spot entry")
		return nil
	}

	m.logger.Warn().
		Str("symbol", req.Symbol).
		Str("side", closeOrder.Side).
		Str("quantity", executedQty.String()).
		Msg("Closed unsafe filled spot entry with failsafe market order")
	return resp
}

func (m *Manager) plannedClientOrderIDs(req *PlaceBracketRequest, bracketID string) ClientOrderIDs {
	if req.ClientOrderIDs != nil {
		tps := make([]string, len(req.ClientOrderIDs.TakeProfits))
		copy(tps, req.ClientOrderIDs.TakeProfits)
		return ClientOrderIDs{
			Main:        req.ClientOrderIDs.Main,
			TakeProfits: tps,
			StopLoss:    req.ClientOrderIDs.StopLoss,
		}
	}

	tps := make([]string, len(req.TakeProfitPrices))
	for i := range req.TakeProfitPrices {
		tps[i] = m.generateClientOrderID(bracketID, fmt.Sprintf("TP%d", i+1))
	}

	return ClientOrderIDs{
		Main:        m.generateClientOrderID(bracketID, "MAIN"),
		TakeProfits: tps,
		StopLoss:    m.generateClientOrderID(bracketID, "SL"),
	}
}

// getOrderType returns the order type based on price
func getOrderType(requestedType string, price decimal.Decimal) string {
	if requestedType != "" {
		return requestedType
	}
	if price.IsZero() {
		return "MARKET"
	}
	return "LIMIT"
}

// getOppositeSide returns the opposite side for closing orders
func getOppositeSide(side string) string {
	if side == "BUY" {
		return "SELL"
	}
	return "BUY"
}

// CloseAllPositions closes all open positions
func (m *Manager) CloseAllPositions(ctx context.Context, req *CloseAllRequest) error {
	client := m.spotClient
	if req.IsFutures {
		client = m.futuresClient
	}

	// Get open orders
	var symbols []string
	if req.Symbol != "" {
		symbols = []string{req.Symbol}
	} else {
		// In production, we'd get all active symbols from positions
		// For now, return error
		return fmt.Errorf("symbol is required for close all")
	}

	var lastErr error
	for _, symbol := range symbols {
		orders, err := client.GetOpenOrders(ctx, symbol)
		if err != nil {
			lastErr = err
			continue
		}

		// Cancel all open orders
		for _, order := range orders {
			_, err = client.CancelOrder(ctx, symbol, order.OrderID)
			if err != nil {
				lastErr = err
				m.logger.Error().
					Err(err).
					Str("symbol", symbol).
					Int64("order_id", order.OrderID).
					Msg("Failed to cancel order during close all")
			}
		}

		// For futures, also close position with market order
		if req.IsFutures {
			m.logger.Warn().
				Str("symbol", symbol).
				Msg("Close-all futures positions not implemented; canceled orders only")
		}
	}

	return lastErr
}

// splitTakeProfitQuantities splits a total quantity into n step-aligned
// slices, assigning the rounding remainder to the last slice so the sum is
// exactly the total. A zero step returns an even unrounded split.
func splitTakeProfitQuantities(total decimal.Decimal, n int, step decimal.Decimal) []decimal.Decimal {
	if n <= 0 {
		return nil
	}
	quantities := make([]decimal.Decimal, n)
	even := total.Div(decimal.NewFromInt(int64(n)))
	if !step.IsPositive() {
		for i := range quantities {
			quantities[i] = even
		}
		return quantities
	}

	slice := even.Div(step).Floor().Mul(step)
	allocated := decimal.Zero
	for i := 0; i < n-1; i++ {
		quantities[i] = slice
		allocated = allocated.Add(slice)
	}
	quantities[n-1] = total.Sub(allocated)
	return quantities
}
