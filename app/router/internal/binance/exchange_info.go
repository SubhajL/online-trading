package binance

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"router/internal/rest"
)

// ExchangeInfoCache caches exchange info for symbols
type ExchangeInfoCache struct {
	spotClient    *rest.Client
	futuresClient *rest.Client
	cache         map[string]*SymbolInfo
	cacheMu       sync.RWMutex
	cacheTime     time.Time
	cacheTTL      time.Duration
	logger        zerolog.Logger
}

// SymbolInfo contains trading rules for a symbol
type SymbolInfo struct {
	Symbol              string
	BaseAsset           string
	QuoteAsset          string
	BaseAssetPrecision  int
	QuoteAssetPrecision int
	PricePrecision      int
	QuantityPrecision   int
	MinPrice            decimal.Decimal
	MaxPrice            decimal.Decimal
	TickSize            decimal.Decimal
	MinQuantity         decimal.Decimal
	MaxQuantity         decimal.Decimal
	StepSize            decimal.Decimal
	MinNotional         decimal.Decimal
	IsFutures           bool
}

// Filter represents a symbol filter from exchange info
type Filter struct {
	FilterType  string          `json:"filterType"`
	MinPrice    decimal.Decimal `json:"minPrice,omitempty"`
	MaxPrice    decimal.Decimal `json:"maxPrice,omitempty"`
	TickSize    decimal.Decimal `json:"tickSize,omitempty"`
	MinQty      decimal.Decimal `json:"minQty,omitempty"`
	MaxQty      decimal.Decimal `json:"maxQty,omitempty"`
	StepSize    decimal.Decimal `json:"stepSize,omitempty"`
	MinNotional decimal.Decimal `json:"minNotional,omitempty"`
}

// NewExchangeInfoCache creates a new exchange info cache
func NewExchangeInfoCache(spotClient, futuresClient *rest.Client, cacheTTL time.Duration, logger zerolog.Logger) *ExchangeInfoCache {
	return &ExchangeInfoCache{
		spotClient:    spotClient,
		futuresClient: futuresClient,
		cache:         make(map[string]*SymbolInfo),
		cacheTTL:      cacheTTL,
		logger:        logger,
	}
}

// GetSymbolInfo retrieves symbol info with caching
func (e *ExchangeInfoCache) GetSymbolInfo(ctx context.Context, symbol string, isFutures bool) (*SymbolInfo, error) {
	e.cacheMu.RLock()
	if time.Since(e.cacheTime) < e.cacheTTL {
		info, exists := e.cache[symbol]
		e.cacheMu.RUnlock()
		if exists && info.IsFutures == isFutures {
			return info, nil
		}
	} else {
		e.cacheMu.RUnlock()
	}

	// Cache miss or expired, refresh
	if err := e.refreshCache(ctx); err != nil {
		return nil, fmt.Errorf("failed to refresh exchange info: %w", err)
	}

	e.cacheMu.RLock()
	info, exists := e.cache[symbol]
	e.cacheMu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("symbol %s not found", symbol)
	}

	if info.IsFutures != isFutures {
		return nil, fmt.Errorf("symbol %s is %s but requested %s", symbol,
			boolToMarket(info.IsFutures), boolToMarket(isFutures))
	}

	return info, nil
}

// RoundPrice rounds price according to symbol filters
func (e *ExchangeInfoCache) RoundPrice(ctx context.Context, symbol string, price decimal.Decimal, isFutures bool) (decimal.Decimal, error) {
	info, err := e.GetSymbolInfo(ctx, symbol, isFutures)
	if err != nil {
		return decimal.Zero, err
	}

	// Check price bounds
	if price.LessThan(info.MinPrice) {
		return info.MinPrice, nil
	}
	if price.GreaterThan(info.MaxPrice) {
		return info.MaxPrice, nil
	}

	// Round to tick size
	if info.TickSize.IsPositive() {
		ticks := price.Div(info.TickSize).Round(0)
		return ticks.Mul(info.TickSize), nil
	}

	// Fallback to precision rounding
	return price.Round(int32(info.PricePrecision)), nil
}

// RoundQuantity rounds quantity according to symbol filters
func (e *ExchangeInfoCache) RoundQuantity(ctx context.Context, symbol string, quantity decimal.Decimal, isFutures bool) (decimal.Decimal, error) {
	info, err := e.GetSymbolInfo(ctx, symbol, isFutures)
	if err != nil {
		return decimal.Zero, err
	}

	// Check quantity bounds
	if quantity.LessThan(info.MinQuantity) {
		return info.MinQuantity, nil
	}
	if quantity.GreaterThan(info.MaxQuantity) {
		return info.MaxQuantity, nil
	}

	// Round to step size
	if info.StepSize.IsPositive() {
		steps := quantity.Div(info.StepSize).Floor()
		return steps.Mul(info.StepSize), nil
	}

	// Fallback to precision rounding
	return quantity.Truncate(int32(info.QuantityPrecision)), nil
}

// ValidateNotional checks if order value meets minimum notional requirement
func (e *ExchangeInfoCache) ValidateNotional(ctx context.Context, symbol string, price, quantity decimal.Decimal, isFutures bool) error {
	info, err := e.GetSymbolInfo(ctx, symbol, isFutures)
	if err != nil {
		return err
	}

	notional := price.Mul(quantity)
	if notional.LessThan(info.MinNotional) {
		return fmt.Errorf("order notional %s is below minimum %s", notional, info.MinNotional)
	}

	return nil
}

// refreshCache updates the cache with latest exchange info
func (e *ExchangeInfoCache) refreshCache(ctx context.Context) error {
	e.cacheMu.Lock()
	defer e.cacheMu.Unlock()

	// Check if another goroutine already refreshed
	if time.Since(e.cacheTime) < e.cacheTTL {
		return nil
	}

	e.logger.Debug().Msg("Refreshing exchange info cache")

	newCache := make(map[string]*SymbolInfo)

	// Fetch spot exchange info
	if e.spotClient != nil {
		e.logger.Debug().Msg("Fetching spot exchange info")
		spotInfo, err := e.spotClient.GetExchangeInfo(ctx)
		if err != nil {
			e.logger.Error().Err(err).Msg("Failed to get spot exchange info")
			return fmt.Errorf("failed to get spot exchange info: %w", err)
		}

		for _, symbol := range spotInfo.Symbols {
			if symbol.Status != "TRADING" {
				continue
			}

			info := &SymbolInfo{
				Symbol:              symbol.Symbol,
				BaseAsset:           symbol.BaseAsset,
				QuoteAsset:          symbol.QuoteAsset,
				BaseAssetPrecision:  symbol.BaseAssetPrecision,
				QuoteAssetPrecision: symbol.QuoteAssetPrecision,
				IsFutures:           false,
			}

			// TODO: Parse filters when Symbol type includes them
			// For now, set default values
			info.MinPrice = decimal.RequireFromString("0.01")
			info.MaxPrice = decimal.RequireFromString("1000000")
			info.TickSize = decimal.RequireFromString("0.01")
			info.MinQuantity = decimal.RequireFromString("0.001")
			info.MaxQuantity = decimal.RequireFromString("10000")
			info.StepSize = decimal.RequireFromString("0.001")
			info.MinNotional = decimal.RequireFromString("10")
			info.PricePrecision = 2
			info.QuantityPrecision = 3

			newCache[symbol.Symbol] = info
		}
	}

	// For futures, we would need to make a different API call
	// Since the REST client doesn't support futures exchange info yet,
	// we'll skip it for now

	e.cache = newCache
	e.cacheTime = time.Now()

	e.logger.Info().
		Int("symbol_count", len(newCache)).
		Msg("Exchange info cache refreshed")

	return nil
}

// parseFilters extracts relevant filter values
func (e *ExchangeInfoCache) parseFilters(info *SymbolInfo, filters []interface{}) {
	for _, filterRaw := range filters {
		filterMap, ok := filterRaw.(map[string]interface{})
		if !ok {
			continue
		}

		filterType, _ := filterMap["filterType"].(string)

		switch filterType {
		case "PRICE_FILTER":
			info.MinPrice = parseDecimalField(filterMap, "minPrice")
			info.MaxPrice = parseDecimalField(filterMap, "maxPrice")
			info.TickSize = parseDecimalField(filterMap, "tickSize")
			info.PricePrecision = calculatePrecision(info.TickSize)

		case "LOT_SIZE":
			info.MinQuantity = parseDecimalField(filterMap, "minQty")
			info.MaxQuantity = parseDecimalField(filterMap, "maxQty")
			info.StepSize = parseDecimalField(filterMap, "stepSize")
			info.QuantityPrecision = calculatePrecision(info.StepSize)

		case "MIN_NOTIONAL", "NOTIONAL":
			info.MinNotional = parseDecimalField(filterMap, "minNotional")
		}
	}
}

// parseDecimalField safely parses a decimal field from a map
func parseDecimalField(m map[string]interface{}, field string) decimal.Decimal {
	if val, ok := m[field].(string); ok {
		if d, err := decimal.NewFromString(val); err == nil {
			return d
		}
	}
	return decimal.Zero
}

// calculatePrecision calculates decimal precision from step size
func calculatePrecision(stepSize decimal.Decimal) int {
	if stepSize.IsZero() {
		return 8 // Default precision
	}

	// Count decimal places
	str := stepSize.String()
	dotIndex := -1
	for i, c := range str {
		if c == '.' {
			dotIndex = i
			break
		}
	}

	if dotIndex == -1 {
		return 0
	}

	// Count non-zero digits after decimal
	precision := 0
	for i := dotIndex + 1; i < len(str); i++ {
		if str[i] != '0' {
			precision = i - dotIndex
		}
	}

	return precision
}

// boolToMarket converts boolean to market type string
func boolToMarket(isFutures bool) string {
	if isFutures {
		return "futures"
	}
	return "spot"
}
