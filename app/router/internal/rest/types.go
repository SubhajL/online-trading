package rest

import (
	"github.com/shopspring/decimal"
)

// OrderRequest represents a request to place an order
type OrderRequest struct {
	Symbol           string          `json:"symbol"`
	Side             string          `json:"side"`             // BUY or SELL
	Type             string          `json:"type"`             // MARKET, LIMIT, etc.
	Quantity         decimal.Decimal `json:"quantity"`
	Price            decimal.Decimal `json:"price,omitempty"`
	TimeInForce      string          `json:"timeInForce,omitempty"` // GTC, IOC, FOK
	NewClientOrderID string          `json:"newClientOrderId,omitempty"`
	RecvWindow       int64           `json:"recvWindow,omitempty"`
}

// OrderResponse represents the response from placing an order
type OrderResponse struct {
	Symbol              string          `json:"symbol"`
	OrderID             int64           `json:"orderId"`
	OrderListID         int64           `json:"orderListId"`
	ClientOrderID       string          `json:"clientOrderId"`
	TransactTime        int64           `json:"transactTime"`
	Price               decimal.Decimal `json:"price"`
	OrigQty             decimal.Decimal `json:"origQty"`
	ExecutedQty         decimal.Decimal `json:"executedQty"`
	CummulativeQuoteQty decimal.Decimal `json:"cummulativeQuoteQty"`
	Status              string          `json:"status"`
	TimeInForce         string          `json:"timeInForce"`
	Type                string          `json:"type"`
	Side                string          `json:"side"`
	Fills               []Fill          `json:"fills"`
}

// Fill represents a trade execution
type Fill struct {
	Price           decimal.Decimal `json:"price"`
	Qty             decimal.Decimal `json:"qty"`
	Commission      decimal.Decimal `json:"commission"`
	CommissionAsset string          `json:"commissionAsset"`
	TradeID         int64           `json:"tradeId"`
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
	Permissions      []string  `json:"permissions"`
}

// Balance represents an asset balance
type Balance struct {
	Asset  string          `json:"asset"`
	Free   decimal.Decimal `json:"free"`
	Locked decimal.Decimal `json:"locked"`
}

// ExchangeInfo represents exchange trading rules
type ExchangeInfo struct {
	Timezone   string   `json:"timezone"`
	ServerTime int64    `json:"serverTime"`
	Symbols    []Symbol `json:"symbols"`
}

// Symbol represents trading symbol information
type Symbol struct {
	Symbol              string   `json:"symbol"`
	Status              string   `json:"status"`
	BaseAsset           string   `json:"baseAsset"`
	BaseAssetPrecision  int      `json:"baseAssetPrecision"`
	QuoteAsset          string   `json:"quoteAsset"`
	QuoteAssetPrecision int      `json:"quoteAssetPrecision"`
	OrderTypes          []string `json:"orderTypes"`
	IcebergAllowed      bool     `json:"icebergAllowed"`
	OcoAllowed          bool     `json:"ocoAllowed"`
	IsSpotTradingAllowed bool    `json:"isSpotTradingAllowed"`
	IsMarginTradingAllowed bool  `json:"isMarginTradingAllowed"`
}

// OrderBook represents order book depth
type OrderBook struct {
	LastUpdateID int64       `json:"lastUpdateId"`
	Bids         []PriceLevel `json:"bids"`
	Asks         []PriceLevel `json:"asks"`
}

// PriceLevel represents a price level in the order book
type PriceLevel struct {
	Price    decimal.Decimal `json:"price"`
	Quantity decimal.Decimal `json:"quantity"`
}

// Order represents an order in the system
type Order struct {
	Symbol              string          `json:"symbol"`
	OrderID             int64           `json:"orderId"`
	OrderListID         int64           `json:"orderListId"`
	ClientOrderID       string          `json:"clientOrderId"`
	Price               decimal.Decimal `json:"price"`
	OrigQty             decimal.Decimal `json:"origQty"`
	ExecutedQty         decimal.Decimal `json:"executedQty"`
	CummulativeQuoteQty decimal.Decimal `json:"cummulativeQuoteQty"`
	Status              string          `json:"status"`
	TimeInForce         string          `json:"timeInForce"`
	Type                string          `json:"type"`
	Side                string          `json:"side"`
	StopPrice           decimal.Decimal `json:"stopPrice"`
	IcebergQty          decimal.Decimal `json:"icebergQty"`
	Time                int64           `json:"time"`
	UpdateTime          int64           `json:"updateTime"`
	IsWorking           bool            `json:"isWorking"`
	OrigQuoteOrderQty   decimal.Decimal `json:"origQuoteOrderQty"`
}