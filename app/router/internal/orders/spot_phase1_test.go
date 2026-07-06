package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
)

type fakeSpotOrderTracker struct {
	mu       sync.Mutex
	called   bool
	requests []SpotReconcileRequest
}

func (f *fakeSpotOrderTracker) Track(req SpotReconcileRequest) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.called = true
	f.requests = append(f.requests, req)
}

func newSpotTestClient(t *testing.T, serverURL string) *binance.Client {
	t.Helper()

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()

	spotRest := rest.NewClient(serverURL, signer)
	spotClient, err := binance.NewSpotClient(serverURL, signer, spotRest, logger)
	require.NoError(t, err)

	spotClient.SetExchangeInfoCache(
		binance.NewExchangeInfoCache(spotRest, nil, time.Hour, logger),
	)

	return spotClient
}

func writeSpotExchangeInfo(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{
		"timezone":"UTC",
		"serverTime":1,
		"symbols":[
			{
				"symbol":"BTCUSDT",
				"status":"TRADING",
				"baseAsset":"BTC",
				"baseAssetPrecision":8,
				"quoteAsset":"USDT",
				"quoteAssetPrecision":8,
				"orderTypes":["LIMIT","MARKET","STOP_LOSS_LIMIT"],
				"icebergAllowed":false,
				"ocoAllowed":false,
				"isSpotTradingAllowed":true,
				"isMarginTradingAllowed":false
			}
		]
	}`))
}

func TestPlaceBracketOrder_SpotImmediateFillEmitsFilled(t *testing.T) {
	var postCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			quantity := q.Get("quantity")
			price := q.Get("price")
			if price == "" {
				price = "0"
			}

			response := map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               price,
				"origQty":             quantity,
				"executedQty":         "0",
				"cummulativeQuoteQty": "0",
				"status":              "NEW",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills":               []map[string]any{},
			}

			if postCalls == 1 {
				response["status"] = "FILLED"
				response["executedQty"] = quantity
				response["cummulativeQuoteQty"] = "1000"
				response["fills"] = []map[string]any{
					{
						"price":           price,
						"qty":             quantity,
						"commission":      "0",
						"commissionAsset": "USDT",
						"tradeId":         1,
					},
				}
			}

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, emitter, zerolog.Nop())

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	require.True(t, emitter.called)
	require.True(t, decimal.RequireFromString("48755").Equal(resp.StopLossLimitPrice))
	var mainUpdate *OrderUpdate
	for _, update := range emitter.updatesSnapshot() {
		if update != nil && update.OrderID == 100 {
			mainUpdate = update
			break
		}
	}
	require.NotNil(t, mainUpdate)
	assert.Equal(t, "FILLED", mainUpdate.Status)
	assert.True(t, decimal.RequireFromString("0.020").Equal(mainUpdate.ExecutedQty))
	assert.Equal(t, int64(100), mainUpdate.OrderID)
	assert.Equal(t, "LIMIT", mainUpdate.OrderType)
}

func TestPlaceBracketOrder_SpotImmediateFillReturnsExecutionSnapshot(t *testing.T) {
	var postCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			price := q.Get("price")
			quantity := q.Get("quantity")
			response := map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               price,
				"origQty":             quantity,
				"executedQty":         quantity,
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills": []map[string]any{
					{
						"price":           price,
						"qty":             quantity,
						"commission":      "0.15",
						"commissionAsset": "USDT",
						"tradeId":         42,
					},
				},
			}

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, emitter, zerolog.Nop())

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	require.Len(t, resp.SpotExecutionSnapshots, 1)

	snapshot := resp.SpotExecutionSnapshots[0]
	assert.Equal(t, "BTCUSDT", snapshot.Symbol)
	assert.Equal(t, "FILLED", snapshot.Status)
	assert.Equal(t, "BUY", snapshot.Side)
	assert.Equal(t, "LIMIT", snapshot.OrderType)
	assert.True(t, decimal.RequireFromString("0.020").Equal(snapshot.ExecutedQty))
	require.Len(t, snapshot.Trades, 1)
	assert.Equal(t, int64(42), snapshot.Trades[0].TradeID)
	assert.True(t, decimal.RequireFromString("0.15").Equal(snapshot.Trades[0].Commission))
	assert.Equal(t, "USDT", snapshot.Trades[0].CommissionAsset)
}

func TestPlaceBracketOrder_SpotTracksAllPlacedLegs(t *testing.T) {
	var postCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			response := map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               q.Get("price"),
				"origQty":             q.Get("quantity"),
				"executedQty":         "0",
				"cummulativeQuoteQty": "0",
				"status":              "NEW",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills":               []map[string]any{},
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	tracker := &fakeSpotOrderTracker{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, emitter, zerolog.Nop())
	manager.SetSpotReconciler(tracker)

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	require.True(t, tracker.called)
	require.Len(t, tracker.requests, 3)

	assert.Equal(t, int64(100), tracker.requests[0].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.Main, tracker.requests[0].ClientOrderID)
	assert.Equal(t, "LIMIT", tracker.requests[0].OrderType)

	assert.Equal(t, int64(200), tracker.requests[1].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.TakeProfits[0], tracker.requests[1].ClientOrderID)
	assert.Equal(t, "LIMIT", tracker.requests[1].OrderType)

	assert.Equal(t, int64(300), tracker.requests[2].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.StopLoss, tracker.requests[2].ClientOrderID)
	assert.Equal(t, "STOP_LOSS_LIMIT", tracker.requests[2].OrderType)
}

func TestPlaceBracketOrder_SpotSkipsTrackingUnplacedExitLegs(t *testing.T) {
	var postCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			if postCalls == 2 {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"take profit rejected"}`))
				return
			}

			response := map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               q.Get("price"),
				"origQty":             q.Get("quantity"),
				"executedQty":         "0",
				"cummulativeQuoteQty": "0",
				"status":              "NEW",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills":               []map[string]any{},
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	tracker := &fakeSpotOrderTracker{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, nil, zerolog.Nop())
	manager.SetSpotReconciler(tracker)

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.NoError(t, err)
	require.NotNil(t, resp)
	require.True(t, tracker.called)
	require.Len(t, tracker.requests, 2)
	assert.Equal(t, int64(100), tracker.requests[0].OrderID)
	assert.Equal(t, int64(300), tracker.requests[1].OrderID)
}

func TestPlaceBracketOrder_SpotStopLossFailureCancelsUnsafeOrders(t *testing.T) {
	var postCalls int
	var deletedOrderIDs []int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			if postCalls == 3 {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"stop loss rejected"}`))
				return
			}

			response := map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               q.Get("price"),
				"origQty":             q.Get("quantity"),
				"executedQty":         "0",
				"cummulativeQuoteQty": "0",
				"status":              "NEW",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills":               []map[string]any{},
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(response)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			orderID, err := strconv.ParseInt(r.URL.Query().Get("orderId"), 10, 64)
			require.NoError(t, err)
			deletedOrderIDs = append(deletedOrderIDs, orderID)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":        r.URL.Query().Get("symbol"),
				"orderId":       orderID,
				"clientOrderId": "canceled",
				"status":        "CANCELED",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, emitter, zerolog.Nop())

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.Error(t, err)
	require.NotNil(t, resp)
	assert.True(t, resp.PartialFailure)
	assert.Contains(t, resp.Errors, "SL: failed to place spot order: PlaceOrder: Binance API error -2010: stop loss rejected")
	assert.Equal(t, []int64{200, 100}, deletedOrderIDs)
	require.True(t, emitter.called)
	var canceledUpdate *OrderUpdate
	for _, update := range emitter.updatesSnapshot() {
		if update != nil && update.Status == "CANCELED" {
			canceledUpdate = update
			break
		}
	}
	require.NotNil(t, canceledUpdate)
	assert.Equal(t, "CANCELED", canceledUpdate.Status)
}

func TestPlaceBracketOrder_SpotStopLossFailureClosesFilledEntry(t *testing.T) {
	var postCalls int
	var deletedOrderIDs []int64
	var compensationSide string
	var compensationType string
	var compensationQty string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			switch postCalls {
			case 1:
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol":              q.Get("symbol"),
					"orderId":             100,
					"clientOrderId":       q.Get("newClientOrderId"),
					"transactTime":        time.Now().UnixMilli(),
					"price":               q.Get("price"),
					"origQty":             q.Get("quantity"),
					"executedQty":         q.Get("quantity"),
					"cummulativeQuoteQty": "1000",
					"status":              "FILLED",
					"timeInForce":         q.Get("timeInForce"),
					"type":                q.Get("type"),
					"side":                q.Get("side"),
					"fills": []map[string]any{
						{
							"price":           q.Get("price"),
							"qty":             q.Get("quantity"),
							"commission":      "0",
							"commissionAsset": "USDT",
							"tradeId":         1,
						},
					},
				})
			case 2:
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol":              q.Get("symbol"),
					"orderId":             200,
					"clientOrderId":       q.Get("newClientOrderId"),
					"transactTime":        time.Now().UnixMilli(),
					"price":               q.Get("price"),
					"origQty":             q.Get("quantity"),
					"executedQty":         "0",
					"cummulativeQuoteQty": "0",
					"status":              "NEW",
					"timeInForce":         q.Get("timeInForce"),
					"type":                q.Get("type"),
					"side":                q.Get("side"),
					"fills":               []map[string]any{},
				})
			case 3:
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"stop loss rejected"}`))
			case 4:
				compensationSide = q.Get("side")
				compensationType = q.Get("type")
				compensationQty = q.Get("quantity")
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol":              q.Get("symbol"),
					"orderId":             300,
					"clientOrderId":       q.Get("newClientOrderId"),
					"transactTime":        time.Now().UnixMilli(),
					"price":               "50010",
					"origQty":             q.Get("quantity"),
					"executedQty":         q.Get("quantity"),
					"cummulativeQuoteQty": "1000",
					"status":              "FILLED",
					"timeInForce":         q.Get("timeInForce"),
					"type":                q.Get("type"),
					"side":                q.Get("side"),
					"fills":               []map[string]any{},
				})
			default:
				t.Fatalf("unexpected POST call %d", postCalls)
			}
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			orderID, err := strconv.ParseInt(r.URL.Query().Get("orderId"), 10, 64)
			require.NoError(t, err)
			deletedOrderIDs = append(deletedOrderIDs, orderID)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":        r.URL.Query().Get("symbol"),
				"orderId":       orderID,
				"clientOrderId": "canceled",
				"status":        "CANCELED",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	manager := NewManager(newSpotTestClient(t, server.URL), nil, nil, zerolog.Nop())

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.Error(t, err)
	require.NotNil(t, resp)
	assert.True(t, resp.PartialFailure)
	assert.Equal(t, []int64{200}, deletedOrderIDs)
	assert.Equal(t, "SELL", compensationSide)
	assert.Equal(t, "MARKET", compensationType)
	assert.True(t, decimal.RequireFromString("0.020").Equal(decimal.RequireFromString(compensationQty)))
	require.Len(t, resp.SpotExecutionSnapshots, 2)
	assert.Equal(t, "FILLED", resp.SpotExecutionSnapshots[0].Status)
	assert.Equal(t, "FILLED", resp.SpotExecutionSnapshots[1].Status)
}

func TestPlaceBracketOrder_SpotSuccessfulCancelClosesResidualFillFromCancelResponse(t *testing.T) {
	var postCalls int
	var deletedOrderIDs []int64
	var compensationQty string
	var compensationSide string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			switch postCalls {
			case 1, 2:
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol":              q.Get("symbol"),
					"orderId":             postCalls * 100,
					"clientOrderId":       q.Get("newClientOrderId"),
					"transactTime":        time.Now().UnixMilli(),
					"price":               q.Get("price"),
					"origQty":             q.Get("quantity"),
					"executedQty":         "0",
					"cummulativeQuoteQty": "0",
					"status":              "NEW",
					"timeInForce":         q.Get("timeInForce"),
					"type":                q.Get("type"),
					"side":                q.Get("side"),
					"fills":               []map[string]any{},
				})
			case 3:
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"stop loss rejected"}`))
			case 4:
				compensationQty = q.Get("quantity")
				compensationSide = q.Get("side")
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol":              q.Get("symbol"),
					"orderId":             300,
					"clientOrderId":       q.Get("newClientOrderId"),
					"transactTime":        time.Now().UnixMilli(),
					"price":               "50010",
					"origQty":             q.Get("quantity"),
					"executedQty":         q.Get("quantity"),
					"cummulativeQuoteQty": "350",
					"status":              "FILLED",
					"timeInForce":         q.Get("timeInForce"),
					"type":                q.Get("type"),
					"side":                q.Get("side"),
					"fills":               []map[string]any{},
				})
			default:
				t.Fatalf("unexpected POST call %d", postCalls)
			}
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			orderID, err := strconv.ParseInt(r.URL.Query().Get("orderId"), 10, 64)
			require.NoError(t, err)
			deletedOrderIDs = append(deletedOrderIDs, orderID)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              r.URL.Query().Get("symbol"),
				"orderId":             orderID,
				"clientOrderId":       "canceled",
				"status":              "CANCELED",
				"executedQty":         "0.007",
				"cummulativeQuoteQty": "350",
				"side":                "BUY",
				"type":                "LIMIT",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	manager := NewManager(newSpotTestClient(t, server.URL), nil, nil, zerolog.Nop())

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.Error(t, err)
	require.NotNil(t, resp)
	assert.True(t, resp.PartialFailure)
	assert.Equal(t, []int64{200, 100}, deletedOrderIDs)
	assert.Equal(t, "SELL", compensationSide)
	assert.True(t, decimal.RequireFromString("0.007").Equal(decimal.RequireFromString(compensationQty)))
	require.Len(t, resp.SpotExecutionSnapshots, 2)
	assert.Equal(t, "CANCELED", resp.SpotExecutionSnapshots[0].Status)
	assert.Equal(t, "FILLED", resp.SpotExecutionSnapshots[1].Status)
}

func TestPlaceBracketOrder_SpotNewStatusTracksForReconciliation(t *testing.T) {
	var postCalls int

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			postCalls++
			q := r.URL.Query()
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              q.Get("symbol"),
				"orderId":             postCalls * 100,
				"clientOrderId":       q.Get("newClientOrderId"),
				"transactTime":        time.Now().UnixMilli(),
				"price":               q.Get("price"),
				"origQty":             q.Get("quantity"),
				"executedQty":         "0",
				"cummulativeQuoteQty": "0",
				"status":              "NEW",
				"timeInForce":         q.Get("timeInForce"),
				"type":                q.Get("type"),
				"side":                q.Get("side"),
				"fills":               []map[string]any{},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	tracker := &fakeSpotOrderTracker{}
	manager := NewManager(newSpotTestClient(t, server.URL), nil, emitter, zerolog.Nop())
	manager.SetSpotReconciler(tracker)

	req := &PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.020"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		OrderType:        "LIMIT",
	}

	resp, err := manager.PlaceBracketOrder(context.Background(), req)
	require.NoError(t, err)
	require.NotNil(t, resp)

	tracker.mu.Lock()
	defer tracker.mu.Unlock()
	require.True(t, tracker.called)
	require.Len(t, tracker.requests, 3)
	assert.Equal(t, "BTCUSDT", tracker.requests[0].Symbol)
	assert.Equal(t, "NEW", tracker.requests[0].InitialStatus)
	assert.Equal(t, int64(100), tracker.requests[0].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.Main, tracker.requests[0].ClientOrderID)
	assert.Equal(t, int64(200), tracker.requests[1].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.TakeProfits[0], tracker.requests[1].ClientOrderID)
	assert.Equal(t, int64(300), tracker.requests[2].OrderID)
	assert.Equal(t, resp.ClientOrderIDs.StopLoss, tracker.requests[2].ClientOrderID)
}
