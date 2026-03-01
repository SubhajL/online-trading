package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
)

func TestManager_PlaceBracketOrder_UsesProvidedClientOrderIDs(t *testing.T) {
	var callCount atomic.Int64
	seen := make([]string, 0, 3)
	var seenMu sync.Mutex

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order" {
			callCount.Add(1)

			q := r.URL.Query()
			clientOrderID := q.Get("newClientOrderId")
			price := q.Get("price")
			if price == "" {
				price = "0"
			}
			quantity := q.Get("quantity")
			if quantity == "" {
				quantity = "0"
			}
			stopPrice := q.Get("stopPrice")
			if stopPrice == "" {
				stopPrice = "0"
			}
			seenMu.Lock()
			seen = append(seen, clientOrderID)
			seenMu.Unlock()

			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       callCount.Load(),
				"symbol":        q.Get("symbol"),
				"status":        "NEW",
				"clientOrderId": clientOrderID,
				"price":         price,
				"avgPrice":      "0",
				"origQty":       quantity,
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   q.Get("timeInForce"),
				"type":          q.Get("type"),
				"reduceOnly":    q.Get("reduceOnly") == "true",
				"closePosition": q.Get("closePosition") == "true",
				"side":          q.Get("side"),
				"positionSide":  "BOTH",
				"stopPrice":     stopPrice,
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      q.Get("type"),
				"updateTime":    1,
			})
			return
		}

		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "SELL",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
		StopLossPrice:    decimal.RequireFromString("51000"),
		OrderType:        "LIMIT",
		IsFutures:        true,
		ClientOrderIDs: &ClientOrderIDs{
			Main:        "abc_entry",
			TakeProfits: []string{"abc_tp1"},
			StopLoss:    "abc_sl",
		},
		Metadata: map[string]any{"signal_id": "sig-1"},
	}

	_, err = manager.PlaceBracketOrder(context.Background(), req)
	assert.NoError(t, err)
	assert.Equal(t, int64(3), callCount.Load())
	assert.Equal(t, []string{"abc_entry", "abc_tp1", "abc_sl"}, seen)
}

func TestManager_PlaceBracketOrder_IsIdempotentByProvidedMainClientOrderID(t *testing.T) {
	var callCount atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order" {
			callCount.Add(1)

			q := r.URL.Query()
			clientOrderID := q.Get("newClientOrderId")
			price := q.Get("price")
			if price == "" {
				price = "0"
			}
			quantity := q.Get("quantity")
			if quantity == "" {
				quantity = "0"
			}
			stopPrice := q.Get("stopPrice")
			if stopPrice == "" {
				stopPrice = "0"
			}

			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       callCount.Load(),
				"symbol":        q.Get("symbol"),
				"status":        "NEW",
				"clientOrderId": clientOrderID,
				"price":         price,
				"avgPrice":      "0",
				"origQty":       quantity,
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   q.Get("timeInForce"),
				"type":          q.Get("type"),
				"reduceOnly":    q.Get("reduceOnly") == "true",
				"closePosition": q.Get("closePosition") == "true",
				"side":          q.Get("side"),
				"positionSide":  "BOTH",
				"stopPrice":     stopPrice,
				"workingType":   "CONTRACT_PRICE",
				"priceProtect":  false,
				"origType":      q.Get("type"),
				"updateTime":    1,
			})
			return
		}

		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"error":"not found"}`))
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "SELL",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
		StopLossPrice:    decimal.RequireFromString("51000"),
		OrderType:        "LIMIT",
		IsFutures:        true,
		ClientOrderIDs: &ClientOrderIDs{
			Main:        "same_entry",
			TakeProfits: []string{"same_tp1"},
			StopLoss:    "same_sl",
		},
		Metadata: map[string]any{"signal_id": "sig-1"},
	}

	first, err := manager.PlaceBracketOrder(context.Background(), req)
	assert.NoError(t, err)
	second, err := manager.PlaceBracketOrder(context.Background(), req)
	assert.NoError(t, err)

	assert.Equal(t, int64(3), callCount.Load())
	assert.Equal(t, first.BracketOrderID, second.BracketOrderID)
	assert.Equal(t, first.ClientOrderIDs, second.ClientOrderIDs)
}
