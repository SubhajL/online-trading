package binance

import (
	"context"
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