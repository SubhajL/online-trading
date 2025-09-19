package websocket

import (
	"encoding/json"

	"github.com/shopspring/decimal"
)

// StreamMessage represents an incoming WebSocket message
type StreamMessage struct {
	Stream string          `json:"stream"`
	Data   json.RawMessage `json:"data"`
}

// SubscriptionRequest represents an outgoing subscription request
type SubscriptionRequest struct {
	Method string   `json:"method"`
	Params []string `json:"params"`
	ID     int      `json:"id"`
}

// SubscriptionResponse represents a subscription response from server
type SubscriptionResponse struct {
	Result interface{} `json:"result"`
	ID     int         `json:"id"`
	Error  *struct {
		Code int    `json:"code"`
		Msg  string `json:"msg"`
	} `json:"error,omitempty"`
}

// EventHandler interface for handling different types of real-time events
type EventHandler interface {
	HandleEvent(eventType string, data json.RawMessage) error
}

// DepthHandler handles order book depth updates
type DepthHandler interface {
	HandleDepthUpdate(event *DepthUpdateEvent) error
}

// TickerHandler handles 24hr ticker statistics
type TickerHandler interface {
	HandleTickerUpdate(event *TickerEvent) error
}

// UserStreamHandler handles private user data events
type UserStreamHandler interface {
	HandleAccountUpdate(event *AccountUpdateEvent) error
	HandleOrderUpdate(event *OrderUpdateEvent) error
	HandleListenKeyExpired() error
}

// DepthUpdateEvent represents order book depth changes
type DepthUpdateEvent struct {
	EventType     string       `json:"e"`
	EventTime     int64        `json:"E"`
	Symbol        string       `json:"s"`
	FirstUpdateID int64        `json:"U"`
	FinalUpdateID int64        `json:"u"`
	Bids          []PriceLevel `json:"b"`
	Asks          []PriceLevel `json:"a"`
}

// PriceLevel represents a price level in order book
type PriceLevel struct {
	Price    decimal.Decimal `json:"price"`
	Quantity decimal.Decimal `json:"quantity"`
}

// UnmarshalJSON implements custom JSON unmarshaling for Binance string array format
func (p *PriceLevel) UnmarshalJSON(data []byte) error {
	// Try to unmarshal as string array first (Binance format)
	var priceQty []string
	if err := json.Unmarshal(data, &priceQty); err == nil && len(priceQty) == 2 {
		var parseErr error
		p.Price, parseErr = decimal.NewFromString(priceQty[0])
		if parseErr != nil {
			return parseErr
		}

		p.Quantity, parseErr = decimal.NewFromString(priceQty[1])
		if parseErr != nil {
			return parseErr
		}

		return nil
	}

	// Fallback to standard object format
	type Alias PriceLevel
	aux := &struct {
		*Alias
	}{
		Alias: (*Alias)(p),
	}
	return json.Unmarshal(data, aux)
}

// TickerEvent represents 24hr ticker statistics
type TickerEvent struct {
	EventType          string          `json:"e"`
	EventTime          int64           `json:"E"`
	Symbol             string          `json:"s"`
	PriceChange        decimal.Decimal `json:"p"`
	PriceChangePercent decimal.Decimal `json:"P"`
	WeightedAvgPrice   decimal.Decimal `json:"w"`
	PrevClosePrice     decimal.Decimal `json:"x"`
	LastPrice          decimal.Decimal `json:"c"`
	LastQty            decimal.Decimal `json:"Q"`
	BidPrice           decimal.Decimal `json:"b"`
	BidQty             decimal.Decimal `json:"B"`
	AskPrice           decimal.Decimal `json:"a"`
	AskQty             decimal.Decimal `json:"A"`
	OpenPrice          decimal.Decimal `json:"o"`
	HighPrice          decimal.Decimal `json:"h"`
	LowPrice           decimal.Decimal `json:"l"`
	Volume             decimal.Decimal `json:"v"`
	QuoteVolume        decimal.Decimal `json:"q"`
	OpenTime           int64           `json:"O"`
	CloseTime          int64           `json:"C"`
	FirstTradeID       int64           `json:"F"`
	LastTradeID        int64           `json:"L"`
	Count              int64           `json:"n"`
}

// AccountUpdateEvent represents account balance changes
type AccountUpdateEvent struct {
	EventType  string    `json:"e"`
	EventTime  int64     `json:"E"`
	LastUpdate int64     `json:"u"`
	Balances   []Balance `json:"B"`
}

// Balance represents account balance for an asset
type Balance struct {
	Asset  string          `json:"a"`
	Free   decimal.Decimal `json:"f"`
	Locked decimal.Decimal `json:"l"`
}

// OrderUpdateEvent represents order status changes
type OrderUpdateEvent struct {
	EventType            string          `json:"e"`
	EventTime            int64           `json:"E"`
	Symbol               string          `json:"s"`
	ClientOrderID        string          `json:"c"`
	Side                 string          `json:"S"`
	OrderType            string          `json:"o"`
	TimeInForce          string          `json:"f"`
	Quantity             decimal.Decimal `json:"q"`
	Price                decimal.Decimal `json:"p"`
	StopPrice            decimal.Decimal `json:"P"`
	IcebergQuantity      decimal.Decimal `json:"F"`
	OrderListID          int64           `json:"g"`
	OrigClientOrderID    string          `json:"C"`
	ExecutionType        string          `json:"x"`
	OrderStatus          string          `json:"X"`
	OrderRejectReason    string          `json:"r"`
	OrderID              int64           `json:"i"`
	LastExecutedQuantity decimal.Decimal `json:"l"`
	CumulativeFilledQty  decimal.Decimal `json:"z"`
	LastExecutedPrice    decimal.Decimal `json:"L"`
	CommissionAmount     decimal.Decimal `json:"n"`
	CommissionAsset      string          `json:"N"`
	TransactionTime      int64           `json:"T"`
	TradeID              int64           `json:"t"`
	IsOrderWorking       bool            `json:"w"`
	IsMaker              bool            `json:"m"`
}

// ConnectionState represents WebSocket connection status
type ConnectionState int

const (
	StateDisconnected ConnectionState = iota
	StateConnecting
	StateConnected
	StateReconnecting
	StateClosed
)

func (s ConnectionState) String() string {
	switch s {
	case StateDisconnected:
		return "disconnected"
	case StateConnecting:
		return "connecting"
	case StateConnected:
		return "connected"
	case StateReconnecting:
		return "reconnecting"
	case StateClosed:
		return "closed"
	default:
		return "unknown"
	}
}
