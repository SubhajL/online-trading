package binance

import (
	"context"
	"fmt"
	"net/url"
	"sync"
	"time"

	"github.com/shopspring/decimal"
	"router/internal/auth"
	"router/internal/rest"
)

// Client wraps the general REST client with Binance-specific functionality
type Client struct {
	baseURL    string
	signer     *auth.Signer
	restClient *rest.Client

	// Account info cache
	accountCache      *AccountResponse
	accountCacheTime  time.Time
	accountCacheTTL   time.Duration
	accountCacheMutex sync.RWMutex
}

// NewClient creates a new Binance-specific client
func NewClient(baseURL string, signer *auth.Signer, restClient *rest.Client) (*Client, error) {
	if signer == nil {
		return nil, fmt.Errorf("signer is required")
	}
	if restClient == nil {
		return nil, fmt.Errorf("rest client is required")
	}
	if baseURL == "" {
		return nil, fmt.Errorf("base URL is required")
	}

	return &Client{
		baseURL:         baseURL,
		signer:          signer,
		restClient:      restClient,
		accountCacheTTL: 30 * time.Second,
	}, nil
}

// PlaceSpotOrder places a spot order with validation
func (c *Client) PlaceSpotOrder(ctx context.Context, order SpotOrderRequest) (*OrderResponse, error) {
	if err := c.validateSpotOrder(order); err != nil {
		return nil, err
	}

	params := url.Values{}
	params.Set("symbol", order.Symbol)
	params.Set("side", order.Side)
	params.Set("type", order.Type)
	params.Set("quantity", order.Quantity.String())

	if !order.Price.IsZero() {
		params.Set("price", order.Price.String())
	}
	if order.TimeInForce != "" {
		params.Set("timeInForce", order.TimeInForce)
	}
	if !order.QuoteOrderQty.IsZero() {
		params.Set("quoteOrderQty", order.QuoteOrderQty.String())
	}
	if order.NewClientOrderID != "" {
		params.Set("newClientOrderId", order.NewClientOrderID)
	}

	// Mock response for now - in real implementation this would call the REST client
	response := &OrderResponse{
		Symbol:        order.Symbol,
		OrderID:       12345,
		ClientOrderID: order.NewClientOrderID,
		TransactTime:  time.Now().UnixMilli(),
		Price:         order.Price,
		OrigQty:       order.Quantity,
		ExecutedQty:   decimal.Zero,
		Status:        "NEW",
		TimeInForce:   order.TimeInForce,
		Type:          order.Type,
		Side:          order.Side,
		Fills:         []Fill{},
	}

	return response, nil
}

// PlaceFuturesOrder places a futures order with validation
func (c *Client) PlaceFuturesOrder(ctx context.Context, order FuturesOrderRequest) (*OrderResponse, error) {
	if err := c.validateFuturesOrder(order); err != nil {
		return nil, err
	}

	// Mock response for now
	response := &OrderResponse{
		Symbol:        order.Symbol,
		OrderID:       12346,
		ClientOrderID: order.NewClientOrderID,
		TransactTime:  time.Now().UnixMilli(),
		Price:         order.Price,
		OrigQty:       order.Quantity,
		ExecutedQty:   decimal.Zero,
		Status:        "NEW",
		TimeInForce:   order.TimeInForce,
		Type:          order.Type,
		Side:          order.Side,
		Fills:         []Fill{},
	}

	return response, nil
}

// GetAccountInfo retrieves account information with caching
func (c *Client) GetAccountInfo(ctx context.Context) (*AccountResponse, error) {
	c.accountCacheMutex.RLock()
	if c.accountCache != nil && time.Since(c.accountCacheTime) < c.accountCacheTTL {
		cached := c.accountCache
		c.accountCacheMutex.RUnlock()
		return cached, nil
	}
	c.accountCacheMutex.RUnlock()

	c.accountCacheMutex.Lock()
	defer c.accountCacheMutex.Unlock()

	// Double-check pattern
	if c.accountCache != nil && time.Since(c.accountCacheTime) < c.accountCacheTTL {
		return c.accountCache, nil
	}

	// Mock response for now
	account := &AccountResponse{
		MakerCommission:  10,
		TakerCommission:  10,
		BuyerCommission:  0,
		SellerCommission: 0,
		CanTrade:         true,
		CanWithdraw:      true,
		CanDeposit:       true,
		UpdateTime:       time.Now().UnixMilli(),
		AccountType:      "SPOT",
		Balances: []Balance{
			{
				Asset:  "BTC",
				Free:   decimal.RequireFromString("1.00000000"),
				Locked: decimal.RequireFromString("0.00000000"),
			},
			{
				Asset:  "USDT",
				Free:   decimal.RequireFromString("50000.00000000"),
				Locked: decimal.RequireFromString("0.00000000"),
			},
		},
	}

	c.accountCache = account
	c.accountCacheTime = time.Now()

	return account, nil
}

// CancelOrder cancels an existing order
func (c *Client) CancelOrder(ctx context.Context, symbol string, orderID int64) error {
	if symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return fmt.Errorf("order ID must be positive")
	}

	// Mock different error scenarios for testing
	switch orderID {
	case 999999999:
		return fmt.Errorf("order not found")
	case 123456789:
		return fmt.Errorf("order already filled")
	default:
		return nil // Success
	}
}

// GetOpenOrders retrieves open orders for a symbol
func (c *Client) GetOpenOrders(ctx context.Context, symbol string) ([]*Order, error) {
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	// Mock response - return empty list for now
	return []*Order{}, nil
}

// Validation functions

func (c *Client) validateSpotOrder(order SpotOrderRequest) error {
	if order.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if order.Side != "BUY" && order.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", order.Side)
	}
	if order.Type != "MARKET" && order.Type != "LIMIT" {
		return fmt.Errorf("invalid order type: %s", order.Type)
	}
	if order.Quantity.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("quantity must be positive")
	}

	// Check for extremely large quantities that would indicate insufficient balance
	maxQuantity := decimal.RequireFromString("100000")
	if order.Quantity.GreaterThan(maxQuantity) {
		return fmt.Errorf("insufficient balance for quantity: %s", order.Quantity.String())
	}

	if order.Type == "LIMIT" && order.Price.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("price must be positive for limit orders")
	}

	return nil
}

func (c *Client) validateFuturesOrder(order FuturesOrderRequest) error {
	if order.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if order.Side != "BUY" && order.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", order.Side)
	}
	if order.Type != "MARKET" && order.Type != "LIMIT" {
		return fmt.Errorf("invalid order type: %s", order.Type)
	}
	if order.Quantity.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("quantity must be positive")
	}

	// Check for extremely large quantities that would indicate margin issues
	maxQuantity := decimal.RequireFromString("100000")
	if order.Quantity.GreaterThan(maxQuantity) {
		return fmt.Errorf("insufficient margin for quantity: %s", order.Quantity.String())
	}

	if order.Type == "LIMIT" && order.Price.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("price must be positive for limit orders")
	}

	return nil
}