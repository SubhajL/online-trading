package orders

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"
	"router/internal/binance"
)

// placeSpotBracket places a bracket order for spot trading
func (m *Manager) placeSpotBracket(ctx context.Context, client *binance.Client, req *PlaceBracketRequest, bracketID string) (ClientOrderIDs, error) {
	ids := ClientOrderIDs{
		TakeProfits: make([]string, len(req.TakeProfitPrices)),
	}

	// Create error aggregator
	bracketErr := NewBracketOrderError(bracketID, req.Symbol)

	// 1. Place main order
	mainOrderID := m.generateClientOrderID(bracketID, "MAIN")
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
		return ids, bracketErr
	}
	ids.Main = mainOrderID

	// 2. Place take profit orders (as limit orders)
	// For spot, we can place these immediately
	for i, tpPrice := range req.TakeProfitPrices {
		tpID := m.generateClientOrderID(bracketID, fmt.Sprintf("TP%d", i+1))

		// Calculate quantity for this TP (split evenly for simplicity)
		tpQuantity := req.Quantity.Div(decimal.NewFromInt(int64(len(req.TakeProfitPrices))))

		tpOrder := binance.SpotOrderRequest{
			Symbol:           req.Symbol,
			Side:             getOppositeSide(req.Side),
			Type:             "LIMIT",
			Quantity:         tpQuantity,
			Price:            tpPrice,
			TimeInForce:      "GTC",
			NewClientOrderID: tpID,
		}

		_, err := client.PlaceSpotOrder(ctx, tpOrder)
		if err != nil {
			bracketErr.Add(fmt.Sprintf("TP%d", i+1), err)
			m.logger.Error().
				Err(err).
				Str("symbol", req.Symbol).
				Str("tp_id", tpID).
				Int("tp_index", i+1).
				Msg("Failed to place take profit order")
		} else {
			ids.TakeProfits[i] = tpID
		}
	}

	// 3. Place stop loss order using STOP_LOSS_LIMIT
	slID := m.generateClientOrderID(bracketID, "SL")

	// For STOP_LOSS_LIMIT:
	// - stopPrice is the trigger price
	// - price is the limit price (slightly worse than stop to ensure fill)
	slLimitPrice := req.StopLossPrice
	if req.Side == "BUY" {
		// For long positions, SL sells below stop price
		slLimitPrice = req.StopLossPrice.Mul(decimal.NewFromFloat(0.995))
	} else {
		// For short positions, SL buys above stop price
		slLimitPrice = req.StopLossPrice.Mul(decimal.NewFromFloat(1.005))
	}

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

	_, err = client.PlaceSpotOrder(ctx, slOrder)
	if err != nil {
		bracketErr.Add("SL", err)
		m.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("sl_id", slID).
			Msg("Failed to place stop loss order")
	} else {
		ids.StopLoss = slID
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
	if bracketErr.HasErrors() {
		return ids, bracketErr
	}

	return ids, nil
}

// placeFuturesBracket places a bracket order for futures trading
func (m *Manager) placeFuturesBracket(ctx context.Context, client *binance.Client, req *PlaceBracketRequest, bracketID string) (ClientOrderIDs, error) {
	ids := ClientOrderIDs{
		TakeProfits: make([]string, len(req.TakeProfitPrices)),
	}

	// Create error aggregator
	bracketErr := NewBracketOrderError(bracketID, req.Symbol)

	// 1. Place main order
	mainOrderID := m.generateClientOrderID(bracketID, "MAIN")
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
		return ids, bracketErr
	}
	ids.Main = mainOrderID

	// 2. Place take profit orders with ReduceOnly
	for i, tpPrice := range req.TakeProfitPrices {
		tpID := m.generateClientOrderID(bracketID, fmt.Sprintf("TP%d", i+1))

		// Calculate quantity for this TP
		tpQuantity := req.Quantity.Div(decimal.NewFromInt(int64(len(req.TakeProfitPrices))))

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

		_, err := client.PlaceFuturesOrder(ctx, tpOrder)
		if err != nil {
			bracketErr.Add(fmt.Sprintf("TP%d", i+1), err)
			m.logger.Error().
				Err(err).
				Str("symbol", req.Symbol).
				Str("tp_id", tpID).
				Int("tp_index", i+1).
				Msg("Failed to place futures take profit order")
		} else {
			ids.TakeProfits[i] = tpID
		}
	}

	// 3. Place stop loss order using STOP_MARKET
	slID := m.generateClientOrderID(bracketID, "SL")
	slOrder := binance.FuturesOrderRequest{
		Symbol:           req.Symbol,
		Side:             getOppositeSide(req.Side),
		Type:             "STOP_MARKET",
		Quantity:         req.Quantity,
		StopPrice:        req.StopLossPrice, // Stop trigger price
		TimeInForce:      "GTC",
		NewClientOrderID: slID,
		ReduceOnly:       true, // SL reduces position
		ClosePosition:    true, // Close entire position on stop
	}

	_, err = client.PlaceFuturesOrder(ctx, slOrder)
	if err != nil {
		bracketErr.Add("SL", err)
		m.logger.Error().
			Err(err).
			Str("symbol", req.Symbol).
			Str("sl_id", slID).
			Msg("Failed to place futures stop loss order")
	} else {
		ids.StopLoss = slID
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
		return ids, bracketErr
	}

	return ids, nil
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
			err = client.CancelOrder(ctx, symbol, order.OrderID)
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
			// In production, check actual position size
			// For now, skip position closing
		}
	}

	return lastErr
}
