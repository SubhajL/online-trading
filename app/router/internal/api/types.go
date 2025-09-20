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
