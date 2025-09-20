package filters

import (
	"github.com/shopspring/decimal"
)

// SymbolFilter contains all filters for a trading symbol
type SymbolFilter struct {
	Symbol     string
	Filters    []Filter
	BaseAsset  string
	QuoteAsset string
}

// Filter interface for different filter types
type Filter interface {
	Validate(order Order) error
	Type() string
}

// Order represents a trading order
type Order struct {
	Symbol   string
	Side     string // BUY or SELL
	Type     string // MARKET or LIMIT
	Price    decimal.Decimal
	Quantity decimal.Decimal
}

// PriceFilter validates price constraints
type PriceFilter struct {
	MinPrice decimal.Decimal `json:"minPrice"`
	MaxPrice decimal.Decimal `json:"maxPrice"`
	TickSize decimal.Decimal `json:"tickSize"`
}

// LotSizeFilter validates quantity constraints
type LotSizeFilter struct {
	MinQty   decimal.Decimal `json:"minQty"`
	MaxQty   decimal.Decimal `json:"maxQty"`
	StepSize decimal.Decimal `json:"stepSize"`
}

// MinNotionalFilter validates minimum notional value
type MinNotionalFilter struct {
	MinNotional   decimal.Decimal `json:"minNotional"`
	ApplyToMarket bool            `json:"applyToMarket"`
	AvgPriceMins  int             `json:"avgPriceMins"`
}

// MarketLotSizeFilter for market orders
type MarketLotSizeFilter struct {
	MinQty   decimal.Decimal `json:"minQty"`
	MaxQty   decimal.Decimal `json:"maxQty"`
	StepSize decimal.Decimal `json:"stepSize"`
}
