package rest

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
)

func TestPlaceOrder_StopLossLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify stop order parameters
		assert.Equal(t, "POST", r.Method)
		assert.Equal(t, "/api/v3/order", r.URL.Path)
		assert.Contains(t, r.URL.RawQuery, "symbol=BTCUSDT")
		assert.Contains(t, r.URL.RawQuery, "side=SELL")
		assert.Contains(t, r.URL.RawQuery, "type=STOP_LOSS_LIMIT")
		assert.Contains(t, r.URL.RawQuery, "quantity=0.001")
		assert.Contains(t, r.URL.RawQuery, "price=59900")     // Limit price
		assert.Contains(t, r.URL.RawQuery, "stopPrice=60000") // Stop trigger price
		assert.Contains(t, r.URL.RawQuery, "timeInForce=GTC")

		resp := &OrderResponse{
			OrderID:       123456789,
			Symbol:        "BTCUSDT",
			Status:        "NEW",
			ClientOrderID: "test_stop_123",
			Type:          "STOP_LOSS_LIMIT",
			Side:          "SELL",
			Price:         decimal.RequireFromString("59900"),
			OrigQty:       decimal.RequireFromString("0.001"),
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &OrderRequest{
		Symbol:           "BTCUSDT",
		Side:             "SELL",
		Type:             "STOP_LOSS_LIMIT",
		Quantity:         decimal.RequireFromString("0.001"),
		Price:            decimal.RequireFromString("59900"), // Limit price (slightly below stop)
		StopPrice:        decimal.RequireFromString("60000"), // Stop trigger price
		TimeInForce:      "GTC",
		NewClientOrderID: "test_stop_123",
	}

	resp, err := client.PlaceOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, "STOP_LOSS_LIMIT", resp.Type)
	assert.Equal(t, "59900", resp.Price.String())
}

func TestPlaceOrder_TakeProfitLimit(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify take profit order parameters
		assert.Contains(t, r.URL.RawQuery, "type=TAKE_PROFIT_LIMIT")
		assert.Contains(t, r.URL.RawQuery, "price=71000")     // Limit price
		assert.Contains(t, r.URL.RawQuery, "stopPrice=70000") // Stop trigger price

		resp := &OrderResponse{
			OrderID: 987654321,
			Symbol:  "BTCUSDT",
			Status:  "NEW",
			Type:    "TAKE_PROFIT_LIMIT",
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &OrderRequest{
		Symbol:      "BTCUSDT",
		Side:        "SELL",
		Type:        "TAKE_PROFIT_LIMIT",
		Quantity:    decimal.RequireFromString("0.001"),
		Price:       decimal.RequireFromString("71000"), // Limit price (above trigger)
		StopPrice:   decimal.RequireFromString("70000"), // Trigger price
		TimeInForce: "GTC",
	}

	resp, err := client.PlaceOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, "TAKE_PROFIT_LIMIT", resp.Type)
}

func TestPlaceOrder_StopLossLimitValidation(t *testing.T) {
	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient("http://localhost", signer)

	tests := []struct {
		name string
		req  *OrderRequest
		err  string
	}{
		{
			name: "stop loss limit without stop price",
			req: &OrderRequest{
				Symbol:      "BTCUSDT",
				Side:        "SELL",
				Type:        "STOP_LOSS_LIMIT",
				Quantity:    decimal.RequireFromString("0.001"),
				Price:       decimal.RequireFromString("59900"),
				TimeInForce: "GTC",
			},
			err: "stopPrice is required for STOP",
		},
		{
			name: "stop loss limit without limit price",
			req: &OrderRequest{
				Symbol:      "BTCUSDT",
				Side:        "SELL",
				Type:        "STOP_LOSS_LIMIT",
				Quantity:    decimal.RequireFromString("0.001"),
				StopPrice:   decimal.RequireFromString("60000"),
				TimeInForce: "GTC",
			},
			err: "price is required for STOP_LOSS_LIMIT",
		},
		{
			name: "stop market without stop price",
			req: &OrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "SELL",
				Type:     "STOP_MARKET",
				Quantity: decimal.RequireFromString("0.001"),
			},
			err: "stopPrice is required for STOP",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := client.PlaceOrder(context.Background(), tt.req)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tt.err)
		})
	}
}
