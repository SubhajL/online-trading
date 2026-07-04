package binance

import (
	"context"
	"errors"
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
	futuresCache  map[string]*SymbolInfo
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

// Rounding-boundary violations are surfaced as errors instead of silently
// clamping: inflating a quantity to minQty would violate risk sizing.
var (
	ErrQtyBelowMin = errors.New("quantity below symbol minimum")
	ErrQtyAboveMax = errors.New("quantity above symbol maximum")
)

// RoundDir selects the tick-rounding direction for trigger-sensitive prices.
type RoundDir int

const (
	RoundNearest RoundDir = iota
	RoundDown
	RoundUp
)

// NewExchangeInfoCache creates a new exchange info cache
func NewExchangeInfoCache(spotClient, futuresClient *rest.Client, cacheTTL time.Duration, logger zerolog.Logger) *ExchangeInfoCache {
	return &ExchangeInfoCache{
		spotClient:    spotClient,
		futuresClient: futuresClient,
		cache:         make(map[string]*SymbolInfo),
		futuresCache:  make(map[string]*SymbolInfo),
		cacheTTL:      cacheTTL,
		logger:        logger,
	}
}

// GetSymbolInfo retrieves symbol info with caching
func (e *ExchangeInfoCache) GetSymbolInfo(ctx context.Context, symbol string, isFutures bool) (*SymbolInfo, error) {
	e.cacheMu.RLock()
	if time.Since(e.cacheTime) < e.cacheTTL {
		info, exists := e.marketCache(isFutures)[symbol]
		e.cacheMu.RUnlock()
		if exists {
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
	info, exists := e.marketCache(isFutures)[symbol]
	e.cacheMu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("symbol %s not found on %s", symbol, boolToMarket(isFutures))
	}

	return info, nil
}

// marketCache must be called with cacheMu held.
func (e *ExchangeInfoCache) marketCache(isFutures bool) map[string]*SymbolInfo {
	if isFutures {
		return e.futuresCache
	}
	return e.cache
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

	// Round to step size first, then enforce bounds: silently inflating a
	// below-minimum quantity to minQty would violate risk sizing.
	rounded := quantity
	if info.StepSize.IsPositive() {
		steps := quantity.Div(info.StepSize).Floor()
		rounded = steps.Mul(info.StepSize)
	} else if info.QuantityPrecision > 0 {
		rounded = quantity.Truncate(int32(info.QuantityPrecision))
	}

	if rounded.LessThan(info.MinQuantity) {
		return decimal.Zero, fmt.Errorf("%w: %s < %s for %s",
			ErrQtyBelowMin, rounded, info.MinQuantity, symbol)
	}
	if info.MaxQuantity.IsPositive() && rounded.GreaterThan(info.MaxQuantity) {
		return decimal.Zero, fmt.Errorf("%w: %s > %s for %s",
			ErrQtyAboveMax, rounded, info.MaxQuantity, symbol)
	}

	return rounded, nil
}

// RoundPriceDirectional rounds a price onto the tick grid in a fixed
// direction so that rounding can never move a stop or take-profit across
// its trigger relation.
func (e *ExchangeInfoCache) RoundPriceDirectional(ctx context.Context, symbol string, price decimal.Decimal, dir RoundDir, isFutures bool) (decimal.Decimal, error) {
	info, err := e.GetSymbolInfo(ctx, symbol, isFutures)
	if err != nil {
		return decimal.Zero, err
	}

	if !info.TickSize.IsPositive() {
		return price.Round(int32(info.PricePrecision)), nil
	}

	ticks := price.Div(info.TickSize)
	switch dir {
	case RoundDown:
		ticks = ticks.Floor()
	case RoundUp:
		ticks = ticks.Ceil()
	default:
		ticks = ticks.Round(0)
	}
	rounded := ticks.Mul(info.TickSize)

	if info.MinPrice.IsPositive() && rounded.LessThan(info.MinPrice) {
		return info.MinPrice, nil
	}
	if info.MaxPrice.IsPositive() && rounded.GreaterThan(info.MaxPrice) {
		return info.MaxPrice, nil
	}
	return rounded, nil
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
			applyRawFilters(info, symbol.Filters)

			newCache[symbol.Symbol] = info
		}
	}

	// A futures outage must not take down spot ordering: keep the previous
	// futures entries and refresh spot only.
	newFuturesCache := e.futuresCache
	if e.futuresClient != nil {
		e.logger.Debug().Msg("Fetching futures exchange info")
		futuresInfo, err := e.futuresClient.GetFuturesExchangeInfo(ctx)
		if err != nil {
			e.logger.Error().Err(err).Msg("Failed to get futures exchange info; keeping previous futures entries")
			futuresInfo = &rest.FuturesExchangeInfo{}
		} else {
			newFuturesCache = make(map[string]*SymbolInfo)
		}

		for _, symbol := range futuresInfo.Symbols {
			if symbol.Status != "TRADING" {
				continue
			}

			info := &SymbolInfo{
				Symbol:            symbol.Symbol,
				BaseAsset:         symbol.BaseAsset,
				QuoteAsset:        symbol.QuoteAsset,
				PricePrecision:    symbol.PricePrecision,
				QuantityPrecision: symbol.QuantityPrecision,
				IsFutures:         true,
			}
			applyRawFilters(info, symbol.Filters)

			newFuturesCache[symbol.Symbol] = info
		}
	}

	e.cache = newCache
	e.futuresCache = newFuturesCache
	e.cacheTime = time.Now()

	e.logger.Info().
		Int("spot_symbol_count", len(newCache)).
		Int("futures_symbol_count", len(newFuturesCache)).
		Msg("Exchange info cache refreshed")

	return nil
}

// applyRawFilters populates trading rules from exchangeInfo filters.
func applyRawFilters(info *SymbolInfo, rawFilters []rest.RawFilter) {
	parse := func(v string) decimal.Decimal {
		if v == "" {
			return decimal.Zero
		}
		d, err := decimal.NewFromString(v)
		if err != nil {
			return decimal.Zero
		}
		return d
	}

	for _, f := range rawFilters {
		switch f.FilterType {
		case "PRICE_FILTER":
			info.MinPrice = parse(f.MinPrice)
			info.MaxPrice = parse(f.MaxPrice)
			info.TickSize = parse(f.TickSize)
			if info.PricePrecision == 0 {
				info.PricePrecision = calculatePrecision(info.TickSize)
			}
		case "LOT_SIZE":
			info.MinQuantity = parse(f.MinQty)
			info.MaxQuantity = parse(f.MaxQty)
			info.StepSize = parse(f.StepSize)
			if info.QuantityPrecision == 0 {
				info.QuantityPrecision = calculatePrecision(info.StepSize)
			}
		case "MIN_NOTIONAL":
			// Spot uses minNotional, futures uses notional.
			if f.MinNotional != "" {
				info.MinNotional = parse(f.MinNotional)
			} else {
				info.MinNotional = parse(f.Notional)
			}
		case "NOTIONAL":
			info.MinNotional = parse(f.MinNotional)
		}
	}
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
