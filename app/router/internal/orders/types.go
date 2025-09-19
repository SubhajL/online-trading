package orders

import (
	"time"

	"github.com/shopspring/decimal"
)

// OrderType represents the type of order
type OrderType string

const (
	OrderTypeSpot    OrderType = "SPOT"
	OrderTypeFutures OrderType = "FUTURES"
)

// BracketOrder represents a bracket order (main + TPs + SL)
type BracketOrder struct {
	ID               string            `json:"id"`
	Symbol           string            `json:"symbol"`
	Type             OrderType         `json:"type"`
	Side             string            `json:"side"`
	Quantity         decimal.Decimal   `json:"quantity"`
	EntryPrice       decimal.Decimal   `json:"entry_price"`
	TakeProfitPrices []decimal.Decimal `json:"take_profit_prices"`
	StopLossPrice    decimal.Decimal   `json:"stop_loss_price"`
	ClientOrderIDs   ClientOrderIDs    `json:"client_order_ids"`
	CreatedAt        time.Time         `json:"created_at"`
	UpdatedAt        time.Time         `json:"updated_at"`
}

// ClientOrderIDs holds the client order IDs for a bracket order
type ClientOrderIDs struct {
	Main        string   `json:"main"`
	TakeProfits []string `json:"take_profits"`
	StopLoss    string   `json:"stop_loss"`
}

// OrderUpdate represents an order status update event
type OrderUpdate struct {
	EventType     string          `json:"event_type"`
	Symbol        string          `json:"symbol"`
	OrderID       int64           `json:"order_id"`
	ClientOrderID string          `json:"client_order_id"`
	Status        string          `json:"status"`
	Side          string          `json:"side"`
	OrderType     string          `json:"order_type"`
	Price         decimal.Decimal `json:"price"`
	Quantity      decimal.Decimal `json:"quantity"`
	ExecutedQty   decimal.Decimal `json:"executed_qty"`
	UpdateTime    time.Time       `json:"update_time"`
	Reason        string          `json:"reason,omitempty"`
}

// PlaceBracketRequest represents a request to place a bracket order
type PlaceBracketRequest struct {
	Symbol           string            `json:"symbol"`
	Side             string            `json:"side"`
	Quantity         decimal.Decimal   `json:"quantity"`
	EntryPrice       decimal.Decimal   `json:"entry_price,omitempty"`
	TakeProfitPrices []decimal.Decimal `json:"take_profit_prices"`
	StopLossPrice    decimal.Decimal   `json:"stop_loss_price"`
	OrderType        string            `json:"order_type,omitempty"` // LIMIT or MARKET
	IsFutures        bool              `json:"is_futures"`
}

// PlaceBracketResponse represents the response from placing a bracket order
type PlaceBracketResponse struct {
	BracketOrderID string          `json:"bracket_order_id"`
	ClientOrderIDs ClientOrderIDs  `json:"client_order_ids"`
	Symbol         string          `json:"symbol"`
	Side           string          `json:"side"`
	Quantity       decimal.Decimal `json:"quantity"`
	CreatedAt      time.Time       `json:"created_at"`
	PartialFailure bool            `json:"partial_failure,omitempty"`
	Errors         []string        `json:"errors,omitempty"`
}

// CancelRequest represents a request to cancel an order
type CancelRequest struct {
	Symbol        string `json:"symbol"`
	OrderID       int64  `json:"order_id,omitempty"`
	ClientOrderID string `json:"client_order_id,omitempty"`
}

// CloseAllRequest represents a request to close all positions
type CloseAllRequest struct {
	Symbol    string `json:"symbol,omitempty"`
	IsFutures bool   `json:"is_futures"`
}
