package binance

import (
	"context"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestRoundPrice(t *testing.T) {
	tests := []struct {
		name     string
		price    string
		tickSize string
		minPrice string
		maxPrice string
		expected string
	}{
		{
			name:     "round to tick size",
			price:    "100.12345",
			tickSize: "0.01",
			minPrice: "0.01",
			maxPrice: "1000000",
			expected: "100.12",
		},
		{
			name:     "round up to tick size",
			price:    "100.126",
			tickSize: "0.01",
			minPrice: "0.01",
			maxPrice: "1000000",
			expected: "100.13",
		},
		{
			name:     "below min price",
			price:    "0.001",
			tickSize: "0.01",
			minPrice: "0.01",
			maxPrice: "1000000",
			expected: "0.01",
		},
		{
			name:     "above max price",
			price:    "2000000",
			tickSize: "0.01",
			minPrice: "0.01",
			maxPrice: "1000000",
			expected: "1000000",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cache := &ExchangeInfoCache{
				cache: map[string]*SymbolInfo{
					"BTCUSDT": {
						Symbol:    "BTCUSDT",
						TickSize:  decimal.RequireFromString(tt.tickSize),
						MinPrice:  decimal.RequireFromString(tt.minPrice),
						MaxPrice:  decimal.RequireFromString(tt.maxPrice),
						IsFutures: false,
					},
				},
				cacheTime: time.Now(),
				cacheTTL:  time.Hour,
			}

			price := decimal.RequireFromString(tt.price)
			rounded, err := cache.RoundPrice(context.Background(), "BTCUSDT", price, false)

			require.NoError(t, err)
			assert.Equal(t, tt.expected, rounded.String())
		})
	}
}

func TestRoundQuantity(t *testing.T) {
	tests := []struct {
		name        string
		quantity    string
		stepSize    string
		minQuantity string
		maxQuantity string
		expected    string
	}{
		{
			name:        "round to step size",
			quantity:    "1.12345",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			expected:    "1.123",
		},
		{
			name:        "floor to step size",
			quantity:    "1.12399",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			expected:    "1.123",
		},
		{
			name:        "below min quantity",
			quantity:    "0.0001",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			expected:    "0.001",
		},
		{
			name:        "above max quantity",
			quantity:    "10000",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			expected:    "9000",
		},
		{
			name:        "exact step multiple",
			quantity:    "1.5",
			stepSize:    "0.1",
			minQuantity: "0.1",
			maxQuantity: "9000",
			expected:    "1.5",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cache := &ExchangeInfoCache{
				cache: map[string]*SymbolInfo{
					"BTCUSDT": {
						Symbol:      "BTCUSDT",
						StepSize:    decimal.RequireFromString(tt.stepSize),
						MinQuantity: decimal.RequireFromString(tt.minQuantity),
						MaxQuantity: decimal.RequireFromString(tt.maxQuantity),
						IsFutures:   false,
					},
				},
				cacheTime: time.Now(),
				cacheTTL:  time.Hour,
			}

			quantity := decimal.RequireFromString(tt.quantity)
			rounded, err := cache.RoundQuantity(context.Background(), "BTCUSDT", quantity, false)

			require.NoError(t, err)
			assert.Equal(t, tt.expected, rounded.String())
		})
	}
}

func TestValidateNotional(t *testing.T) {
	tests := []struct {
		name        string
		price       string
		quantity    string
		minNotional string
		expectError bool
	}{
		{
			name:        "valid notional",
			price:       "50000",
			quantity:    "0.001",
			minNotional: "10",
			expectError: false,
		},
		{
			name:        "below min notional",
			price:       "50000",
			quantity:    "0.0001",
			minNotional: "10",
			expectError: true,
		},
		{
			name:        "exactly min notional",
			price:       "100",
			quantity:    "0.1",
			minNotional: "10",
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cache := &ExchangeInfoCache{
				cache: map[string]*SymbolInfo{
					"BTCUSDT": {
						Symbol:      "BTCUSDT",
						MinNotional: decimal.RequireFromString(tt.minNotional),
						IsFutures:   false,
					},
				},
				cacheTime: time.Now(),
				cacheTTL:  time.Hour,
			}

			price := decimal.RequireFromString(tt.price)
			quantity := decimal.RequireFromString(tt.quantity)
			err := cache.ValidateNotional(context.Background(), "BTCUSDT", price, quantity, false)

			if tt.expectError {
				assert.Error(t, err)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestCalculatePrecision(t *testing.T) {
	tests := []struct {
		stepSize string
		expected int
	}{
		{"1", 0},
		{"0.1", 1},
		{"0.01", 2},
		{"0.001", 3},
		{"0.00001", 5},
		{"0.00000001", 8},
		{"0", 8}, // Default
	}

	for _, tt := range tests {
		t.Run("step_"+tt.stepSize, func(t *testing.T) {
			stepSize := decimal.RequireFromString(tt.stepSize)
			precision := calculatePrecision(stepSize)
			assert.Equal(t, tt.expected, precision)
		})
	}
}

func TestSymbolValidation(t *testing.T) {
	cache := &ExchangeInfoCache{
		cache: map[string]*SymbolInfo{
			"BTCUSDT": {
				Symbol:    "BTCUSDT",
				IsFutures: false,
			},
			"BTCUSDT-PERP": {
				Symbol:    "BTCUSDT-PERP",
				IsFutures: true,
			},
		},
		cacheTime: time.Now(),
		cacheTTL:  time.Hour,
	}

	// Test spot symbol as spot - should work
	info, err := cache.GetSymbolInfo(context.Background(), "BTCUSDT", false)
	require.NoError(t, err)
	assert.Equal(t, "BTCUSDT", info.Symbol)
	assert.False(t, info.IsFutures)

	// Test futures symbol as futures - should work
	info, err = cache.GetSymbolInfo(context.Background(), "BTCUSDT-PERP", true)
	require.NoError(t, err)
	assert.Equal(t, "BTCUSDT-PERP", info.Symbol)
	assert.True(t, info.IsFutures)

	// Test spot symbol as futures - should fail
	_, err = cache.GetSymbolInfo(context.Background(), "BTCUSDT", true)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "is spot but requested futures")

	// Test unknown symbol - should fail
	_, err = cache.GetSymbolInfo(context.Background(), "UNKNOWN", false)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
}
