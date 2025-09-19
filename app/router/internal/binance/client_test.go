package binance

import (
	"context"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
	"router/internal/rest"
)

const (
	testBaseURL   = "https://api.binance.com"
	testAPIKey    = "test-api-key"
	testSecretKey = "test-secret-key"
	testSymbol    = "BTCUSDT"
)

var (
	testPrice    = decimal.RequireFromString("50000.00")
	testQuantity = decimal.RequireFromString("0.001")
)

func TestNewClient_ValidatesConfiguration(t *testing.T) {
	signer := createTestSigner(t)
	restClient := createTestRestClient(t)
	logger := zerolog.Nop()

	client, err := NewClient(testBaseURL, signer, restClient, logger)
	require.NoError(t, err)
	assert.NotNil(t, client)
}

func TestNewClient_RequiresSigner(t *testing.T) {
	restClient := createTestRestClient(t)
	logger := zerolog.Nop()

	_, err := NewClient(testBaseURL, nil, restClient, logger)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "signer")
}

func TestNewClient_RequiresRestClient(t *testing.T) {
	signer := createTestSigner(t)
	logger := zerolog.Nop()

	_, err := NewClient(testBaseURL, signer, nil, logger)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "rest client")
}

func TestPlaceSpotOrder_ValidatesSymbolFilters(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	order := SpotOrderRequest{
		Symbol:   testSymbol,
		Side:     "BUY",
		Type:     "LIMIT",
		Quantity: testQuantity,
		Price:    testPrice,
	}

	_, err := client.PlaceSpotOrder(ctx, order)
	// Should validate against symbol filters
	assert.NoError(t, err) // This will fail until implemented
}

func TestPlaceSpotOrder_HandlesInsufficientBalance(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	order := SpotOrderRequest{
		Symbol:   testSymbol,
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.RequireFromString("1000000"), // Very large quantity
	}

	_, err := client.PlaceSpotOrder(ctx, order)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "insufficient")
}

func TestPlaceSpotOrder_SignsRequestProperly(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	order := SpotOrderRequest{
		Symbol:           testSymbol,
		Side:             "BUY",
		Type:             "LIMIT",
		Quantity:         testQuantity,
		Price:            testPrice,
		NewClientOrderID: "test-order-123",
	}

	response, err := client.PlaceSpotOrder(ctx, order)
	require.NoError(t, err)
	assert.Equal(t, testSymbol, response.Symbol)
	assert.Equal(t, "test-order-123", response.ClientOrderID)
}

func TestPlaceFuturesOrder_ValidatesLeverage(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	order := FuturesOrderRequest{
		Symbol:   testSymbol,
		Side:     "BUY",
		Type:     "LIMIT",
		Quantity: testQuantity,
		Price:    testPrice,
	}

	_, err := client.PlaceFuturesOrder(ctx, order)
	assert.NoError(t, err) // This will fail until implemented
}

func TestPlaceFuturesOrder_HandlesMarginRequirements(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	order := FuturesOrderRequest{
		Symbol:   testSymbol,
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.RequireFromString("1000000"), // Very large quantity
	}

	_, err := client.PlaceFuturesOrder(ctx, order)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "margin")
}

func TestGetAccountInfo_CachesResults(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	// First call
	account1, err1 := client.GetAccountInfo(ctx)
	require.NoError(t, err1)
	assert.NotNil(t, account1)

	// Second call should be cached
	account2, err2 := client.GetAccountInfo(ctx)
	require.NoError(t, err2)
	assert.Equal(t, account1.UpdateTime, account2.UpdateTime)
}

func TestGetAccountInfo_ParsesBalancesCorrectly(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	account, err := client.GetAccountInfo(ctx)
	require.NoError(t, err)
	assert.True(t, len(account.Balances) > 0)

	// Find BTC balance
	var btcBalance *Balance
	for _, balance := range account.Balances {
		if balance.Asset == "BTC" {
			btcBalance = &balance
			break
		}
	}
	assert.NotNil(t, btcBalance)
	assert.True(t, btcBalance.Free.GreaterThanOrEqual(decimal.Zero))
}

func TestCancelOrder_HandlesNotFound(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	err := client.CancelOrder(ctx, testSymbol, 999999999)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
}

func TestCancelOrder_HandlesAlreadyFilled(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	err := client.CancelOrder(ctx, testSymbol, 123456789)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "already filled")
}

func TestGetOpenOrders_HandlesPagination(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	orders, err := client.GetOpenOrders(ctx, testSymbol)
	require.NoError(t, err)
	assert.IsType(t, []*Order{}, orders)
}

func TestGetOpenOrders_FiltersSymbolCorrectly(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	orders, err := client.GetOpenOrders(ctx, testSymbol)
	require.NoError(t, err)

	for _, order := range orders {
		assert.Equal(t, testSymbol, order.Symbol)
	}
}

func TestClient_ConcurrentSafety(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	// Run multiple concurrent requests
	done := make(chan bool, 10)
	for i := 0; i < 10; i++ {
		go func() {
			_, err := client.GetAccountInfo(ctx)
			assert.NoError(t, err)
			done <- true
		}()
	}

	// Wait for all to complete
	for i := 0; i < 10; i++ {
		<-done
	}
}

func TestClient_RespectsRateLimits(t *testing.T) {
	client := createTestClient(t)
	ctx := context.Background()

	// Make rapid requests - should not fail due to rate limiting
	for i := 0; i < 5; i++ {
		_, err := client.GetAccountInfo(ctx)
		assert.NoError(t, err)
	}
}

// Helper functions

func createTestClient(t *testing.T) *Client {
	t.Helper()
	signer := createTestSigner(t)
	restClient := createTestRestClient(t)
	logger := zerolog.Nop()

	client, err := NewClient(testBaseURL, signer, restClient, logger)
	require.NoError(t, err)
	return client
}

func createTestSigner(t *testing.T) *auth.Signer {
	t.Helper()
	return auth.NewSigner(testAPIKey, testSecretKey)
}

func createTestRestClient(t *testing.T) *rest.Client {
	t.Helper()
	signer := createTestSigner(t)
	return rest.NewClient(testBaseURL, signer, rest.WithTimeout(30*time.Second))
}
