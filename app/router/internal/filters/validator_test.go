package filters

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

func TestNewSymbolValidator(t *testing.T) {
	t.Run("creates validator with symbol filters", func(t *testing.T) {
		filters := []SymbolFilter{
			{
				Symbol:     "BTCUSDT",
				BaseAsset:  "BTC",
				QuoteAsset: "USDT",
				Filters: []Filter{
					&PriceFilter{
						MinPrice: decimal.NewFromFloat(0.01),
						MaxPrice: decimal.NewFromFloat(1000000),
						TickSize: decimal.NewFromFloat(0.01),
					},
				},
			},
		}

		validator := NewSymbolValidator(filters)
		assert.NotNil(t, validator)
	})

	t.Run("validates filter consistency", func(t *testing.T) {
		filters := []SymbolFilter{
			{
				Symbol: "BTCUSDT",
				Filters: []Filter{
					&PriceFilter{
						MinPrice: decimal.NewFromFloat(100),
						MaxPrice: decimal.NewFromFloat(10), // Invalid: max < min
						TickSize: decimal.NewFromFloat(0.01),
					},
				},
			},
		}

		validator := NewSymbolValidator(filters)
		assert.NotNil(t, validator)
		// Should log warning but not fail
	})
}

func TestValidateOrder_AllFilterTypes(t *testing.T) {
	validator := setupTestValidator()

	t.Run("validates against all filter types", func(t *testing.T) {
		order := Order{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Price:    decimal.NewFromFloat(50000.00),
			Quantity: decimal.NewFromFloat(0.001),
		}

		err := validator.ValidateOrder(order)
		assert.NoError(t, err)
	})
}

func TestValidateOrder_InvalidPrice(t *testing.T) {
	validator := setupTestValidator()

	testCases := []struct {
		name  string
		price decimal.Decimal
		error string
	}{
		{
			name:  "price not matching tick size",
			price: decimal.NewFromFloat(50000.123), // tick size is 0.01
			error: "price precision",
		},
		{
			name:  "price below minimum",
			price: decimal.NewFromFloat(0.001),
			error: "price below minimum",
		},
		{
			name:  "price above maximum",
			price: decimal.NewFromFloat(10000000),
			error: "price above maximum",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			order := Order{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "LIMIT",
				Price:    tc.price,
				Quantity: decimal.NewFromFloat(0.001),
			}

			err := validator.ValidateOrder(order)
			assert.Error(t, err)
			assert.Contains(t, err.Error(), tc.error)
		})
	}
}

func TestValidateOrder_InvalidQuantity(t *testing.T) {
	validator := setupTestValidator()

	testCases := []struct {
		name     string
		quantity decimal.Decimal
		error    string
	}{
		{
			name:     "quantity not matching step size",
			quantity: decimal.NewFromFloat(0.00012345), // step size is 0.00001
			error:    "quantity precision",
		},
		{
			name:     "quantity below minimum",
			quantity: decimal.NewFromFloat(0.00001),
			error:    "quantity below minimum",
		},
		{
			name:     "quantity above maximum",
			quantity: decimal.NewFromFloat(10000),
			error:    "quantity above maximum",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			order := Order{
				Symbol:   "BTCUSDT",
				Side:     "BUY",
				Type:     "LIMIT",
				Price:    decimal.NewFromFloat(50000),
				Quantity: tc.quantity,
			}

			err := validator.ValidateOrder(order)
			assert.Error(t, err)
			assert.Contains(t, err.Error(), tc.error)
		})
	}
}

func TestValidateOrder_BelowMinNotional(t *testing.T) {
	validator := setupTestValidator()

	t.Run("rejects orders below minimum notional", func(t *testing.T) {
		order := Order{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Price:    decimal.NewFromFloat(50000),
			Quantity: decimal.NewFromFloat(0.0001), // 5 USDT, below min of 10
		}

		err := validator.ValidateOrder(order)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "minimum notional")
	})

	t.Run("accepts orders at minimum notional", func(t *testing.T) {
		order := Order{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Price:    decimal.NewFromFloat(50000),
			Quantity: decimal.NewFromFloat(0.0002), // Exactly 10 USDT
		}

		err := validator.ValidateOrder(order)
		assert.NoError(t, err)
	})
}

func TestRoundPrice_VariousTickSizes(t *testing.T) {
	validator := setupTestValidator()

	testCases := []struct {
		name     string
		symbol   string
		price    decimal.Decimal
		expected decimal.Decimal
	}{
		{
			name:     "rounds down to tick size 0.01",
			symbol:   "BTCUSDT",
			price:    decimal.NewFromFloat(50000.12345),
			expected: decimal.NewFromFloat(50000.12),
		},
		{
			name:     "already rounded",
			symbol:   "BTCUSDT",
			price:    decimal.NewFromFloat(50000.50),
			expected: decimal.NewFromFloat(50000.50),
		},
		{
			name:     "rounds to integer for tick size 1",
			symbol:   "BNBUSDT",
			price:    decimal.NewFromFloat(250.99),
			expected: decimal.NewFromFloat(250),
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := validator.RoundPrice(tc.symbol, tc.price)
			assert.True(t, tc.expected.Equal(result),
				"expected %s, got %s", tc.expected, result)
		})
	}
}

func TestRoundQuantity_VariousStepSizes(t *testing.T) {
	validator := setupTestValidator()

	testCases := []struct {
		name     string
		symbol   string
		quantity decimal.Decimal
		expected decimal.Decimal
	}{
		{
			name:     "rounds down to step size 0.00001",
			symbol:   "BTCUSDT",
			quantity: decimal.NewFromFloat(0.12345678),
			expected: decimal.NewFromFloat(0.12345),
		},
		{
			name:     "already rounded",
			symbol:   "BTCUSDT",
			quantity: decimal.NewFromFloat(1.00000),
			expected: decimal.NewFromFloat(1.00000),
		},
		{
			name:     "rounds to step size 0.001",
			symbol:   "ETHUSDT",
			quantity: decimal.NewFromFloat(1.23456),
			expected: decimal.NewFromFloat(1.234),
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := validator.RoundQuantity(tc.symbol, tc.quantity)
			assert.True(t, tc.expected.Equal(result),
				"expected %s, got %s", tc.expected, result)
		})
	}
}

func TestSymbolValidator_UnknownSymbol(t *testing.T) {
	validator := setupTestValidator()

	t.Run("handles unknown symbols gracefully", func(t *testing.T) {
		order := Order{
			Symbol:   "UNKNOWN",
			Side:     "BUY",
			Type:     "LIMIT",
			Price:    decimal.NewFromFloat(100),
			Quantity: decimal.NewFromFloat(1),
		}

		err := validator.ValidateOrder(order)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "unknown symbol")
	})

	t.Run("returns zero for unknown symbol rounding", func(t *testing.T) {
		price := validator.RoundPrice("UNKNOWN", decimal.NewFromFloat(100))
		assert.True(t, price.IsZero())

		qty := validator.RoundQuantity("UNKNOWN", decimal.NewFromFloat(1))
		assert.True(t, qty.IsZero())
	})
}

func TestGetSymbolFilters(t *testing.T) {
	validator := setupTestValidator()

	t.Run("returns filters for known symbol", func(t *testing.T) {
		filters, err := validator.GetSymbolFilters("BTCUSDT")
		assert.NoError(t, err)
		assert.NotEmpty(t, filters)
		assert.GreaterOrEqual(t, len(filters), 3) // price, lot, notional
	})

	t.Run("errors for unknown symbol", func(t *testing.T) {
		filters, err := validator.GetSymbolFilters("UNKNOWN")
		assert.Error(t, err)
		assert.Nil(t, filters)
		assert.Contains(t, err.Error(), "symbol not found")
	})
}

func TestSymbolValidator_ConcurrentAccess(t *testing.T) {
	validator := setupTestValidator()

	t.Run("thread-safe for concurrent validation", func(t *testing.T) {
		done := make(chan bool)
		orders := []Order{
			{Symbol: "BTCUSDT", Side: "BUY", Type: "LIMIT",
				Price: decimal.NewFromFloat(50000), Quantity: decimal.NewFromFloat(0.001)},
			{Symbol: "ETHUSDT", Side: "SELL", Type: "LIMIT",
				Price: decimal.NewFromFloat(3000), Quantity: decimal.NewFromFloat(0.01)},
			{Symbol: "BNBUSDT", Side: "BUY", Type: "MARKET",
				Price: decimal.Zero, Quantity: decimal.NewFromFloat(1)},
		}

		// Run concurrent validations
		for i := 0; i < 100; i++ {
			go func(idx int) {
				order := orders[idx%len(orders)]
				err := validator.ValidateOrder(order)
				// Some orders should pass, some might fail
				_ = err
				done <- true
			}(i)
		}

		// Wait for all goroutines
		for i := 0; i < 100; i++ {
			<-done
		}
		// Should complete without panic
	})
}

// Helper function to set up test validator
func setupTestValidator() *SymbolValidator {
	filters := []SymbolFilter{
		{
			Symbol:     "BTCUSDT",
			BaseAsset:  "BTC",
			QuoteAsset: "USDT",
			Filters: []Filter{
				&PriceFilter{
					MinPrice: decimal.NewFromFloat(0.01),
					MaxPrice: decimal.NewFromFloat(1000000),
					TickSize: decimal.NewFromFloat(0.01),
				},
				&LotSizeFilter{
					MinQty:   decimal.NewFromFloat(0.0001),
					MaxQty:   decimal.NewFromFloat(9000),
					StepSize: decimal.NewFromFloat(0.00001),
				},
				&MinNotionalFilter{
					MinNotional:   decimal.NewFromFloat(10),
					ApplyToMarket: true,
					AvgPriceMins:  5,
				},
			},
		},
		{
			Symbol:     "ETHUSDT",
			BaseAsset:  "ETH",
			QuoteAsset: "USDT",
			Filters: []Filter{
				&PriceFilter{
					MinPrice: decimal.NewFromFloat(0.01),
					MaxPrice: decimal.NewFromFloat(100000),
					TickSize: decimal.NewFromFloat(0.01),
				},
				&LotSizeFilter{
					MinQty:   decimal.NewFromFloat(0.001),
					MaxQty:   decimal.NewFromFloat(10000),
					StepSize: decimal.NewFromFloat(0.001),
				},
				&MinNotionalFilter{
					MinNotional:   decimal.NewFromFloat(10),
					ApplyToMarket: true,
					AvgPriceMins:  5,
				},
			},
		},
		{
			Symbol:     "BNBUSDT",
			BaseAsset:  "BNB",
			QuoteAsset: "USDT",
			Filters: []Filter{
				&PriceFilter{
					MinPrice: decimal.NewFromFloat(1),
					MaxPrice: decimal.NewFromFloat(10000),
					TickSize: decimal.NewFromFloat(1),
				},
				&MarketLotSizeFilter{
					MinQty:   decimal.NewFromFloat(0.01),
					MaxQty:   decimal.NewFromFloat(9000),
					StepSize: decimal.NewFromFloat(0.01),
				},
				&MinNotionalFilter{
					MinNotional:   decimal.NewFromFloat(10),
					ApplyToMarket: true,
					AvgPriceMins:  5,
				},
			},
		},
	}

	return NewSymbolValidator(filters)
}

// Ensure filters implement the interface
var (
	_ Filter = (*PriceFilter)(nil)
	_ Filter = (*LotSizeFilter)(nil)
	_ Filter = (*MinNotionalFilter)(nil)
	_ Filter = (*MarketLotSizeFilter)(nil)
)
