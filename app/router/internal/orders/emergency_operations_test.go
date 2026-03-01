package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
)

func TestManager_CancelOpenOrders_CancelsSpotAndFuturesOrders(t *testing.T) {
	var spotCancelCalls atomic.Int64
	var futuresCancelCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{"symbol": "BTCUSDT", "orderId": 101},
			})
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			spotCancelCalls.Add(1)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/openOrders":
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{"symbol": "BTCUSDT", "orderId": 201},
				{"symbol": "BTCUSDT", "orderId": 202},
			})
		case r.Method == http.MethodDelete && r.URL.Path == "/fapi/v1/order":
			futuresCancelCalls.Add(1)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	spotRest := rest.NewClient(server.URL, signer)
	spotClient, err := binance.NewSpotClient(server.URL, signer, spotRest, logger)
	assert.NoError(t, err)

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(spotClient, futuresClient, nil, logger)

	resp, err := manager.CancelOpenOrders(context.Background(), &CancelOpenOrdersRequest{
		Scope:   EmergencyScopeAll,
		Symbols: []string{"BTCUSDT"},
	})

	assert.NoError(t, err)
	assert.Equal(t, 3, resp.CanceledOrders)
	assert.Empty(t, resp.Errors)
	assert.Equal(t, int64(1), spotCancelCalls.Load())
	assert.Equal(t, int64(2), futuresCancelCalls.Load())
}

func TestManager_ClosePositions_ClosesFuturesPositions(t *testing.T) {
	var futuresCloseCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]any{
					{"symbol": "BTCUSDT", "positionAmt": "0.010"},
					{"symbol": "ETHUSDT", "positionAmt": "0"},
				},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			futuresCloseCalls.Add(1)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       999,
				"symbol":        "BTCUSDT",
				"status":        "NEW",
				"clientOrderId": "close-1",
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          "MARKET",
				"reduceOnly":    true,
				"closePosition": true,
				"side":          "SELL",
				"positionSide":  "BOTH",
				"stopPrice":     "0",
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      "MARKET",
				"updateTime":    1,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope: EmergencyScopeFutures,
	})

	assert.NoError(t, err)
	assert.Equal(t, 1, resp.ClosedPositions)
	assert.Empty(t, resp.Errors)
	assert.Equal(t, int64(1), futuresCloseCalls.Load())
}

func TestManager_ClosePositions_SpotIsNotSupported(t *testing.T) {
	logger := zerolog.Nop()
	manager := NewManager(nil, nil, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope: EmergencyScopeSpot,
	})

	assert.NoError(t, err)
	assert.Equal(t, 0, resp.ClosedPositions)
	assert.Equal(t, []string{"spot position closing not supported"}, resp.Errors)
}

func TestManager_ClosePositions_SymbolFilterAppliesToFuturesPositions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]any{
					{"symbol": "BTCUSDT", "positionAmt": "0.010"},
					{"symbol": "ETHUSDT", "positionAmt": "-0.020"},
				},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       999,
				"symbol":        "BTCUSDT",
				"status":        "NEW",
				"clientOrderId": "close-1",
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          "MARKET",
				"reduceOnly":    true,
				"closePosition": true,
				"side":          "SELL",
				"positionSide":  "BOTH",
				"stopPrice":     "0",
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      "MARKET",
				"updateTime":    1,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope:   EmergencyScopeFutures,
		Symbols: []string{"BTCUSDT"},
	})

	assert.NoError(t, err)
	assert.Equal(t, 1, resp.ClosedPositions)
	assert.Empty(t, resp.Errors)
}

func TestManager_ClosePositions_ClosesShortWithBuy(t *testing.T) {
	var capturedSide string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]any{
					{"symbol": "BTCUSDT", "positionAmt": "-0.010"},
				},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			capturedSide = r.URL.Query().Get("side")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       999,
				"symbol":        "BTCUSDT",
				"status":        "NEW",
				"clientOrderId": "close-1",
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          "MARKET",
				"reduceOnly":    true,
				"closePosition": true,
				"side":          "BUY",
				"positionSide":  "BOTH",
				"stopPrice":     "0",
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      "MARKET",
				"updateTime":    1,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope: EmergencyScopeFutures,
	})

	assert.NoError(t, err)
	assert.Equal(t, 1, resp.ClosedPositions)
	assert.Empty(t, resp.Errors)
	assert.Equal(t, "BUY", capturedSide)
}

func TestManager_ClosePositions_ClosesLongWithSell(t *testing.T) {
	var capturedSide string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]any{
					{"symbol": "BTCUSDT", "positionAmt": "0.010"},
				},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			capturedSide = r.URL.Query().Get("side")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       999,
				"symbol":        "BTCUSDT",
				"status":        "NEW",
				"clientOrderId": "close-1",
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          "MARKET",
				"reduceOnly":    true,
				"closePosition": true,
				"side":          "SELL",
				"positionSide":  "BOTH",
				"stopPrice":     "0",
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      "MARKET",
				"updateTime":    1,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope: EmergencyScopeFutures,
	})

	assert.NoError(t, err)
	assert.Equal(t, 1, resp.ClosedPositions)
	assert.Empty(t, resp.Errors)
	assert.Equal(t, "SELL", capturedSide)
}

func TestManager_ClosePositions_UsesClosePositionQuantityZero(t *testing.T) {
	var capturedQuantity string
	var capturedClosePosition string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]any{
					{"symbol": "BTCUSDT", "positionAmt": "0.010"},
				},
			})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			capturedQuantity = r.URL.Query().Get("quantity")
			capturedClosePosition = r.URL.Query().Get("closePosition")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       999,
				"symbol":        "BTCUSDT",
				"status":        "NEW",
				"clientOrderId": "close-1",
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          "MARKET",
				"reduceOnly":    true,
				"closePosition": true,
				"side":          "SELL",
				"positionSide":  "BOTH",
				"stopPrice":     "0",
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      "MARKET",
				"updateTime":    1,
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	resp, err := manager.ClosePositions(context.Background(), &ClosePositionsRequest{
		Scope: EmergencyScopeFutures,
	})

	assert.NoError(t, err)
	assert.Equal(t, 1, resp.ClosedPositions)
	assert.Empty(t, resp.Errors)
	assert.Equal(t, "true", capturedClosePosition)
	assert.True(t, capturedQuantity == "" || capturedQuantity == decimal.Zero.String())
}
