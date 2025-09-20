package filters

import (
	"fmt"
	"sync"

	"github.com/rs/zerolog/log"
	"github.com/shopspring/decimal"
)

// SymbolValidator validates orders against symbol filters
type SymbolValidator struct {
	filters map[string]*SymbolFilter
	mu      sync.RWMutex
}

// NewSymbolValidator creates a new symbol validator
func NewSymbolValidator(filters []SymbolFilter) *SymbolValidator {
	sv := &SymbolValidator{
		filters: make(map[string]*SymbolFilter),
	}

	for i := range filters {
		// Validate filter consistency
		if err := sv.validateFilterConsistency(&filters[i]); err != nil {
			log.Warn().Str("symbol", filters[i].Symbol).Err(err).Msg("Filter validation warning")
		}

		// Store filter - take address of slice element, not loop variable
		sv.filters[filters[i].Symbol] = &filters[i]
	}

	return sv
}

// validateFilterConsistency checks if filter values are valid
func (sv *SymbolValidator) validateFilterConsistency(filter *SymbolFilter) error {
	for _, f := range filter.Filters {
		switch pf := f.(type) {
		case *PriceFilter:
			if pf.MinPrice.GreaterThan(pf.MaxPrice) {
				return fmt.Errorf("min price %s greater than max price %s",
					pf.MinPrice.String(), pf.MaxPrice.String())
			}
		case *LotSizeFilter:
			if pf.MinQty.GreaterThan(pf.MaxQty) {
				return fmt.Errorf("min qty %s greater than max qty %s",
					pf.MinQty.String(), pf.MaxQty.String())
			}
		}
	}
	return nil
}

// ValidateOrder validates an order against symbol filters
func (sv *SymbolValidator) ValidateOrder(order Order) error {
	sv.mu.RLock()
	symbolFilter, exists := sv.filters[order.Symbol]
	sv.mu.RUnlock()

	if !exists {
		return fmt.Errorf("unknown symbol: %s", order.Symbol)
	}

	// Validate against each filter
	for _, filter := range symbolFilter.Filters {
		if err := filter.Validate(order); err != nil {
			return fmt.Errorf("validation failed for %s: %w", filter.Type(), err)
		}
	}

	return nil
}

// RoundPrice rounds a price to the symbol's tick size
func (sv *SymbolValidator) RoundPrice(symbol string, price decimal.Decimal) decimal.Decimal {
	sv.mu.RLock()
	symbolFilter, exists := sv.filters[symbol]
	sv.mu.RUnlock()

	if !exists {
		return decimal.Zero
	}

	// Find price filter
	for _, filter := range symbolFilter.Filters {
		if pf, ok := filter.(*PriceFilter); ok {
			if pf.TickSize.IsZero() {
				return price
			}

			// Round down to nearest tick size
			quotient := price.Div(pf.TickSize)
			rounded := quotient.Floor()
			return rounded.Mul(pf.TickSize)
		}
	}

	return price
}

// RoundQuantity rounds a quantity to the symbol's step size
func (sv *SymbolValidator) RoundQuantity(symbol string, quantity decimal.Decimal) decimal.Decimal {
	sv.mu.RLock()
	symbolFilter, exists := sv.filters[symbol]
	sv.mu.RUnlock()

	if !exists {
		return decimal.Zero
	}

	// Find lot size filter or market lot size filter
	for _, filter := range symbolFilter.Filters {
		switch lf := filter.(type) {
		case *LotSizeFilter:
			if lf.StepSize.IsZero() {
				return quantity
			}

			// Round down to nearest step size
			quotient := quantity.Div(lf.StepSize)
			rounded := quotient.Floor()
			return rounded.Mul(lf.StepSize)

		case *MarketLotSizeFilter:
			if lf.StepSize.IsZero() {
				return quantity
			}

			// Round down to nearest step size
			quotient := quantity.Div(lf.StepSize)
			rounded := quotient.Floor()
			return rounded.Mul(lf.StepSize)
		}
	}

	return quantity
}

// GetSymbolFilters returns all filters for a symbol
func (sv *SymbolValidator) GetSymbolFilters(symbol string) ([]Filter, error) {
	sv.mu.RLock()
	symbolFilter, exists := sv.filters[symbol]
	sv.mu.RUnlock()

	if !exists {
		return nil, fmt.Errorf("symbol not found: %s", symbol)
	}

	return symbolFilter.Filters, nil
}

// Implementation of Filter methods for PriceFilter
func (f *PriceFilter) Validate(order Order) error {
	if order.Type == "MARKET" {
		return nil // Market orders don't have price
	}

	if order.Price.LessThan(f.MinPrice) {
		return fmt.Errorf("price below minimum: %s < %s", order.Price.String(), f.MinPrice.String())
	}
	if order.Price.GreaterThan(f.MaxPrice) {
		return fmt.Errorf("price above maximum: %s > %s", order.Price.String(), f.MaxPrice.String())
	}

	// Check tick size
	if !f.TickSize.IsZero() {
		remainder := order.Price.Mod(f.TickSize)
		if !remainder.IsZero() {
			return fmt.Errorf("price precision does not match tick size: %s mod %s = %s",
				order.Price.String(), f.TickSize.String(), remainder.String())
		}
	}

	return nil
}

func (f *PriceFilter) Type() string {
	return "PRICE_FILTER"
}

// Implementation of Filter methods for LotSizeFilter
func (f *LotSizeFilter) Validate(order Order) error {
	if order.Quantity.LessThan(f.MinQty) {
		return fmt.Errorf("quantity below minimum: %s < %s", order.Quantity.String(), f.MinQty.String())
	}
	if order.Quantity.GreaterThan(f.MaxQty) {
		return fmt.Errorf("quantity above maximum: %s > %s", order.Quantity.String(), f.MaxQty.String())
	}

	// Check step size
	if !f.StepSize.IsZero() {
		remainder := order.Quantity.Mod(f.StepSize)
		if !remainder.IsZero() {
			return fmt.Errorf("quantity precision does not match step size: %s mod %s = %s",
				order.Quantity.String(), f.StepSize.String(), remainder.String())
		}
	}

	return nil
}

func (f *LotSizeFilter) Type() string {
	return "LOT_SIZE"
}

// Implementation of Filter methods for MinNotionalFilter
func (f *MinNotionalFilter) Validate(order Order) error {
	if order.Type == "MARKET" && !f.ApplyToMarket {
		return nil
	}

	// For market orders, we'd need average price
	// For limit orders, use the specified price
	if order.Type == "LIMIT" {
		notional := order.Price.Mul(order.Quantity)
		if notional.LessThan(f.MinNotional) {
			return fmt.Errorf("order value below minimum notional: %s < %s",
				notional.String(), f.MinNotional.String())
		}
	}

	return nil
}

func (f *MinNotionalFilter) Type() string {
	return "MIN_NOTIONAL"
}

// Implementation of Filter methods for MarketLotSizeFilter
func (f *MarketLotSizeFilter) Validate(order Order) error {
	if order.Type != "MARKET" {
		return nil // Only applies to market orders
	}

	if order.Quantity.LessThan(f.MinQty) {
		return fmt.Errorf("quantity below minimum: %s < %s", order.Quantity.String(), f.MinQty.String())
	}
	if order.Quantity.GreaterThan(f.MaxQty) {
		return fmt.Errorf("quantity above maximum: %s > %s", order.Quantity.String(), f.MaxQty.String())
	}

	// Check step size
	if !f.StepSize.IsZero() {
		remainder := order.Quantity.Mod(f.StepSize)
		if !remainder.IsZero() {
			return fmt.Errorf("quantity precision does not match step size: %s mod %s = %s",
				order.Quantity.String(), f.StepSize.String(), remainder.String())
		}
	}

	return nil
}

func (f *MarketLotSizeFilter) Type() string {
	return "MARKET_LOT_SIZE"
}
