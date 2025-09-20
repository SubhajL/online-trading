package binance

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/rest"
)

// TestPlaceSpotOrder_RealTestnet tests real order placement on testnet
func TestPlaceSpotOrder_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	// Find a suitable test symbol
	symbol := findTestSymbol(t, client)

	// Get symbol info for proper price/quantity
	info, err := client.restClient.GetExchangeInfo(ctx)
	require.NoError(t, err)

	var symbolInfo *rest.Symbol
	for _, s := range info.Symbols {
		if s.Symbol == symbol {
			symbolInfo = &s
			break
		}
	}
	require.NotNil(t, symbolInfo, "Symbol info not found")

	// Get current market price
	ticker, err := client.restClient.GetTicker24hr(ctx, symbol)
	require.NoError(t, err)
	currentPrice := ticker.LastPrice
	t.Logf("Current %s price: %s", symbol, currentPrice.String())

	// Create a small test order that won't fill
	// Use 50% of current price for BUY order so it won't execute
	// Round to 2 decimal places for common price precision
	testPrice := currentPrice.Mul(decimal.NewFromFloat(0.5)).Round(2)
	testQty := decimal.NewFromFloat(0.001) // Small quantity

	order := SpotOrderRequest{
		Symbol:           symbol,
		Side:             "BUY",
		Type:             "LIMIT",
		Quantity:         testQty,
		Price:            testPrice,
		TimeInForce:      "GTC",
		NewClientOrderID: fmt.Sprintf("test-%d", time.Now().Unix()),
	}

	resp, err := client.PlaceSpotOrder(ctx, order)
	require.NoError(t, err)
	assert.NotNil(t, resp)
	assert.Equal(t, symbol, resp.Symbol)
	assert.Greater(t, resp.OrderID, int64(0))
	assert.Equal(t, "NEW", resp.Status)

	t.Logf("Placed test order: %d", resp.OrderID)

	// Cancel the order to clean up
	err = client.CancelOrder(ctx, symbol, resp.OrderID)
	assert.NoError(t, err)
	t.Log("Cancelled test order")
}

// TestGetAccountInfo_RealTestnet tests getting real account info
func TestGetAccountInfo_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	// First call
	start := time.Now()
	account1, err := client.GetAccountInfo(ctx)
	require.NoError(t, err)
	assert.NotNil(t, account1)
	assert.True(t, account1.CanTrade)
	firstCallDuration := time.Since(start)

	// Second call should be cached
	start = time.Now()
	account2, err := client.GetAccountInfo(ctx)
	require.NoError(t, err)
	assert.Equal(t, account1.UpdateTime, account2.UpdateTime)
	secondCallDuration := time.Since(start)

	// Second call should be much faster due to cache
	assert.Less(t, secondCallDuration, firstCallDuration/10)
	t.Logf("First call: %v, Cached call: %v", firstCallDuration, secondCallDuration)

	// Log some balances
	hasBalance := false
	for _, balance := range account1.Balances {
		if !balance.Free.IsZero() || !balance.Locked.IsZero() {
			t.Logf("Balance: %s - Free: %s, Locked: %s",
				balance.Asset, balance.Free.String(), balance.Locked.String())
			hasBalance = true
		}
	}
	if !hasBalance {
		t.Log("No non-zero balances found (this is normal for new testnet account)")
	}
}

// TestCancelOrder_NonExistent tests cancelling non-existent order
func TestCancelOrder_NonExistent(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	symbol := findTestSymbol(t, client)

	// Try to cancel non-existent order
	err := client.CancelOrder(ctx, symbol, 999999999)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "Unknown order")
}

// TestGetOpenOrders_RealTestnet tests getting open orders
func TestGetOpenOrders_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	symbol := findTestSymbol(t, client)

	orders, err := client.GetOpenOrders(ctx, symbol)
	require.NoError(t, err)
	assert.NotNil(t, orders)

	// Should be empty initially
	assert.Empty(t, orders)

	// Get current price
	ticker, err := client.restClient.GetTicker24hr(ctx, symbol)
	require.NoError(t, err)

	// Place a test order at 50% of current price
	order := SpotOrderRequest{
		Symbol:           symbol,
		Side:             "BUY",
		Type:             "LIMIT",
		Quantity:         decimal.NewFromFloat(0.001),
		Price:            ticker.LastPrice.Mul(decimal.NewFromFloat(0.5)).Round(2), // Low price, rounded
		TimeInForce:      "GTC",
		NewClientOrderID: fmt.Sprintf("test-open-%d", time.Now().Unix()),
	}

	resp, err := client.PlaceSpotOrder(ctx, order)
	require.NoError(t, err)

	// Now should have one order
	orders, err = client.GetOpenOrders(ctx, symbol)
	require.NoError(t, err)
	assert.Len(t, orders, 1)
	assert.Equal(t, resp.OrderID, orders[0].OrderID)

	// Clean up
	err = client.CancelOrder(ctx, symbol, resp.OrderID)
	assert.NoError(t, err)
}

// TestPlaceStopLossOrder_RealTestnet tests stop loss order placement
func TestPlaceStopLossOrder_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	symbol := findTestSymbol(t, client)

	// Get current price
	ticker, err := client.restClient.GetTicker24hr(ctx, symbol)
	require.NoError(t, err)
	currentPrice := ticker.LastPrice

	// For stop loss BUY, stop price should be above current price
	// Set stop at 150% of current price, limit at 151%
	order := SpotOrderRequest{
		Symbol:           symbol,
		Side:             "BUY",
		Type:             "STOP_LOSS_LIMIT",
		Quantity:         decimal.NewFromFloat(0.001),
		Price:            currentPrice.Mul(decimal.NewFromFloat(1.51)).Round(2), // Limit price
		StopPrice:        currentPrice.Mul(decimal.NewFromFloat(1.50)).Round(2), // Stop trigger price
		TimeInForce:      "GTC",
		NewClientOrderID: fmt.Sprintf("test-stop-%d", time.Now().Unix()),
	}

	resp, err := client.PlaceSpotOrder(ctx, order)
	if err != nil {
		// Some symbols might not support stop orders
		if assert.Contains(t, err.Error(), "not supported") {
			t.Skip("Stop orders not supported for this symbol")
		}
		require.NoError(t, err)
	}

	assert.NotNil(t, resp)
	assert.Equal(t, symbol, resp.Symbol)
	assert.Greater(t, resp.OrderID, int64(0))
	// Stop orders may return empty status and type in the response
	t.Logf("Stop order created with ID: %d", resp.OrderID)

	// Clean up
	err = client.CancelOrder(ctx, symbol, resp.OrderID)
	assert.NoError(t, err)
}

// TestSymbolValidation_RealTestnet tests symbol validation against exchange info
func TestSymbolValidation_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	client := createTestnetClient(t)
	ctx := context.Background()

	// Try invalid symbol
	order := SpotOrderRequest{
		Symbol:      "INVALID123",
		Side:        "BUY",
		Type:        "LIMIT",
		Quantity:    decimal.NewFromFloat(1),
		Price:       decimal.NewFromFloat(100),
		TimeInForce: "GTC",
	}

	_, err := client.PlaceSpotOrder(ctx, order)
	assert.Error(t, err)
	// Binance returns "Invalid symbol." for unknown symbols
	assert.Contains(t, err.Error(), "symbol")
}

// TestRateLimiting_RealTestnet tests rate limiting behavior
func TestRateLimiting_RealTestnet(t *testing.T) {
	if testing.Short() {
		t.Skip("Skipping integration test in short mode")
	}

	t.Skip("Rate limit testing can affect testnet usage - enable carefully")

	client := createTestnetClient(t)
	ctx := context.Background()

	// Make many requests quickly
	for i := 0; i < 20; i++ {
		_, err := client.GetAccountInfo(ctx)
		if err != nil {
			// Check if it's rate limit error
			if assert.Contains(t, err.Error(), "Too many requests") {
				t.Log("Hit rate limit as expected")
				break
			}
			require.NoError(t, err)
		}
	}
}
