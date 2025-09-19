package rest

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
)

func TestPlaceFuturesOrder_Success(t *testing.T) {
	expectedResponse := &FuturesOrderResponse{
		OrderID:       123456789,
		Symbol:        "BTCUSDT",
		Status:        "NEW",
		ClientOrderID: "test123",
		Price:         decimal.RequireFromString("50000"),
		OrigQty:       decimal.RequireFromString("0.001"),
		ExecutedQty:   decimal.Zero,
		Type:          "LIMIT",
		Side:          "BUY",
		ReduceOnly:    false,
		UpdateTime:    time.Now().UnixMilli(),
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify request
		assert.Equal(t, "POST", r.Method)
		assert.Equal(t, "/fapi/v1/order", r.URL.Path)
		assert.Contains(t, r.URL.RawQuery, "symbol=BTCUSDT")
		assert.Contains(t, r.URL.RawQuery, "side=BUY")
		assert.Contains(t, r.URL.RawQuery, "type=LIMIT")
		assert.Contains(t, r.URL.RawQuery, "quantity=0.001")
		assert.Contains(t, r.URL.RawQuery, "price=50000")
		assert.Contains(t, r.URL.RawQuery, "signature=")
		assert.Equal(t, "test-api-key", r.Header.Get("X-MBX-APIKEY"))

		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(expectedResponse)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &FuturesOrderRequest{
		Symbol:      "BTCUSDT",
		Side:        "BUY",
		Type:        "LIMIT",
		Quantity:    decimal.RequireFromString("0.001"),
		Price:       decimal.RequireFromString("50000"),
		TimeInForce: "GTC",
	}

	resp, err := client.PlaceFuturesOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, expectedResponse.OrderID, resp.OrderID)
	assert.Equal(t, expectedResponse.Symbol, resp.Symbol)
	assert.Equal(t, expectedResponse.ClientOrderID, resp.ClientOrderID)
}

func TestPlaceFuturesOrder_ReduceOnly(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify reduceOnly parameter
		assert.Contains(t, r.URL.RawQuery, "reduceOnly=true")

		resp := &FuturesOrderResponse{
			OrderID:    987654321,
			Symbol:     "BTCUSDT",
			Status:     "NEW",
			ReduceOnly: true,
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &FuturesOrderRequest{
		Symbol:     "BTCUSDT",
		Side:       "SELL",
		Type:       "MARKET",
		Quantity:   decimal.RequireFromString("0.001"),
		ReduceOnly: true,
	}

	resp, err := client.PlaceFuturesOrder(context.Background(), req)
	require.NoError(t, err)
	assert.True(t, resp.ReduceOnly)
}

func TestPlaceFuturesOrder_StopMarket(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify stop market parameters
		assert.Contains(t, r.URL.RawQuery, "type=STOP_MARKET")
		assert.Contains(t, r.URL.RawQuery, "stopPrice=60000")
		assert.Contains(t, r.URL.RawQuery, "closePosition=true")

		resp := &FuturesOrderResponse{
			OrderID:  111222333,
			Symbol:   "BTCUSDT",
			Status:   "NEW",
			Type:     "STOP_MARKET",
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &FuturesOrderRequest{
		Symbol:        "BTCUSDT",
		Side:          "SELL",
		Type:          "STOP_MARKET",
		StopPrice:     decimal.RequireFromString("60000"),
		ClosePosition: true,
	}

	resp, err := client.PlaceFuturesOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, "STOP_MARKET", resp.Type)
}

func TestPlaceFuturesOrder_ValidationErrors(t *testing.T) {
	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient("http://localhost", signer)

	tests := []struct {
		name string
		req  *FuturesOrderRequest
		err  string
	}{
		{
			name: "missing symbol",
			req: &FuturesOrderRequest{
				Side:     "BUY",
				Type:     "MARKET",
				Quantity: decimal.RequireFromString("1"),
			},
			err: "symbol is required",
		},
		{
			name: "missing side",
			req: &FuturesOrderRequest{
				Symbol:   "BTCUSDT",
				Type:     "MARKET",
				Quantity: decimal.RequireFromString("1"),
			},
			err: "side is required",
		},
		{
			name: "missing type",
			req: &FuturesOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Quantity: decimal.RequireFromString("1"),
			},
			err: "type is required",
		},
		{
			name: "zero quantity",
			req: &FuturesOrderRequest{
				Symbol: "BTCUSDT",
				Side:   "BUY",
				Type:   "MARKET",
			},
			err: "quantity is required",
		},
		{
			name: "limit order without price",
			req: &FuturesOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "LIMIT",
				Quantity: decimal.RequireFromString("1"),
			},
			err: "price is required for LIMIT orders",
		},
		{
			name: "stop order without stop price",
			req: &FuturesOrderRequest{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "STOP_MARKET",
				Quantity: decimal.RequireFromString("1"),
			},
			err: "stopPrice is required for STOP",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := client.PlaceFuturesOrder(context.Background(), tt.req)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tt.err)
		})
	}
}

func TestPlaceFuturesOrder_APIError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(BinanceError{
			Code:    -2010,
			Message: "Insufficient balance",
		})
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &FuturesOrderRequest{
		Symbol:   "BTCUSDT",
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.RequireFromString("100"),
	}

	_, err := client.PlaceFuturesOrder(context.Background(), req)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "Insufficient balance")
}

func TestGetFuturesAccount_Success(t *testing.T) {
	expectedResponse := &FuturesAccountResponse{
		TotalWalletBalance:    decimal.RequireFromString("1000.5"),
		TotalUnrealizedProfit: decimal.RequireFromString("50.25"),
		TotalMarginBalance:    decimal.RequireFromString("1050.75"),
		AvailableBalance:      decimal.RequireFromString("900.0"),
		UpdateTime:            time.Now().UnixMilli(),
		Assets: []FuturesAsset{
			{
				Asset:               "USDT",
				WalletBalance:       decimal.RequireFromString("1000.5"),
				UnrealizedProfit:    decimal.RequireFromString("50.25"),
				MarginBalance:       decimal.RequireFromString("1050.75"),
				AvailableBalance:    decimal.RequireFromString("900.0"),
			},
		},
		Positions: []FuturesPosition{
			{
				Symbol:           "BTCUSDT",
				PositionSide:     "BOTH",
				PositionAmt:      decimal.RequireFromString("0.01"),
				UnrealizedProfit: decimal.RequireFromString("50.25"),
				EntryPrice:       decimal.RequireFromString("65000"),
				MarkPrice:        decimal.RequireFromString("70025"),
			},
		},
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "GET", r.Method)
		assert.Equal(t, "/fapi/v2/account", r.URL.Path)
		assert.Contains(t, r.URL.RawQuery, "signature=")

		json.NewEncoder(w).Encode(expectedResponse)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	resp, err := client.GetFuturesAccount(context.Background())
	require.NoError(t, err)
	assert.Equal(t, expectedResponse.TotalWalletBalance.String(), resp.TotalWalletBalance.String())
	assert.Len(t, resp.Assets, 1)
	assert.Len(t, resp.Positions, 1)
}

func TestPlaceFuturesOrder_RetryOn5xx(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts < 3 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}

		// Success on third attempt
		resp := &FuturesOrderResponse{
			OrderID: 999,
			Symbol:  "BTCUSDT",
			Status:  "NEW",
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer, WithMaxRetries(3))

	req := &FuturesOrderRequest{
		Symbol:   "BTCUSDT",
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.RequireFromString("0.001"),
	}

	resp, err := client.PlaceFuturesOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, int64(999), resp.OrderID)
	assert.Equal(t, 3, attempts)
}

func TestPlaceFuturesOrder_TimeSync(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts == 1 {
			// First attempt fails with time sync error
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(BinanceError{
				Code:    -1021,
				Message: "Timestamp for this request is outside of the recvWindow",
			})
			return
		}

		// Second attempt succeeds
		resp := &FuturesOrderResponse{
			OrderID: 888,
			Symbol:  "BTCUSDT",
			Status:  "NEW",
		}
		json.NewEncoder(w).Encode(resp)
	}))
	defer server.Close()

	signer := auth.NewSigner("test-api-key", "test-secret")
	client := NewClient(server.URL, signer)

	req := &FuturesOrderRequest{
		Symbol:   "BTCUSDT",
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.RequireFromString("0.001"),
	}

	resp, err := client.PlaceFuturesOrder(context.Background(), req)
	require.NoError(t, err)
	assert.Equal(t, int64(888), resp.OrderID)
	assert.Equal(t, 2, attempts)
}