package orders

import (
	"bytes"
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/binance"
)

// mockFailingEmitter is an EventEmitter that always returns an error
type mockFailingEmitter struct {
	err error
}

func (m *mockFailingEmitter) EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error {
	return m.err
}

// mockSuccessEmitter is an EventEmitter that always succeeds
type mockSuccessEmitter struct {
	mu     sync.Mutex
	called bool
	update *OrderUpdate
}

func (m *mockSuccessEmitter) EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.called = true
	if update == nil {
		m.update = nil
		return nil
	}
	updateCopy := *update
	m.update = &updateCopy
	return nil
}

func (m *mockSuccessEmitter) snapshot() (bool, *OrderUpdate) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.update == nil {
		return m.called, nil
	}
	updateCopy := *m.update
	return m.called, &updateCopy
}

func TestManager_validateBracketRequest(t *testing.T) {
	logger := zerolog.Nop()
	manager := NewManager(nil, nil, nil, logger)

	tests := []struct {
		name    string
		req     *PlaceBracketRequest
		wantErr string
	}{
		{
			name: "valid buy request",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "",
		},
		{
			name: "valid sell request",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "SELL",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
				StopLossPrice:    decimal.RequireFromString("51000"),
			},
			wantErr: "",
		},
		{
			name: "missing idempotency identity",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "idempotency_key is required",
		},
		{
			name: "missing symbol",
			req: &PlaceBracketRequest{
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "symbol is required",
		},
		{
			name: "invalid side",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "INVALID",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "invalid side: INVALID",
		},
		{
			name: "negative quantity",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("-0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "quantity must be positive",
		},
		{
			name: "no take profit prices",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "at least one take profit price is required",
		},
		{
			name: "buy order with SL above entry",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("51000"),
			},
			wantErr: "stop loss must be below entry for buy orders",
		},
		{
			name: "buy order with TP below entry",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "BUY",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "take profit 1 must be above entry for buy orders",
		},
		{
			name: "sell order with SL below entry",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "SELL",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("49000")},
				StopLossPrice:    decimal.RequireFromString("49000"),
			},
			wantErr: "stop loss must be above entry for sell orders",
		},
		{
			name: "sell order with TP above entry",
			req: &PlaceBracketRequest{
				Symbol:           "BTCUSDT",
				Side:             "SELL",
				Quantity:         decimal.RequireFromString("0.001"),
				EntryPrice:       decimal.RequireFromString("50000"),
				TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
				StopLossPrice:    decimal.RequireFromString("51000"),
			},
			wantErr: "take profit 1 must be below entry for sell orders",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.name != "missing idempotency identity" {
				tt.req.IdempotencyKey = "test-request"
				tt.req.ClientOrderIDs = &ClientOrderIDs{
					Main:        "test-entry",
					TakeProfits: []string{"test-tp1"},
					StopLoss:    "test-sl",
				}
			}
			err := manager.validateBracketRequest(tt.req)
			if tt.wantErr == "" {
				assert.NoError(t, err)
			} else {
				assert.EqualError(t, err, tt.wantErr)
			}
		})
	}
}

func TestPlaceBracketRequiresClientOrderIDs(t *testing.T) {
	manager := NewManager(nil, nil, nil, zerolog.Nop())
	req := idempotentBracketRequest()
	req.ClientOrderIDs = nil

	err := manager.validateBracketRequest(req)

	require.EqualError(t, err, "client_order_ids is required")
}

func TestManager_generateClientOrderID(t *testing.T) {
	logger := zerolog.Nop()
	manager := NewManager(nil, nil, nil, logger)

	bracketID := "12345678-1234-1234-1234-123456789012"
	orderType := "MAIN"

	clientOrderID := manager.generateClientOrderID(bracketID, orderType)

	// Check that the ID contains the expected prefix
	assert.Contains(t, clientOrderID, "12345678")
	assert.Contains(t, clientOrderID, "MAIN")

	// Check that IDs are unique
	id1 := manager.generateClientOrderID(bracketID, orderType)
	time.Sleep(time.Nanosecond) // Ensure different timestamp
	id2 := manager.generateClientOrderID(bracketID, orderType)
	assert.NotEqual(t, id1, id2)
}

func TestGetOrderType(t *testing.T) {
	tests := []struct {
		name          string
		requestedType string
		price         decimal.Decimal
		want          string
	}{
		{
			name:          "explicit LIMIT",
			requestedType: "LIMIT",
			price:         decimal.RequireFromString("50000"),
			want:          "LIMIT",
		},
		{
			name:          "explicit MARKET",
			requestedType: "MARKET",
			price:         decimal.RequireFromString("50000"),
			want:          "MARKET",
		},
		{
			name:          "auto detect MARKET with zero price",
			requestedType: "",
			price:         decimal.Zero,
			want:          "MARKET",
		},
		{
			name:          "auto detect LIMIT with non-zero price",
			requestedType: "",
			price:         decimal.RequireFromString("50000"),
			want:          "LIMIT",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := getOrderType(tt.requestedType, tt.price)
			assert.Equal(t, tt.want, got)
		})
	}
}

func TestGetOppositeSide(t *testing.T) {
	tests := []struct {
		name string
		side string
		want string
	}{
		{
			name: "BUY to SELL",
			side: "BUY",
			want: "SELL",
		},
		{
			name: "SELL to BUY",
			side: "SELL",
			want: "BUY",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := getOppositeSide(tt.side)
			assert.Equal(t, tt.want, got)
		})
	}
}

// =============================================================================
// Tests for emitOrderUpdateWithLogging (P1 #3)
// =============================================================================

func TestManager_emitOrderUpdateWithLogging_LogsErrorOnEmitFailure(t *testing.T) {
	// Capture logs in buffer
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	// Create failing emitter
	emitter := &mockFailingEmitter{err: errors.New("connection refused")}
	manager := NewManager(nil, nil, emitter, logger)

	update := &OrderUpdate{
		EventType:     "order_update.v1",
		Symbol:        "ETHUSDT",
		ClientOrderID: "test-order-456",
		Status:        "NEW",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Price:         decimal.RequireFromString("3000"),
		Quantity:      decimal.RequireFromString("0.1"),
		ExecutedQty:   decimal.Zero,
		UpdateTime:    time.Now(),
	}

	// Call the method - should not panic
	manager.emitOrderUpdateWithLogging(context.Background(), update)

	// Verify log contains structured fields
	logOutput := buf.String()
	assert.Contains(t, logOutput, "ETHUSDT", "log should contain symbol")
	assert.Contains(t, logOutput, "test-order-456", "log should contain client_order_id")
	assert.Contains(t, logOutput, "connection refused", "log should contain error message")
	assert.Contains(t, logOutput, "failed to emit order update event", "log should contain failure message")
	assert.Contains(t, logOutput, "order_update.v1", "log should contain event_type")
}

func TestManager_emitOrderUpdateWithLogging_ContinuesOnEmitFailure(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	emitter := &mockFailingEmitter{err: errors.New("network timeout")}
	manager := NewManager(nil, nil, emitter, logger)

	update := &OrderUpdate{
		EventType:     "order_update.v1",
		Symbol:        "BTCUSDT",
		ClientOrderID: "test-order-789",
		Status:        "FILLED",
		Price:         decimal.RequireFromString("50000"),
		Quantity:      decimal.RequireFromString("0.001"),
		ExecutedQty:   decimal.RequireFromString("0.001"),
		UpdateTime:    time.Now(),
	}

	// Should not panic - function should complete gracefully
	require.NotPanics(t, func() {
		manager.emitOrderUpdateWithLogging(context.Background(), update)
	})

	// Error should be logged (we already verified in previous test)
	assert.NotEmpty(t, buf.String(), "error should be logged")
}

func TestManager_emitOrderUpdateWithLogging_SkipsWhenEmitterNil(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	// Create manager with nil emitter
	manager := NewManager(nil, nil, nil, logger)

	update := &OrderUpdate{
		EventType:     "order_update.v1",
		Symbol:        "BTCUSDT",
		ClientOrderID: "test-order-000",
		Status:        "NEW",
		Price:         decimal.RequireFromString("50000"),
		Quantity:      decimal.RequireFromString("0.001"),
		ExecutedQty:   decimal.Zero,
		UpdateTime:    time.Now(),
	}

	// Should not panic
	require.NotPanics(t, func() {
		manager.emitOrderUpdateWithLogging(context.Background(), update)
	})

	// No error should be logged (silent skip)
	assert.Empty(t, buf.String(), "no log should be produced for nil emitter")
}

func TestManager_emitOrderUpdateWithLogging_SkipsWhenUpdateNil(t *testing.T) {
	var buf bytes.Buffer
	logger := zerolog.New(&buf)

	emitter := &mockSuccessEmitter{}
	manager := NewManager(nil, nil, emitter, logger)

	// Should not panic with nil update
	require.NotPanics(t, func() {
		manager.emitOrderUpdateWithLogging(context.Background(), nil)
	})

	// Emitter should not be called
	assert.False(t, emitter.called, "emitter should not be called with nil update")
	assert.Empty(t, buf.String(), "no log should be produced for nil update")
}

func TestManager_emitOrderUpdateWithLogging_CallsEmitterOnSuccess(t *testing.T) {
	logger := zerolog.Nop()

	emitter := &mockSuccessEmitter{}
	manager := NewManager(nil, nil, emitter, logger)

	update := &OrderUpdate{
		EventType:     "order_update.v1",
		Symbol:        "SOLUSDT",
		ClientOrderID: "test-order-sol",
		Status:        "NEW",
		Price:         decimal.RequireFromString("100"),
		Quantity:      decimal.RequireFromString("1"),
		ExecutedQty:   decimal.Zero,
		UpdateTime:    time.Now(),
	}

	manager.emitOrderUpdateWithLogging(context.Background(), update)

	// Emitter should be called with correct update
	assert.True(t, emitter.called, "emitter should be called")
	assert.Equal(t, "SOLUSDT", emitter.update.Symbol)
	assert.Equal(t, "test-order-sol", emitter.update.ClientOrderID)
}

func TestPlaceBracketRejectsUnconfiguredVenueClient(t *testing.T) {
	manager := NewManager(nil, nil, nil, zerolog.Nop())
	spotRequest := &PlaceBracketRequest{
		IdempotencyKey: "missing-client", Symbol: "BTCUSDT", Side: "BUY",
		Quantity: decimal.RequireFromString("0.001"), EntryPrice: decimal.NewFromInt(50000),
		TakeProfitPrices: []decimal.Decimal{decimal.NewFromInt(51000)},
		StopLossPrice:    decimal.NewFromInt(49000),
		ClientOrderIDs: &ClientOrderIDs{
			Main: "missing_entry", TakeProfits: []string{"missing_tp1"}, StopLoss: "missing_sl",
		},
	}
	futuresRequest := *spotRequest
	futuresRequest.IsFutures = true

	_, spotErr := manager.placeBracketOrder(context.Background(), spotRequest)
	_, futuresErr := manager.placeBracketOrder(context.Background(), &futuresRequest)

	require.ErrorContains(t, spotErr, "spot exchange client is not configured")
	require.ErrorContains(t, futuresErr, "futures exchange client is not configured")
}

func TestCountAlgoOrders_CountsOnlyAlgoTypes(t *testing.T) {
	tests := []struct {
		name     string
		types    []string
		wantAlgo int
	}{
		{
			name:     "mixed order types",
			types:    []string{"LIMIT", "STOP_LOSS_LIMIT", "MARKET", "TAKE_PROFIT", "LIMIT"},
			wantAlgo: 2,
		},
		{
			name:     "all algo types",
			types:    []string{"STOP_LOSS", "STOP_LOSS_LIMIT", "TAKE_PROFIT", "TAKE_PROFIT_LIMIT"},
			wantAlgo: 4,
		},
		{
			name:     "no algo orders",
			types:    []string{"LIMIT", "MARKET", "LIMIT_MAKER"},
			wantAlgo: 0,
		},
		{
			name:     "empty",
			types:    []string{},
			wantAlgo: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			orders := make([]*binance.Order, len(tt.types))
			for i, typ := range tt.types {
				orders[i] = &binance.Order{Type: typ, Symbol: "ETHUSDT"}
			}
			count := 0
			for _, o := range orders {
				if algoOrderTypes[o.Type] {
					count++
				}
			}
			assert.Equal(t, tt.wantAlgo, count)
		})
	}
}

func TestGenerateClientOrderID_AllSuffixesWithin36Chars(t *testing.T) {
	logger := zerolog.Nop()
	manager := NewManager(nil, nil, nil, logger)
	bracketID := "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" // 36-char UUID

	suffixes := []string{"MAIN", "SL", "TP1", "TP2", "TP3", "FAILSAFE"}
	binanceRegex := `^[a-zA-Z0-9\-_]{1,36}$`

	for _, suffix := range suffixes {
		t.Run(suffix, func(t *testing.T) {
			id := manager.generateClientOrderID(bracketID, suffix)
			assert.LessOrEqual(t, len(id), 36, "ID %q is %d chars, exceeds 36", id, len(id))
			assert.Regexp(t, binanceRegex, id, "ID %q does not match Binance regex", id)
		})
	}
}

func TestGenerateClientOrderID_Uniqueness(t *testing.T) {
	logger := zerolog.Nop()
	manager := NewManager(nil, nil, nil, logger)
	bracketID := "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

	ids := make(map[string]bool)
	for i := 0; i < 100; i++ {
		id := manager.generateClientOrderID(bracketID, "MAIN")
		assert.False(t, ids[id], "duplicate ID generated: %s", id)
		ids[id] = true
	}
}
