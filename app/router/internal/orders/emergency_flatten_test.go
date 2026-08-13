package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"sync/atomic"
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

func newEmergencySpotManager(t *testing.T, handler http.Handler) *Manager {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{"positions": []any{}})
		case "/fapi/v1/openOrders":
			_ = json.NewEncoder(w).Encode([]any{})
		default:
			handler.ServeHTTP(w, r)
		}
	}))
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	restClient := rest.NewClient(server.URL, signer)
	client, err := binance.NewSpotClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)
	client.SetExchangeInfoCache(binance.NewExchangeInfoCache(restClient, nil, 0, zerolog.Nop()))
	futuresRestClient := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRestClient, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(client, futuresClient, nil, zerolog.Nop())
	manager.SetExecutionGate(staticExecutionGate{state: "HALTED"})
	manager.SetEmergencyConfig(EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"},
		ProtectedAssets: []string{"USDT"},
		DustMaxUSDT:     decimal.NewFromInt(1),
		FillTimeout:     200 * time.Millisecond,
		MaxPasses:       3,
	})
	return manager
}

func TestEmergencyRequestedVenueRequiresConfiguredClient(t *testing.T) {
	manager := NewManager(nil, nil, nil, zerolog.Nop())
	manager.SetExecutionGate(staticExecutionGate{state: "HALTED"})

	_, spotErr := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "missing-spot",
	})
	_, futuresErr := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeFutures, IdempotencyKey: "missing-futures",
	})
	_, allErr := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeAll, IdempotencyKey: "missing-all",
	})

	require.ErrorContains(t, spotErr, "spot exchange client is not configured")
	require.ErrorContains(t, futuresErr, "futures exchange client is not configured")
	require.ErrorContains(t, allErr, "spot exchange client is not configured")
}

type staticExecutionGate struct{ state string }

func (gate staticExecutionGate) AcquirePlacement(context.Context) (string, func() error, error) {
	return gate.state, func() error { return nil }, nil
}

func (gate staticExecutionGate) AcquireEmergency(context.Context) (string, func() error, error) {
	return gate.state, func() error { return nil }, nil
}

func TestEmergencyAllFlattensUnknownSpotBalance(t *testing.T) {
	var filled atomic.Bool
	var canceled atomic.Int64
	var submitted atomic.Int64

	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			free := "0.010"
			if filled.Load() {
				free = "0"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": free, "locked": "0"}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			orders := []map[string]any{}
			if canceled.Load() == 0 {
				orders = append(orders, map[string]any{
					"symbol": "BTCUSDT", "orderId": 101, "clientOrderId": "unknown_entry",
					"side": "BUY", "type": "LIMIT", "origQty": "0.01", "executedQty": "0",
				})
			}
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			canceled.Add(1)
			_ = json.NewEncoder(w).Encode(map[string]any{"symbol": "BTCUSDT", "orderId": 101})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbols": []map[string]any{{
					"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
					"filters": []map[string]string{
						{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"},
						{"filterType": "MIN_NOTIONAL", "minNotional": "5"},
					},
				}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			submitted.Add(1)
			assert.Equal(t, "BTCUSDT", r.URL.Query().Get("symbol"))
			assert.Equal(t, "SELL", r.URL.Query().Get("side"))
			assert.Equal(t, "MARKET", r.URL.Query().Get("type"))
			time.Sleep(250 * time.Millisecond)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 202, "clientOrderId": r.URL.Query().Get("newClientOrderId"),
				"status": "FILLED", "side": "SELL", "type": "MARKET",
				"origQty": r.URL.Query().Get("quantity"), "executedQty": r.URL.Query().Get("quantity"),
				"price": "0", "cummulativeQuoteQty": "500",
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			assert.NotEmpty(t, r.URL.Query().Get("origClientOrderId"))
			filled.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 202, "clientOrderId": r.URL.Query().Get("origClientOrderId"),
				"status": "FILLED", "side": "SELL", "type": "MARKET",
				"origQty": "0.010", "executedQty": "0.010", "price": "0", "cummulativeQuoteQty": "500",
			})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeAll, IdempotencyKey: "unknown-spot",
	})

	require.NoError(t, err)
	assert.True(t, response.FullyFlattened, "%+v", response)
	assert.Equal(t, 1, response.CanceledOrders)
	assert.Equal(t, 1, response.FlattenedSpotAssets, "%+v", response)
	assert.Equal(t, int64(1), submitted.Load())
	assert.Empty(t, response.Residuals)
	assert.NotEmpty(t, response.Starting.SpotBalances)
	assert.Empty(t, response.Final.SpotBalances)
}

func TestEmergencyResidualAboveThresholdFails(t *testing.T) {
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": "0.010", "locked": "0"}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			_ = json.NewEncoder(w).Encode([]map[string]any{})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbols": []map[string]any{{
					"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
					"filters": []map[string]string{{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"}},
				}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			http.Error(w, `{"code":-2010,"msg":"rejected"}`, http.StatusBadRequest)
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "residual-spot",
	})

	require.NoError(t, err)
	assert.False(t, response.FullyFlattened)
	require.Len(t, response.Residuals, 1)
	assert.Equal(t, "BTC", response.Residuals[0].Asset)
	assert.Equal(t, "500", response.Residuals[0].NotionalUSDT.String())
	assert.False(t, response.Residuals[0].Dust)
	assert.NotEmpty(t, response.Errors)
}

func TestEmergencyFuturesResolvesAcceptedTimeoutWithoutDuplicateClose(t *testing.T) {
	var filled atomic.Bool
	var submitted atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			quantity := "1"
			if filled.Load() {
				quantity = "0"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]string{{
					"symbol": "BTCUSDT", "positionAmt": quantity, "positionSide": "BOTH",
				}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/openOrders":
			_ = json.NewEncoder(w).Encode([]any{})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			submitted.Add(1)
			assert.Equal(t, "1", r.URL.Query().Get("quantity"))
			assert.Equal(t, "true", r.URL.Query().Get("reduceOnly"))
			assert.Empty(t, r.URL.Query().Get("closePosition"))
			assert.Equal(t, "BOTH", r.URL.Query().Get("positionSide"))
			http.Error(w, `{"code":-1007,"msg":"execution status unknown"}`, http.StatusGatewayTimeout)
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/order":
			assert.NotEmpty(t, r.URL.Query().Get("origClientOrderId"))
			filled.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 303,
				"clientOrderId": r.URL.Query().Get("origClientOrderId"),
				"status":        "FILLED", "side": "SELL", "type": "MARKET",
				"origQty": "1", "executedQty": "1", "price": "50000",
			})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	restClient := rest.NewClient(server.URL, signer)
	client, err := binance.NewFuturesClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(nil, client, nil, zerolog.Nop())
	manager.SetExecutionGate(staticExecutionGate{state: "HALTED"})
	manager.SetEmergencyConfig(EmergencyConfig{FillTimeout: 5 * time.Second, MaxPasses: 3})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeFutures, IdempotencyKey: "accepted-timeout-futures",
	})

	require.NoError(t, err)
	assert.True(t, response.FullyFlattened, "%+v", response)
	assert.Equal(t, 1, response.ClosedFuturesPositions)
	assert.Equal(t, int64(1), submitted.Load())
}

func TestEmergencyFuturesHedgeCloseIdentitiesAreDistinct(t *testing.T) {
	longID := emergencyClientOrderID("flatten", "fut", "BTCUSDT:LONG")
	shortID := emergencyClientOrderID("flatten", "fut", "BTCUSDT:SHORT")

	assert.NotEqual(t, longID, shortID)
}

func TestEmergencyCloseFailureRetainsProtectiveOrders(t *testing.T) {
	var canceled atomic.Int64
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{
				"positions": []map[string]string{{
					"symbol": "BTCUSDT", "positionAmt": "1", "positionSide": "BOTH",
				}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/openOrders":
			_ = json.NewEncoder(w).Encode([]map[string]any{{
				"symbol": "BTCUSDT", "orderId": 404, "clientOrderId": "position-sl",
				"side": "SELL", "type": "STOP_MARKET", "origQty": "1", "executedQty": "0",
			}})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			http.Error(w, `{"code":-2010,"msg":"rejected"}`, http.StatusBadRequest)
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/order":
			http.Error(w, `{"code":-2013,"msg":"Order does not exist."}`, http.StatusBadRequest)
		case r.Method == http.MethodDelete && r.URL.Path == "/fapi/v1/order":
			canceled.Add(1)
			_ = json.NewEncoder(w).Encode(map[string]any{"symbol": "BTCUSDT", "orderId": 404})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	restClient := rest.NewClient(server.URL, signer)
	client, err := binance.NewFuturesClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(nil, client, nil, zerolog.Nop())
	manager.SetExecutionGate(staticExecutionGate{state: "HALTED"})
	manager.SetEmergencyConfig(EmergencyConfig{FillTimeout: 50 * time.Millisecond, MaxPasses: 1})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeFutures, IdempotencyKey: "retain-protection",
	})

	require.NoError(t, err)
	assert.False(t, response.FullyFlattened)
	assert.Zero(t, canceled.Load(), "residual exposure must retain its protective exit")
	require.Len(t, response.Final.OpenOrders, 1)
	assert.Equal(t, "EXIT", response.Final.OpenOrders[0].Kind)
}

func TestEmergencyHedgeModeCancelsEntriesAndRetainsMatchingProtection(t *testing.T) {
	var mu sync.Mutex
	canceled := make(map[int64]bool)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v2/account":
			_ = json.NewEncoder(w).Encode(map[string]any{"positions": []map[string]string{
				{"symbol": "BTCUSDT", "positionAmt": "1", "positionSide": "LONG"},
				{"symbol": "BTCUSDT", "positionAmt": "-1", "positionSide": "SHORT"},
			}})
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/openOrders":
			all := []map[string]any{
				{"symbol": "BTCUSDT", "orderId": 601, "clientOrderId": "long-entry", "side": "BUY", "positionSide": "LONG", "type": "STOP_MARKET", "origQty": "1"},
				{"symbol": "BTCUSDT", "orderId": 602, "clientOrderId": "long-stop", "side": "SELL", "positionSide": "LONG", "type": "STOP_MARKET", "origQty": "1"},
				{"symbol": "BTCUSDT", "orderId": 603, "clientOrderId": "short-stop", "side": "BUY", "positionSide": "SHORT", "type": "TAKE_PROFIT_MARKET", "origQty": "1"},
				{"symbol": "BTCUSDT", "orderId": 604, "clientOrderId": "short-entry", "side": "SELL", "positionSide": "SHORT", "type": "TAKE_PROFIT_MARKET", "origQty": "1"},
			}
			mu.Lock()
			orders := make([]map[string]any, 0, len(all))
			for _, order := range all {
				if !canceled[int64(order["orderId"].(int))] {
					orders = append(orders, order)
				}
			}
			mu.Unlock()
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/fapi/v1/order":
			orderID, _ := strconv.ParseInt(r.URL.Query().Get("orderId"), 10, 64)
			mu.Lock()
			canceled[orderID] = true
			mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{"symbol": "BTCUSDT", "orderId": orderID})
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/order":
			http.Error(w, `{"code":-2010,"msg":"rejected"}`, http.StatusBadRequest)
		case r.Method == http.MethodGet && r.URL.Path == "/fapi/v1/order":
			http.Error(w, `{"code":-2013,"msg":"Order does not exist."}`, http.StatusBadRequest)
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	restClient := rest.NewClient(server.URL, signer)
	client, err := binance.NewFuturesClient(server.URL, signer, restClient, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(nil, client, nil, zerolog.Nop())
	manager.SetExecutionGate(staticExecutionGate{state: "HALTED"})
	manager.SetEmergencyConfig(EmergencyConfig{FillTimeout: 50 * time.Millisecond, MaxPasses: 1})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeFutures, IdempotencyKey: "hedge-classification",
	})

	require.NoError(t, err)
	assert.False(t, response.FullyFlattened)
	mu.Lock()
	assert.Equal(t, map[int64]bool{601: true, 604: true}, canceled)
	mu.Unlock()
	require.Len(t, response.Final.OpenOrders, 2)
	for _, order := range response.Final.OpenOrders {
		assert.Equal(t, "EXIT", order.Kind)
	}
}

func TestEmergencySpotCloseFailureRetainsProtectiveOrders(t *testing.T) {
	var canceled atomic.Int64
	var protectionOpen atomic.Bool
	var restored atomic.Int64
	protectionOpen.Store(true)
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			free, locked := "0.01", "0"
			if protectionOpen.Load() {
				free, locked = "0", "0.01"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": free, "locked": locked}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			orders := []map[string]any{}
			if protectionOpen.Load() {
				orders = append(orders, map[string]any{
					"symbol": "BTCUSDT", "orderId": 405, "orderListId": 700,
					"clientOrderId": "position-tp", "side": "SELL", "type": "LIMIT_MAKER",
					"price": "51000", "timeInForce": "GTC", "origQty": "0.01", "executedQty": "0",
				}, map[string]any{
					"symbol": "BTCUSDT", "orderId": 406, "orderListId": 700,
					"clientOrderId": "position-stop", "side": "SELL", "type": "STOP_LOSS_LIMIT",
					"price": "49000", "stopPrice": "49500", "timeInForce": "GTC",
					"origQty": "0.01", "executedQty": "0",
				})
			}
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			canceled.Add(1)
			protectionOpen.Store(false)
			_ = json.NewEncoder(w).Encode(map[string]any{"symbol": "BTCUSDT", "orderId": 405})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{"symbols": []map[string]any{{
				"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
				"filters": []map[string]string{{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"}},
			}}})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			http.Error(w, `{"code":-2010,"msg":"rejected"}`, http.StatusBadRequest)
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/orderList/oco":
			restored.Add(1)
			protectionOpen.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderListId": 701, "listClientOrderId": r.URL.Query().Get("listClientOrderId"),
				"listOrderStatus": "EXECUTING",
				"orders": []map[string]any{
					{"symbol": "BTCUSDT", "orderId": 407, "clientOrderId": r.URL.Query().Get("aboveClientOrderId")},
					{"symbol": "BTCUSDT", "orderId": 408, "clientOrderId": r.URL.Query().Get("belowClientOrderId")},
				},
				"orderReports": []map[string]any{
					{"symbol": "BTCUSDT", "orderId": 407, "clientOrderId": r.URL.Query().Get("aboveClientOrderId"), "status": "NEW"},
					{"symbol": "BTCUSDT", "orderId": 408, "clientOrderId": r.URL.Query().Get("belowClientOrderId"), "status": "NEW"},
				},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			http.Error(w, `{"code":-2013,"msg":"Order does not exist."}`, http.StatusBadRequest)
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	manager.SetEmergencyConfig(EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"}, ProtectedAssets: []string{"USDT"},
		DustMaxUSDT: decimal.NewFromInt(1), FillTimeout: 5 * time.Second, MaxPasses: 1,
	})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "retain-spot-protection",
	})

	require.NoError(t, err)
	assert.False(t, response.FullyFlattened)
	assert.Equal(t, int64(1), canceled.Load(), "one cancel request must unlock the OCO pair")
	assert.Equal(t, int64(1), restored.Load(), "a rejected close must restore protection: %+v", response)
	require.Len(t, response.Final.OpenOrders, 2)
	for _, order := range response.Final.OpenOrders {
		assert.Equal(t, "EXIT", order.Kind)
	}
}

func TestEmergencySpotUnlocksProtectionBeforeSuccessfulClose(t *testing.T) {
	var protectionOpen atomic.Bool
	var filled atomic.Bool
	var canceled atomic.Int64
	protectionOpen.Store(true)
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			free, locked := "0.01", "0"
			if protectionOpen.Load() {
				free, locked = "0", "0.01"
			}
			if filled.Load() {
				free, locked = "0", "0"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": free, "locked": locked}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			orders := []map[string]any{}
			if protectionOpen.Load() {
				orders = append(orders, map[string]any{
					"symbol": "BTCUSDT", "orderId": 501, "orderListId": -1,
					"clientOrderId": "locked-stop", "side": "SELL", "type": "STOP_LOSS_LIMIT",
					"price": "49000", "stopPrice": "49500", "timeInForce": "GTC",
					"origQty": "0.01", "executedQty": "0",
				})
			}
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			canceled.Add(1)
			protectionOpen.Store(false)
			_ = json.NewEncoder(w).Encode(map[string]any{"symbol": "BTCUSDT", "orderId": 501})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{"symbols": []map[string]any{{
				"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
				"filters": []map[string]string{{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"}},
			}}})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			filled.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 502,
				"clientOrderId": r.URL.Query().Get("newClientOrderId"), "status": "FILLED",
				"side": "SELL", "type": "MARKET", "origQty": "0.01", "executedQty": "0.01",
			})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	manager.SetEmergencyConfig(EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"}, ProtectedAssets: []string{"USDT"},
		DustMaxUSDT: decimal.NewFromInt(1), FillTimeout: 2 * time.Second, MaxPasses: 1,
	})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "unlock-protection",
	})

	require.NoError(t, err)
	assert.True(t, response.FullyFlattened)
	assert.Equal(t, int64(1), canceled.Load())
	assert.Equal(t, 1, response.FlattenedSpotAssets, "%+v", response)
}

func TestEmergencySpotResolvesLostProtectiveCancelResponseBeforeClosing(t *testing.T) {
	var protectionOpen atomic.Bool
	var filled atomic.Bool
	var closeRequests atomic.Int64
	protectionOpen.Store(true)
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			free, locked := "0.01", "0"
			if protectionOpen.Load() {
				free, locked = "0", "0.01"
			}
			if filled.Load() {
				free, locked = "0", "0"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": free, "locked": locked}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			orders := []map[string]any{}
			if protectionOpen.Load() {
				orders = append(orders, map[string]any{
					"symbol": "BTCUSDT", "orderId": 551, "orderListId": -1,
					"clientOrderId": "lost-cancel-stop", "side": "SELL", "type": "STOP_LOSS_LIMIT",
					"price": "49000", "stopPrice": "49500", "timeInForce": "GTC",
					"origQty": "0.01", "executedQty": "0",
				})
			}
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			protectionOpen.Store(false)
			connection, _, hijackErr := w.(http.Hijacker).Hijack()
			require.NoError(t, hijackErr)
			require.NoError(t, connection.Close())
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{"symbols": []map[string]any{{
				"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
				"filters": []map[string]string{{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"}},
			}}})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			closeRequests.Add(1)
			filled.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 552,
				"clientOrderId": r.URL.Query().Get("newClientOrderId"), "status": "FILLED",
				"side": "SELL", "type": "MARKET", "origQty": "0.01", "executedQty": "0.01",
			})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	manager.SetEmergencyConfig(EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"}, ProtectedAssets: []string{"USDT"},
		DustMaxUSDT: decimal.NewFromInt(1), FillTimeout: 2 * time.Second, MaxPasses: 1,
	})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "lost-protection-cancel-response",
	})

	require.NoError(t, err)
	assert.True(t, response.FullyFlattened)
	assert.Equal(t, int64(1), closeRequests.Load())
	assert.Equal(t, 1, response.FlattenedSpotAssets, "%+v", response)
}

func TestEmergencySpotRestoresProtectionWhenCancelReconciliationAlsoFails(t *testing.T) {
	var protectionOpen atomic.Bool
	var cancelAttempted atomic.Bool
	var reconciliationFailed atomic.Bool
	var restored atomic.Int64
	protectionOpen.Store(true)
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/account":
			free, locked := "0.01", "0"
			if protectionOpen.Load() {
				free, locked = "0", "0.01"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"canTrade": true,
				"balances": []map[string]string{{"asset": "BTC", "free": free, "locked": locked}},
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/openOrders":
			if cancelAttempted.Load() && reconciliationFailed.CompareAndSwap(false, true) {
				http.Error(w, "temporary exchange failure", http.StatusServiceUnavailable)
				return
			}
			orders := []map[string]any{}
			if protectionOpen.Load() {
				orders = append(orders, map[string]any{
					"symbol": "BTCUSDT", "orderId": 571, "orderListId": -1,
					"clientOrderId": "restore-after-unresolved-cancel", "side": "SELL",
					"type": "STOP_LOSS_LIMIT", "price": "49000", "stopPrice": "49500",
					"timeInForce": "GTC", "origQty": "0.01", "executedQty": "0",
				})
			}
			_ = json.NewEncoder(w).Encode(orders)
		case r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order":
			cancelAttempted.Store(true)
			protectionOpen.Store(false)
			connection, _, hijackErr := w.(http.Hijacker).Hijack()
			require.NoError(t, hijackErr)
			require.NoError(t, connection.Close())
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			_ = json.NewEncoder(w).Encode(map[string]any{"symbols": []map[string]any{{
				"symbol": "BTCUSDT", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT",
				"filters": []map[string]string{{"filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100", "stepSize": "0.00001"}},
			}}})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/ticker/price":
			_ = json.NewEncoder(w).Encode([]map[string]string{{"symbol": "BTCUSDT", "price": "50000"}})
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			restored.Add(1)
			protectionOpen.Store(true)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 572,
				"clientOrderId": r.URL.Query().Get("newClientOrderId"), "status": "NEW",
				"side": "SELL", "type": "STOP_LOSS_LIMIT", "origQty": "0.01", "executedQty": "0",
			})
		default:
			http.Error(w, r.Method+" "+r.URL.Path, http.StatusNotFound)
		}
	}))
	manager.SetEmergencyConfig(EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"}, ProtectedAssets: []string{"USDT"},
		DustMaxUSDT: decimal.NewFromInt(1), FillTimeout: 2 * time.Second, MaxPasses: 1,
	})

	response, err := manager.EmergencyFlatten(context.Background(), &EmergencyFlattenRequest{
		Scope: EmergencyScopeSpot, IdempotencyKey: "restore-unresolved-protection-cancel",
	})

	require.NoError(t, err)
	assert.False(t, response.FullyFlattened)
	assert.True(t, reconciliationFailed.Load())
	assert.Equal(t, int64(1), restored.Load())
	require.Len(t, response.Final.OpenOrders, 1)
	assert.Equal(t, "EXIT", response.Final.OpenOrders[0].Kind)
}

func TestCancelOrderOutboxFailureDoesNotReturnSuccess(t *testing.T) {
	manager := newEmergencySpotManager(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete && r.URL.Path == "/api/v3/order" {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 42, "clientOrderId": "cancel-me",
			})
			return
		}
		http.Error(w, "not found", http.StatusNotFound)
	}))
	manager.eventEmitter = &mockFailingEmitter{err: assert.AnError}

	err := manager.CancelOrder(context.Background(), &CancelRequest{
		Symbol: "BTCUSDT", OrderID: 42, ClientOrderID: "cancel-me",
	})

	var durabilityErr *ExecutionDurabilityError
	require.ErrorAs(t, err, &durabilityErr)
}
