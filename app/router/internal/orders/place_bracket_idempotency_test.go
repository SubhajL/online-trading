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

func TestManager_PlaceBracketOrder_ConcurrentSameClientIDPlacesOnce(t *testing.T) {
	var mainPosts atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order" {
			q := r.URL.Query()
			if q.Get("newClientOrderId") == "race_entry" {
				mainPosts.Add(1)
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       1,
				"symbol":        q.Get("symbol"),
				"status":        "NEW",
				"clientOrderId": q.Get("newClientOrderId"),
				"price":         "50000",
				"avgPrice":      "0",
				"origQty":       "0.001",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          q.Get("type"),
			})
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)
	manager := NewManager(nil, futuresClient, nil, logger)

	makeReq := func() *PlaceBracketRequest {
		return &PlaceBracketRequest{
			Symbol:           "BTCUSDT",
			Side:             "SELL",
			Quantity:         decimal.RequireFromString("0.001"),
			EntryPrice:       decimal.RequireFromString("50000"),
			TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
			StopLossPrice:    decimal.RequireFromString("51000"),
			OrderType:        "LIMIT",
			IsFutures:        true,
			ClientOrderIDs: &ClientOrderIDs{
				Main:        "race_entry",
				TakeProfits: []string{"race_tp1"},
				StopLoss:    "race_sl",
			},
		}
	}

	const racers = 8
	var wg sync.WaitGroup
	for i := 0; i < racers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, _ = manager.PlaceBracketOrder(context.Background(), makeReq())
		}()
	}
	wg.Wait()

	// The check-and-reserve write lock guarantees exactly one racer POSTs
	// the main order; the rest observe the reservation or the stored bracket.
	assert.Equal(t, int64(1), mainPosts.Load())
}

func TestManager_PlaceBracketOrder_ReservationReleasedOnFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte(`{"code":-1013,"msg":"Filter failure: PRICE_FILTER"}`))
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
			Main:        "fail_entry",
			TakeProfits: []string{"fail_tp1"},
			StopLoss:    "fail_sl",
		},
	}

	_, err = manager.PlaceBracketOrder(context.Background(), req)
	assert.Error(t, err)

	// A failed placement must not leave a dangling reservation that bricks
	// every retry with "is being placed".
	_, err = manager.PlaceBracketOrder(context.Background(), req)
	assert.Error(t, err)
	assert.NotContains(t, err.Error(), "is being placed")
}

func TestManager_FuturesStopLossSendsClosePositionWithoutReduceOnly(t *testing.T) {
	var slQuery string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order" {
			q := r.URL.Query()
			if q.Get("type") == "STOP_MARKET" {
				slQuery = r.URL.RawQuery
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId":       1,
				"symbol":        q.Get("symbol"),
				"status":        "NEW",
				"clientOrderId": q.Get("newClientOrderId"),
				"price":         "0",
				"avgPrice":      "0",
				"origQty":       "0.001",
				"executedQty":   "0",
				"cumQty":        "0",
				"cumQuote":      "0",
				"timeInForce":   "GTC",
				"type":          q.Get("type"),
			})
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	assert.NoError(t, err)
	manager := NewManager(nil, futuresClient, nil, logger)

	_, err = manager.PlaceBracketOrder(context.Background(), &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "SELL",
		Quantity:         decimal.RequireFromString("0.001"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
		StopLossPrice:    decimal.RequireFromString("51000"),
		OrderType:        "LIMIT",
		IsFutures:        true,
		ClientOrderIDs: &ClientOrderIDs{
			Main:        "cp_entry",
			TakeProfits: []string{"cp_tp1"},
			StopLoss:    "cp_sl",
		},
	})
	assert.NoError(t, err)

	// USD-M rejects closePosition together with reduceOnly (-1106).
	assert.Contains(t, slQuery, "closePosition=true")
	assert.NotContains(t, slQuery, "reduceOnly")
}
