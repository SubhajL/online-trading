package api

import (
	"time"
)

// OrderRequest represents an order placement request
type OrderRequest struct {
	Symbol        string `json:"symbol"`
	Side          string `json:"side"` // BUY or SELL
	Type          string `json:"type"` // MARKET, LIMIT, etc.
	Quantity      string `json:"quantity"`
	Price         string `json:"price,omitempty"`
	ClientOrderID string `json:"clientOrderId"`
	StopPrice     string `json:"stopPrice,omitempty"`
	TimeInForce   string `json:"timeInForce,omitempty"`
	ReduceOnly    bool   `json:"reduceOnly,omitempty"` // For futures
}

// OrderResponse represents the response after placing an order
type OrderResponse struct {
	OrderID         string    `json:"orderId"`
	ClientOrderID   string    `json:"clientOrderId"`
	Symbol          string    `json:"symbol"`
	Status          string    `json:"status"`
	ExecutedQty     string    `json:"executedQty"`
	CumulativeQuote string    `json:"cumulativeQuoteQty"`
	TransactTime    time.Time `json:"transactTime"`
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status    string            `json:"status"`
	Timestamp time.Time         `json:"timestamp"`
	Services  map[string]string `json:"services"`
}

// OrderTimingPatch represents timing updates for order execution tracking
type OrderTimingPatch struct {
	RouterReceivedAt *time.Time `json:"router_received_at,omitempty"`
	RouterSentAt     *time.Time `json:"router_sent_at,omitempty"`
	ExchangeAckAt    *time.Time `json:"exchange_ack_at,omitempty"`
	FirstFillAt      *time.Time `json:"first_fill_at,omitempty"`
	FilledAt         *time.Time `json:"filled_at,omitempty"`
}

// ExecutionQuality represents aggregated execution quality metrics
type ExecutionQuality struct {
	TotalOrders int     `json:"total_orders"`
	FilledOrders int    `json:"filled_orders"`
	FillRate    float64 `json:"fill_rate"`

	// Latency percentiles (ms)
	EngineToRouterP50   float64 `json:"engine_to_router_p50_ms"`
	EngineToRouterP95   float64 `json:"engine_to_router_p95_ms"`
	RouterToExchangeP50 float64 `json:"router_to_exchange_p50_ms"`
	RouterToExchangeP95 float64 `json:"router_to_exchange_p95_ms"`
	TimeToFirstFillP50  float64 `json:"time_to_first_fill_p50_ms"`
	TimeToFirstFillP95  float64 `json:"time_to_first_fill_p95_ms"`

	// Slippage metrics (basis points)
	AvgSlippageBps float64 `json:"avg_slippage_bps"`
	MaxSlippageBps float64 `json:"max_slippage_bps"`
	SlippageStdDev float64 `json:"slippage_std_dev_bps"`
}
