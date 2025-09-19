package rest

import (
	"github.com/shopspring/decimal"
)

// OrderRequest represents a request to place an order
type OrderRequest struct {
	Symbol           string          `json:"symbol"`
	Side             string          `json:"side"`             // BUY or SELL
	Type             string          `json:"type"`             // MARKET, LIMIT, STOP_LOSS_LIMIT, etc.
	Quantity         decimal.Decimal `json:"quantity"`
	Price            decimal.Decimal `json:"price,omitempty"`
	StopPrice        decimal.Decimal `json:"stopPrice,omitempty"`    // For stop orders
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

// FuturesOrderRequest represents a futures order request
type FuturesOrderRequest struct {
	Symbol              string          `json:"symbol"`
	Side                string          `json:"side"`
	Type                string          `json:"type"`
	Quantity            decimal.Decimal `json:"quantity"`
	Price               decimal.Decimal `json:"price,omitempty"`
	StopPrice           decimal.Decimal `json:"stopPrice,omitempty"`
	TimeInForce         string          `json:"timeInForce,omitempty"`
	ReduceOnly          bool            `json:"reduceOnly,omitempty"`
	ClosePosition       bool            `json:"closePosition,omitempty"`
	ActivationPrice     decimal.Decimal `json:"activationPrice,omitempty"`
	CallbackRate        decimal.Decimal `json:"callbackRate,omitempty"`
	WorkingType         string          `json:"workingType,omitempty"`
	PriceProtect        bool            `json:"priceProtect,omitempty"`
	NewClientOrderID    string          `json:"newClientOrderId,omitempty"`
	RecvWindow          int64           `json:"recvWindow,omitempty"`
}

// FuturesOrderResponse represents a futures order response
type FuturesOrderResponse struct {
	OrderID               int64           `json:"orderId"`
	Symbol                string          `json:"symbol"`
	Status                string          `json:"status"`
	ClientOrderID         string          `json:"clientOrderId"`
	Price                 decimal.Decimal `json:"price"`
	AvgPrice              decimal.Decimal `json:"avgPrice"`
	OrigQty               decimal.Decimal `json:"origQty"`
	ExecutedQty           decimal.Decimal `json:"executedQty"`
	CumQty                decimal.Decimal `json:"cumQty"`
	CumQuote              decimal.Decimal `json:"cumQuote"`
	TimeInForce           string          `json:"timeInForce"`
	Type                  string          `json:"type"`
	ReduceOnly            bool            `json:"reduceOnly"`
	ClosePosition         bool            `json:"closePosition"`
	Side                  string          `json:"side"`
	PositionSide          string          `json:"positionSide"`
	StopPrice             decimal.Decimal `json:"stopPrice"`
	WorkingType           string          `json:"workingType"`
	PriceProtect          bool            `json:"priceProtect"`
	OrigType              string          `json:"origType"`
	UpdateTime            int64           `json:"updateTime"`
}

// FuturesAccountResponse represents futures account info
type FuturesAccountResponse struct {
	TotalWalletBalance       decimal.Decimal    `json:"totalWalletBalance"`
	TotalUnrealizedProfit    decimal.Decimal    `json:"totalUnrealizedProfit"`
	TotalMarginBalance       decimal.Decimal    `json:"totalMarginBalance"`
	AvailableBalance         decimal.Decimal    `json:"availableBalance"`
	TotalPositionInitialMargin decimal.Decimal  `json:"totalPositionInitialMargin"`
	TotalOpenOrderInitialMargin decimal.Decimal `json:"totalOpenOrderInitialMargin"`
	TotalCrossWalletBalance  decimal.Decimal    `json:"totalCrossWalletBalance"`
	TotalCrossUnPnl          decimal.Decimal    `json:"totalCrossUnPnl"`
	MaxWithdrawAmount        decimal.Decimal    `json:"maxWithdrawAmount"`
	UpdateTime               int64              `json:"updateTime"`
	Assets                   []FuturesAsset     `json:"assets"`
	Positions                []FuturesPosition  `json:"positions"`
}

// FuturesAsset represents a futures account asset
type FuturesAsset struct {
	Asset                  string          `json:"asset"`
	WalletBalance          decimal.Decimal `json:"walletBalance"`
	UnrealizedProfit       decimal.Decimal `json:"unrealizedProfit"`
	MarginBalance          decimal.Decimal `json:"marginBalance"`
	MaintMargin            decimal.Decimal `json:"maintMargin"`
	InitialMargin          decimal.Decimal `json:"initialMargin"`
	PositionInitialMargin  decimal.Decimal `json:"positionInitialMargin"`
	OpenOrderInitialMargin decimal.Decimal `json:"openOrderInitialMargin"`
	MaxWithdrawAmount      decimal.Decimal `json:"maxWithdrawAmount"`
	CrossWalletBalance     decimal.Decimal `json:"crossWalletBalance"`
	CrossUnPnl             decimal.Decimal `json:"crossUnPnl"`
	AvailableBalance       decimal.Decimal `json:"availableBalance"`
}

// FuturesPosition represents an open futures position
type FuturesPosition struct {
	Symbol                 string          `json:"symbol"`
	InitialMargin          decimal.Decimal `json:"initialMargin"`
	MaintMargin            decimal.Decimal `json:"maintMargin"`
	UnrealizedProfit       decimal.Decimal `json:"unrealizedProfit"`
	PositionInitialMargin  decimal.Decimal `json:"positionInitialMargin"`
	OpenOrderInitialMargin decimal.Decimal `json:"openOrderInitialMargin"`
	Leverage               string          `json:"leverage"`
	Isolated               bool            `json:"isolated"`
	EntryPrice             decimal.Decimal `json:"entryPrice"`
	MaxNotional            decimal.Decimal `json:"maxNotional"`
	BidNotional            decimal.Decimal `json:"bidNotional"`
	AskNotional            decimal.Decimal `json:"askNotional"`
	PositionSide           string          `json:"positionSide"`
	PositionAmt            decimal.Decimal `json:"positionAmt"`
	UpdateTime             int64           `json:"updateTime"`
	MarkPrice              decimal.Decimal `json:"markPrice"`
}

