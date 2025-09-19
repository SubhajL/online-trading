package orders

import (
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

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
			err := manager.validateBracketRequest(tt.req)
			if tt.wantErr == "" {
				assert.NoError(t, err)
			} else {
				assert.EqualError(t, err, tt.wantErr)
			}
		})
	}
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
