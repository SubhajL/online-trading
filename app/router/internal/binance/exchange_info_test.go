package binance

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/rest"
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
		wantErr     error
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
			name:        "below min quantity errors",
			quantity:    "0.0001",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			wantErr:     ErrQtyBelowMin,
		},
		{
			name:        "above max quantity errors",
			quantity:    "10000",
			stepSize:    "0.001",
			minQuantity: "0.001",
			maxQuantity: "9000",
			wantErr:     ErrQtyAboveMax,
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

			if tt.wantErr != nil {
				require.ErrorIs(t, err, tt.wantErr)
				return
			}
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
		},
		futuresCache: map[string]*SymbolInfo{
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
	assert.Contains(t, err.Error(), "not found on futures")

	// Test unknown symbol - should fail
	_, err = cache.GetSymbolInfo(context.Background(), "UNKNOWN", false)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
}

func TestRoundPriceDirectional(t *testing.T) {
	cache := &ExchangeInfoCache{
		cache: map[string]*SymbolInfo{
			"BTCUSDT": {
				Symbol:    "BTCUSDT",
				TickSize:  decimal.RequireFromString("0.10"),
				MinPrice:  decimal.RequireFromString("0.10"),
				MaxPrice:  decimal.RequireFromString("1000000"),
				IsFutures: false,
			},
		},
		cacheTime: time.Now(),
		cacheTTL:  time.Hour,
	}

	tests := []struct {
		name     string
		price    string
		dir      RoundDir
		expected string
	}{
		{"up rounds away", "100.01", RoundUp, "100.1"},
		{"down rounds toward zero", "100.19", RoundDown, "100.1"},
		{"exact tick unchanged up", "100.1", RoundUp, "100.1"},
		{"exact tick unchanged down", "100.1", RoundDown, "100.1"},
		{"nearest rounds half up", "100.15", RoundNearest, "100.2"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			price := decimal.RequireFromString(tt.price)
			rounded, err := cache.RoundPriceDirectional(context.Background(), "BTCUSDT", price, tt.dir, false)
			require.NoError(t, err)
			assert.True(t, rounded.Equal(decimal.RequireFromString(tt.expected)),
				"got %s want %s", rounded, tt.expected)
		})
	}
}

func TestRefreshCacheParsesRealFiltersAndFetchesFutures(t *testing.T) {
	spotServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v3/exchangeInfo", r.URL.Path)
		_, _ = w.Write([]byte(`{"timezone":"UTC","serverTime":1,"symbols":[
			{"symbol":"BTCUSDT","status":"TRADING","baseAsset":"BTC","baseAssetPrecision":8,
			 "quoteAsset":"USDT","quoteAssetPrecision":8,
			 "filters":[
				{"filterType":"PRICE_FILTER","minPrice":"0.01000000","maxPrice":"1000000.00000000","tickSize":"0.01000000"},
				{"filterType":"LOT_SIZE","minQty":"0.00001000","maxQty":"9000.00000000","stepSize":"0.00001000"},
				{"filterType":"NOTIONAL","minNotional":"5.00000000"}
			 ]}]}`))
	}))
	defer spotServer.Close()

	futuresServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/fapi/v1/exchangeInfo", r.URL.Path)
		_, _ = w.Write([]byte(`{"serverTime":1,"symbols":[
			{"symbol":"BTCUSDT","status":"TRADING","baseAsset":"BTC","quoteAsset":"USDT",
			 "pricePrecision":2,"quantityPrecision":3,
			 "filters":[
				{"filterType":"PRICE_FILTER","minPrice":"556.80","maxPrice":"4529764","tickSize":"0.10"},
				{"filterType":"LOT_SIZE","minQty":"0.001","maxQty":"1000","stepSize":"0.001"},
				{"filterType":"MIN_NOTIONAL","notional":"100"}
			 ]}]}`))
	}))
	defer futuresServer.Close()

	cache := NewExchangeInfoCache(
		rest.NewClient(spotServer.URL, nil),
		rest.NewClient(futuresServer.URL, nil),
		time.Hour,
		zerolog.Nop(),
	)

	spotInfo, err := cache.GetSymbolInfo(context.Background(), "BTCUSDT", false)
	require.NoError(t, err)
	assert.Equal(t, "0.01", spotInfo.TickSize.String())
	assert.Equal(t, "0.00001", spotInfo.StepSize.String())
	assert.Equal(t, "5", spotInfo.MinNotional.String())
	assert.False(t, spotInfo.IsFutures)

	// Regression: the deployed wiring produced an always-empty futures cache,
	// failing every futures bracket at the rounding step.
	futuresInfo, err := cache.GetSymbolInfo(context.Background(), "BTCUSDT", true)
	require.NoError(t, err)
	assert.Equal(t, "0.1", futuresInfo.TickSize.String())
	assert.Equal(t, "0.001", futuresInfo.StepSize.String())
	assert.Equal(t, "100", futuresInfo.MinNotional.String())
	assert.True(t, futuresInfo.IsFutures)
}

func TestRefreshCacheSurvivesFuturesOutage(t *testing.T) {
	spotServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"timezone":"UTC","serverTime":1,"symbols":[
			{"symbol":"BTCUSDT","status":"TRADING","baseAsset":"BTC","baseAssetPrecision":8,
			 "quoteAsset":"USDT","quoteAssetPrecision":8,
			 "filters":[{"filterType":"LOT_SIZE","minQty":"0.00001","maxQty":"9000","stepSize":"0.00001"}]}]}`))
	}))
	defer spotServer.Close()

	futuresServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer futuresServer.Close()

	cache := NewExchangeInfoCache(
		rest.NewClient(spotServer.URL, nil),
		rest.NewClient(futuresServer.URL, nil),
		time.Hour,
		zerolog.Nop(),
	)

	spotInfo, err := cache.GetSymbolInfo(context.Background(), "BTCUSDT", false)
	require.NoError(t, err)
	assert.Equal(t, "0.00001", spotInfo.StepSize.String())

	_, err = cache.GetSymbolInfo(context.Background(), "BTCUSDT", true)
	assert.Error(t, err)
}
