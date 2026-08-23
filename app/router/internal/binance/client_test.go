package binance

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
	"router/internal/rest"
)

func TestGetOrderByClientIDSeparatesMarketPriceFromAverageFillPrice(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v3/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 42, "clientOrderId": "market-entry",
			"price": "0", "origQty": "2", "executedQty": "2",
			"cummulativeQuoteQty": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
			"transactTime": time.Now().UnixMilli(),
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	restClient := rest.NewClient(server.URL, signer)
	client, err := NewClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)

	order, err := client.GetOrderByClientID(context.Background(), "BTCUSDT", "market-entry")
	require.NoError(t, err)
	assert.True(t, order.Price.IsZero())
	assert.True(t, decimal.RequireFromString("50020").Equal(order.AverageFillPrice))
}

func TestGetFuturesOrderByClientIDPreservesExchangeAverageFillPrice(t *testing.T) {
	const updateTime = int64(1774116365123)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/fapi/v1/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 42, "clientOrderId": "market-entry",
			"price": "0", "avgPrice": "50020", "origQty": "2", "executedQty": "2",
			"cumQty": "2", "cumQuote": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
			"updateTime": updateTime,
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	restClient := rest.NewClient(server.URL, signer)
	client, err := NewFuturesClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)

	order, err := client.GetOrderByClientID(context.Background(), "BTCUSDT", "market-entry")
	require.NoError(t, err)
	assert.True(t, order.Price.IsZero())
	assert.True(t, decimal.RequireFromString("50020").Equal(order.AverageFillPrice))
	assert.Equal(t, updateTime, order.TransactTime)
}

func TestPlaceSpotOrderPreservesImmediateFillAverageSeparatelyFromPrice(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/api/v3/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 43, "clientOrderId": "spot-market-entry",
			"price": "0", "origQty": "2", "executedQty": "2",
			"cummulativeQuoteQty": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	client, err := NewSpotClient(server.URL, signer, rest.NewClient(server.URL, signer), zerolog.Nop())
	require.NoError(t, err)
	order, err := client.PlaceSpotOrder(context.Background(), SpotOrderRequest{
		Symbol: "BTCUSDT", Side: "BUY", Type: "MARKET",
		Quantity: decimal.NewFromInt(2), NewClientOrderID: "spot-market-entry",
	})
	require.NoError(t, err)
	assert.True(t, order.Price.IsZero())
	assert.True(t, decimal.RequireFromString("50020").Equal(order.AverageFillPrice))
}

func TestPlaceFuturesOrderPreservesImmediateExchangeAverageSeparatelyFromPrice(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/fapi/v1/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 44, "clientOrderId": "futures-market-entry",
			"price": "0", "avgPrice": "50020", "origQty": "2", "executedQty": "2",
			"cumQty": "2", "cumQuote": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	client, err := NewFuturesClient(server.URL, signer, rest.NewClient(server.URL, signer), zerolog.Nop())
	require.NoError(t, err)
	order, err := client.PlaceFuturesOrder(context.Background(), FuturesOrderRequest{
		Symbol: "BTCUSDT", Side: "BUY", Type: "MARKET",
		Quantity: decimal.NewFromInt(2), NewClientOrderID: "futures-market-entry",
	})
	require.NoError(t, err)
	assert.True(t, order.Price.IsZero())
	assert.True(t, decimal.RequireFromString("50020").Equal(order.AverageFillPrice))
}

func TestPlaceFuturesOrderFallsBackToExchangeTransactionTime(t *testing.T) {
	const transactTime = int64(1774116365123)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/fapi/v1/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 44, "clientOrderId": "futures-observed-at",
			"price": "0", "avgPrice": "50020", "origQty": "2", "executedQty": "2",
			"cumQty": "2", "cumQuote": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
			"transactTime": transactTime,
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	client, err := NewFuturesClient(server.URL, signer, rest.NewClient(server.URL, signer), zerolog.Nop())
	require.NoError(t, err)
	order, err := client.PlaceFuturesOrder(context.Background(), FuturesOrderRequest{
		Symbol: "BTCUSDT", Side: "BUY", Type: "MARKET",
		Quantity: decimal.NewFromInt(2), NewClientOrderID: "futures-observed-at",
	})
	require.NoError(t, err)
	assert.Equal(t, transactTime, order.TransactTime)
}

func TestPlaceFuturesOrderFallsBackToCumulativeQuoteForImmediateAverage(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, http.MethodPost, r.Method)
		require.Equal(t, "/fapi/v1/order", r.URL.Path)
		w.Header().Set("Content-Type", "application/json")
		require.NoError(t, json.NewEncoder(w).Encode(map[string]any{
			"symbol": "BTCUSDT", "orderId": 45, "clientOrderId": "futures-market-fallback",
			"price": "0", "avgPrice": "0", "origQty": "2", "executedQty": "2",
			"cumQty": "2", "cumQuote": "100040", "status": "FILLED",
			"timeInForce": "GTC", "type": "MARKET", "side": "BUY",
		}))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	client, err := NewFuturesClient(server.URL, signer, rest.NewClient(server.URL, signer), zerolog.Nop())
	require.NoError(t, err)
	order, err := client.PlaceFuturesOrder(context.Background(), FuturesOrderRequest{
		Symbol: "BTCUSDT", Side: "BUY", Type: "MARKET",
		Quantity: decimal.NewFromInt(2), NewClientOrderID: "futures-market-fallback",
	})
	require.NoError(t, err)
	assert.True(t, order.Price.IsZero())
	assert.True(t, decimal.RequireFromString("50020").Equal(order.AverageFillPrice))
}

func TestNewClient_ValidatesConfiguration(t *testing.T) {
	apiKey, secretKey := getTestCredentials(t)
	signer := auth.NewSigner(apiKey, secretKey)
	restClient := rest.NewClient(testnetSpotURL, signer)
	logger := zerolog.Nop()

	client, err := NewClient(testnetSpotURL, signer, restClient, logger)
	require.NoError(t, err)
	assert.NotNil(t, client)
}

func TestNewClient_RequiresSigner(t *testing.T) {
	apiKey, secretKey := getTestCredentials(t)
	signer := auth.NewSigner(apiKey, secretKey)
	restClient := rest.NewClient(testnetSpotURL, signer)
	logger := zerolog.Nop()

	_, err := NewClient(testnetSpotURL, nil, restClient, logger)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "signer")
}

func TestNewClient_RequiresRestClient(t *testing.T) {
	apiKey, secretKey := getTestCredentials(t)
	signer := auth.NewSigner(apiKey, secretKey)
	logger := zerolog.Nop()

	_, err := NewClient(testnetSpotURL, signer, nil, logger)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "rest client")
}

// TestOrderValidation tests order validation logic
func TestOrderValidation(t *testing.T) {
	client := &Client{
		logger: zerolog.Nop(),
	}

	tests := []struct {
		name    string
		order   SpotOrderRequest
		wantErr string
	}{
		{
			name:    "empty symbol",
			order:   SpotOrderRequest{},
			wantErr: "symbol is required",
		},
		{
			name: "invalid side",
			order: SpotOrderRequest{
				Symbol: "BTCUSDT",
				Side:   "INVALID",
			},
			wantErr: "invalid side",
		},
		{
			name: "invalid order type",
			order: SpotOrderRequest{
				Symbol: "BTCUSDT",
				Side:   "BUY",
				Type:   "INVALID",
			},
			wantErr: "invalid order type",
		},
		{
			name: "zero quantity",
			order: SpotOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "MARKET",
				Quantity: decimal.Zero,
			},
			wantErr: "quantity must be positive",
		},
		{
			name: "limit order without price",
			order: SpotOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "LIMIT",
				Quantity: decimal.NewFromFloat(0.001),
				Price:    decimal.Zero,
			},
			wantErr: "price must be positive for limit orders",
		},
		{
			name: "stop loss without stop price",
			order: SpotOrderRequest{
				Symbol:    "BTCUSDT",
				Side:      "BUY",
				Type:      "STOP_LOSS",
				Quantity:  decimal.NewFromFloat(0.001),
				StopPrice: decimal.Zero,
			},
			wantErr: "stopPrice must be positive",
		},
		{
			name: "valid market order",
			order: SpotOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "MARKET",
				Quantity: decimal.NewFromFloat(0.001),
			},
			wantErr: "",
		},
		{
			name: "valid limit order",
			order: SpotOrderRequest{
				Symbol:      "BTCUSDT",
				Side:        "SELL",
				Type:        "LIMIT",
				Quantity:    decimal.NewFromFloat(0.001),
				Price:       decimal.NewFromFloat(50000),
				TimeInForce: "GTC",
			},
			wantErr: "",
		},
		{
			name: "valid stop loss limit order",
			order: SpotOrderRequest{
				Symbol:      "BTCUSDT",
				Side:        "SELL",
				Type:        "STOP_LOSS_LIMIT",
				Quantity:    decimal.NewFromFloat(0.001),
				Price:       decimal.NewFromFloat(49000),
				StopPrice:   decimal.NewFromFloat(49500),
				TimeInForce: "GTC",
			},
			wantErr: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := client.validateSpotOrder(tt.order)
			if tt.wantErr != "" {
				assert.Error(t, err)
				assert.Contains(t, err.Error(), tt.wantErr)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

// TestAccountInfoCaching tests the caching behavior
func TestAccountInfoCaching(t *testing.T) {
	// Create a client with short cache TTL
	client := &Client{
		accountCacheTTL:   100 * time.Millisecond,
		accountCacheMutex: sync.RWMutex{},
		logger:            zerolog.Nop(),
		restClient:        &rest.Client{}, // Will fail if actually called
	}

	// Set cached data
	testTime := time.Now()
	testAccount := &AccountResponse{
		UpdateTime: testTime.Unix(),
		CanTrade:   true,
		Balances: []Balance{
			{Asset: "BTC", Free: decimal.NewFromFloat(1)},
		},
	}
	client.accountCache = testAccount
	client.accountCacheTime = testTime

	// Should return cached data
	ctx := context.Background()
	account, err := client.GetAccountInfo(ctx)
	require.NoError(t, err)
	assert.Equal(t, testAccount.UpdateTime, account.UpdateTime)

	// Wait for cache to expire
	time.Sleep(150 * time.Millisecond)

	// Should try to fetch new data (will fail with our mock)
	_, err = client.GetAccountInfo(ctx)
	assert.Error(t, err) // Because our mock restClient won't work
}
