package binance

import (
	"time"

	"github.com/shopspring/decimal"
)

// SpotOrderRequest represents a spot order placement request
type SpotOrderRequest struct {
	Symbol           string          `json:"symbol"`
	Side             string          `json:"side"`
	Type             string          `json:"type"`
	TimeInForce      string          `json:"timeInForce,omitempty"`
	Quantity         decimal.Decimal `json:"quantity"`
	Price            decimal.Decimal `json:"price,omitempty"`
	StopPrice        decimal.Decimal `json:"stopPrice,omitempty"`
	QuoteOrderQty    decimal.Decimal `json:"quoteOrderQty,omitempty"`
	NewClientOrderID string          `json:"newClientOrderId,omitempty"`
}

// FuturesOrderRequest represents a futures order placement request
type FuturesOrderRequest struct {
	Symbol           string          `json:"symbol"`
	Side             string          `json:"side"`
	Type             string          `json:"type"`
	TimeInForce      string          `json:"timeInForce,omitempty"`
	Quantity         decimal.Decimal `json:"quantity"`
	Price            decimal.Decimal `json:"price,omitempty"`
	StopPrice        decimal.Decimal `json:"stopPrice,omitempty"`
	ReduceOnly       bool            `json:"reduceOnly,omitempty"`
	ClosePosition    bool            `json:"closePosition,omitempty"`
	NewClientOrderID string          `json:"newClientOrderId,omitempty"`
}

// OrderResponse represents the response from order placement
type OrderResponse struct {
	Symbol        string          `json:"symbol"`
	OrderID       int64           `json:"orderId"`
	ClientOrderID string          `json:"clientOrderId"`
	TransactTime  int64           `json:"transactTime"`
	Price         decimal.Decimal `json:"price"`
	OrigQty       decimal.Decimal `json:"origQty"`
	ExecutedQty   decimal.Decimal `json:"executedQty"`
	Status        string          `json:"status"`
	TimeInForce   string          `json:"timeInForce"`
	Type          string          `json:"type"`
	Side          string          `json:"side"`
	Fills         []Fill          `json:"fills"`
}

// Fill represents individual trade fills
type Fill struct {
	Price           decimal.Decimal `json:"price"`
	Qty             decimal.Decimal `json:"qty"`
	Commission      decimal.Decimal `json:"commission"`
	CommissionAsset string          `json:"commissionAsset"`
}

// AccountResponse represents account information
type AccountResponse struct {
	MakerCommission  int64     `json:"makerCommission"`
	TakerCommission  int64     `json:"takerCommission"`
	BuyerCommission  int64     `json:"buyerCommission"`
	SellerCommission int64     `json:"sellerCommission"`
	CanTrade         bool      `json:"canTrade"`
	CanWithdraw      bool      `json:"canWithdraw"`
	CanDeposit       bool      `json:"canDeposit"`
	UpdateTime       int64     `json:"updateTime"`
	AccountType      string    `json:"accountType"`
	Balances         []Balance `json:"balances"`
}

// Balance represents account balance for an asset
type Balance struct {
	Asset  string          `json:"asset"`
	Free   decimal.Decimal `json:"free"`
	Locked decimal.Decimal `json:"locked"`
}

// CancelResponse represents order cancellation response
type CancelResponse struct {
	Symbol            string          `json:"symbol"`
	OrderID           int64           `json:"orderId"`
	ClientOrderID     string          `json:"clientOrderId"`
	Price             decimal.Decimal `json:"price"`
	OrigQty           decimal.Decimal `json:"origQty"`
	ExecutedQty       decimal.Decimal `json:"executedQty"`
	Status            string          `json:"status"`
	TimeInForce       string          `json:"timeInForce"`
	Type              string          `json:"type"`
	Side              string          `json:"side"`
}

// Order represents an order in the system
type Order struct {
	Symbol        string          `json:"symbol"`
	OrderID       int64           `json:"orderId"`
	ClientOrderID string          `json:"clientOrderId"`
	Price         decimal.Decimal `json:"price"`
	OrigQty       decimal.Decimal `json:"origQty"`
	ExecutedQty   decimal.Decimal `json:"executedQty"`
	Status        string          `json:"status"`
	TimeInForce   string          `json:"timeInForce"`
	Type          string          `json:"type"`
	Side          string          `json:"side"`
	Time          int64           `json:"time"`
	UpdateTime    int64           `json:"updateTime"`
}

// ClientConfig represents Binance client configuration
type ClientConfig struct {
	BaseURL    string
	APIKey     string
	SecretKey  string
	Timeout    time.Duration
}