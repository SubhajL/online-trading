package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func waitForEmitterStatus(t *testing.T, emitter *mockSuccessEmitter, status string) *OrderUpdate {
	t.Helper()

	var update *OrderUpdate
	require.Eventually(t, func() bool {
		called, current := emitter.snapshot()
		if !called || current == nil || current.Status != status {
			return false
		}
		update = current
		return true
	}, time.Second, 10*time.Millisecond)

	require.NotNil(t, update)
	return update
}

func TestSpotReconciler_TracksUntilTerminalStatus(t *testing.T) {
	var getCalls atomic.Int64
	var tradeCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			currentGetCalls := getCalls.Add(1)
			status := "NEW"
			executedQty := "0"
			if currentGetCalls >= 2 {
				status = "FILLED"
				executedQty = "0.020"
			}

			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         executedQty,
				"cummulativeQuoteQty": "1000",
				"status":              status,
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			tradeCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{
					"symbol":          "BTCUSDT",
					"id":              701,
					"orderId":         100,
					"price":           "50010",
					"qty":             "0.020",
					"commission":      "0.10",
					"commissionAsset": "USDT",
					"time":            time.Now().UnixMilli(),
					"isBuyer":         true,
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	ledger := &fakeSpotExecutionLedger{}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerLedger(ledger),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(3),
	)
	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	update := waitForEmitterStatus(t, emitter, "FILLED")

	assert.Equal(t, int64(100), update.OrderID)
	assert.True(t, decimal.RequireFromString("0.020").Equal(update.ExecutedQty))
	assert.GreaterOrEqual(t, getCalls.Load(), int64(2))
	assert.Equal(t, 1, ledger.callCount())
	assert.Equal(t, int64(1), tradeCalls.Load())
	snapshot := ledger.latestSnapshot()
	assert.Equal(t, "FILLED", snapshot.Status)
	require.Len(t, snapshot.Trades, 1)
	assert.Equal(t, int64(701), snapshot.Trades[0].TradeID)
}

func TestSpotReconciler_IgnoresTrackUntilStarted(t *testing.T) {
	var getCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			getCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         "0.020",
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(1),
	)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})
	time.Sleep(20 * time.Millisecond)
	assert.Equal(t, int64(0), getCalls.Load())

	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)
	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	require.Eventually(t, func() bool {
		return getCalls.Load() > 0
	}, time.Second, 10*time.Millisecond)
}

func TestSpotReconciler_EmitSkipsAfterStop(t *testing.T) {
	emitter := &mockSuccessEmitter{}
	reconciler := NewSpotReconciler(nil, emitter, zerolog.Nop())

	reconciler.Start(context.Background())
	reconciler.Stop()

	reconciler.emit(&OrderUpdate{
		EventType:     "order_update.v1",
		Venue:         "SPOT",
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Status:        "FILLED",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Price:         decimal.RequireFromString("50000"),
		Quantity:      decimal.RequireFromString("0.020"),
		ExecutedQty:   decimal.RequireFromString("0.020"),
		UpdateTime:    time.Now(),
	})

	called, update := emitter.snapshot()
	assert.False(t, called)
	assert.Nil(t, update)
}

func TestSpotReconciler_RetriesTerminalPersistenceAfterLedgerFailure(t *testing.T) {
	var getCalls atomic.Int64
	var tradeCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			getCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         "0.020",
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			tradeCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{
					"symbol":          "BTCUSDT",
					"id":              801,
					"orderId":         100,
					"price":           "50000",
					"qty":             "0.020",
					"commission":      "0.10",
					"commissionAsset": "USDT",
					"time":            time.Now().UnixMilli(),
					"isBuyer":         true,
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	ledger := &flakySpotExecutionLedger{remainingFailures: 1}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerLedger(ledger),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(3),
	)
	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	waitForEmitterStatus(t, emitter, "FILLED")

	assert.GreaterOrEqual(t, ledger.callCount(), 2)
	assert.GreaterOrEqual(t, getCalls.Load(), int64(2))
	assert.GreaterOrEqual(t, tradeCalls.Load(), int64(2))
}

func TestSpotReconciler_RetriesWhenTradesLagTerminalStatus(t *testing.T) {
	var getCalls atomic.Int64
	var tradeCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			getCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         "0.020",
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			currentTradeCalls := tradeCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			if currentTradeCalls == 1 {
				_ = json.NewEncoder(w).Encode([]map[string]any{})
				return
			}
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{
					"symbol":          "BTCUSDT",
					"id":              901,
					"orderId":         100,
					"price":           "50010",
					"qty":             "0.020",
					"commission":      "0.10",
					"commissionAsset": "USDT",
					"time":            time.Now().UnixMilli(),
					"isBuyer":         true,
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	ledger := &fakeSpotExecutionLedger{}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerLedger(ledger),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(3),
	)
	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	waitForEmitterStatus(t, emitter, "FILLED")

	assert.GreaterOrEqual(t, getCalls.Load(), int64(2))
	assert.Equal(t, int64(2), tradeCalls.Load())
	assert.Equal(t, 1, ledger.callCount())
	require.Len(t, ledger.latestSnapshot().Trades, 1)
	assert.True(t, decimal.RequireFromString("50010").Equal(emitter.update.Price))
}

func TestSpotReconciler_EmitsTerminalStatusWhenTradesLag(t *testing.T) {
	var tradeCalls atomic.Int64

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         "0.020",
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			tradeCalls.Add(1)
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]any{})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	ledger := &fakeSpotExecutionLedger{}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerLedger(ledger),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(1),
	)
	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	waitForEmitterStatus(t, emitter, "FILLED")

	assert.Equal(t, int64(1), tradeCalls.Load())
	assert.Equal(t, 0, ledger.callCount())
}

func TestSpotReconciler_EmitsTerminalStatusWhenLedgerPersistenceFails(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol":              "BTCUSDT",
				"orderId":             100,
				"clientOrderId":       "cid-1",
				"price":               "50000",
				"origQty":             "0.020",
				"executedQty":         "0.020",
				"cummulativeQuoteQty": "1000",
				"status":              "FILLED",
				"timeInForce":         "GTC",
				"type":                "LIMIT",
				"side":                "BUY",
				"time":                time.Now().UnixMilli(),
				"updateTime":          time.Now().UnixMilli(),
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]any{
				{
					"symbol":          "BTCUSDT",
					"id":              902,
					"orderId":         100,
					"price":           "50010",
					"qty":             "0.020",
					"commission":      "0.10",
					"commissionAsset": "USDT",
					"time":            time.Now().UnixMilli(),
					"isBuyer":         true,
				},
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1,"msg":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	emitter := &mockSuccessEmitter{}
	ledger := &fakeSpotExecutionLedger{err: assert.AnError}
	reconciler := NewSpotReconciler(
		newSpotTestClient(t, server.URL),
		emitter,
		zerolog.Nop(),
		WithSpotReconcilerLedger(ledger),
		WithSpotReconcilerPollInterval(5*time.Millisecond),
		WithSpotReconcilerMaxAttempts(1),
	)
	reconciler.Start(context.Background())
	t.Cleanup(reconciler.Stop)

	reconciler.Track(SpotReconcileRequest{
		Symbol:        "BTCUSDT",
		OrderID:       100,
		ClientOrderID: "cid-1",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Quantity:      decimal.RequireFromString("0.020"),
		Price:         decimal.RequireFromString("50000"),
		InitialStatus: "NEW",
		ExecutedQty:   decimal.Zero,
	})

	waitForEmitterStatus(t, emitter, "FILLED")

	assert.Equal(t, 1, ledger.callCount())
}
