package binance

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"router/internal/auth"
	"router/internal/rest"
)

// Client wraps the general REST client with Binance-specific functionality
type Client struct {
	baseURL    string
	signer     *auth.Signer
	restClient *rest.Client
	isFutures  bool
	logger     zerolog.Logger

	// Account info cache
	accountCache      *AccountResponse
	accountCacheTime  time.Time
	accountCacheTTL   time.Duration
	accountCacheMutex sync.RWMutex

	// Exchange info cache
	exchangeInfoCache *ExchangeInfoCache
}

// convertFills converts REST fills to our Fill type
func convertFills(restFills []rest.Fill) []Fill {
	fills := make([]Fill, len(restFills))
	for i, f := range restFills {
		fills[i] = Fill{
			Price:           f.Price,
			Qty:             f.Qty,
			Commission:      f.Commission,
			CommissionAsset: f.CommissionAsset,
		}
	}
	return fills
}

// NewClient creates a new Binance-specific client
func NewClient(baseURL string, signer *auth.Signer, restClient *rest.Client, logger zerolog.Logger) (*Client, error) {
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
		logger:          logger,
	}, nil
}

// PlaceSpotOrder places a spot order with validation
func (c *Client) PlaceSpotOrder(ctx context.Context, order SpotOrderRequest) (*OrderResponse, error) {
	if err := c.validateSpotOrder(order); err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", order.Symbol).
			Str("side", order.Side).
			Str("type", order.Type).
			Msg("Spot order validation failed")
		return nil, err
	}

	c.logger.Debug().
		Str("symbol", order.Symbol).
		Str("side", order.Side).
		Str("type", order.Type).
		Str("quantity", order.Quantity.String()).
		Str("price", order.Price.String()).
		Str("client_order_id", order.NewClientOrderID).
		Msg("Placing spot order")

	// Convert to REST client order request
	req := &rest.OrderRequest{
		Symbol:           order.Symbol,
		Side:             order.Side,
		Type:             order.Type,
		Quantity:         order.Quantity,
		Price:            order.Price,
		StopPrice:        order.StopPrice,
		TimeInForce:      order.TimeInForce,
		NewClientOrderID: order.NewClientOrderID,
	}

	// Place order using REST client
	restResp, err := c.restClient.PlaceOrder(ctx, req)
	if err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", order.Symbol).
			Str("side", order.Side).
			Str("type", order.Type).
			Msg("Failed to place spot order")
		return nil, fmt.Errorf("failed to place spot order: %w", err)
	}

	// Convert REST response to our response type
	response := &OrderResponse{
		Symbol:        restResp.Symbol,
		OrderID:       restResp.OrderID,
		ClientOrderID: restResp.ClientOrderID,
		TransactTime:  restResp.TransactTime,
		Price:         restResp.Price,
		OrigQty:       restResp.OrigQty,
		ExecutedQty:   restResp.ExecutedQty,
		Status:        restResp.Status,
		TimeInForce:   restResp.TimeInForce,
		Type:          restResp.Type,
		Side:          restResp.Side,
		Fills:         convertFills(restResp.Fills),
	}

	c.logger.Info().
		Str("symbol", response.Symbol).
		Int64("order_id", response.OrderID).
		Str("client_order_id", response.ClientOrderID).
		Str("status", response.Status).
		Str("side", response.Side).
		Str("type", response.Type).
		Msg("Spot order placed successfully")

	return response, nil
}

// PlaceFuturesOrder places a futures order with validation
func (c *Client) PlaceFuturesOrder(ctx context.Context, order FuturesOrderRequest) (*OrderResponse, error) {
	if err := c.validateFuturesOrder(order); err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", order.Symbol).
			Str("side", order.Side).
			Str("type", order.Type).
			Msg("Futures order validation failed")
		return nil, err
	}

	c.logger.Debug().
		Str("symbol", order.Symbol).
		Str("side", order.Side).
		Str("type", order.Type).
		Str("quantity", order.Quantity.String()).
		Str("price", order.Price.String()).
		Bool("reduce_only", order.ReduceOnly).
		Bool("close_position", order.ClosePosition).
		Str("client_order_id", order.NewClientOrderID).
		Msg("Placing futures order")

	// Convert to REST client futures order request
	req := &rest.FuturesOrderRequest{
		Symbol:           order.Symbol,
		Side:             order.Side,
		Type:             order.Type,
		Quantity:         order.Quantity,
		Price:            order.Price,
		StopPrice:        order.StopPrice,
		TimeInForce:      order.TimeInForce,
		ReduceOnly:       order.ReduceOnly,
		ClosePosition:    order.ClosePosition,
		NewClientOrderID: order.NewClientOrderID,
	}

	// Place order using REST client
	restResp, err := c.restClient.PlaceFuturesOrder(ctx, req)
	if err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", order.Symbol).
			Str("side", order.Side).
			Str("type", order.Type).
			Msg("Failed to place futures order")
		return nil, fmt.Errorf("failed to place futures order: %w", err)
	}

	// Convert REST response to our response type
	response := &OrderResponse{
		Symbol:        restResp.Symbol,
		OrderID:       restResp.OrderID,
		ClientOrderID: restResp.ClientOrderID,
		TransactTime:  time.Now().UnixMilli(), // Futures response doesn't include TransactTime
		Price:         restResp.Price,
		OrigQty:       restResp.OrigQty,
		ExecutedQty:   restResp.ExecutedQty,
		Status:        restResp.Status,
		TimeInForce:   restResp.TimeInForce,
		Type:          restResp.Type,
		Side:          restResp.Side,
		Fills:         []Fill{}, // Futures response doesn't include Fills in the same way
	}

	c.logger.Info().
		Str("symbol", response.Symbol).
		Int64("order_id", response.OrderID).
		Str("client_order_id", response.ClientOrderID).
		Str("status", response.Status).
		Str("side", response.Side).
		Str("type", response.Type).
		Msg("Futures order placed successfully")

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

	// Get account info from REST client
	restAccount, err := c.restClient.GetAccount(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get account info: %w", err)
	}

	// Convert REST response to our type
	account := &AccountResponse{
		MakerCommission:  restAccount.MakerCommission,
		TakerCommission:  restAccount.TakerCommission,
		BuyerCommission:  restAccount.BuyerCommission,
		SellerCommission: restAccount.SellerCommission,
		CanTrade:         restAccount.CanTrade,
		CanWithdraw:      restAccount.CanWithdraw,
		CanDeposit:       restAccount.CanDeposit,
		UpdateTime:       restAccount.UpdateTime,
		AccountType:      restAccount.AccountType,
		Balances:         convertBalances(restAccount.Balances),
	}

	c.accountCache = account
	c.accountCacheTime = time.Now()

	return account, nil
}

// convertBalances converts REST balances to our Balance type
func convertBalances(restBalances []rest.Balance) []Balance {
	balances := make([]Balance, len(restBalances))
	for i, b := range restBalances {
		balances[i] = Balance{
			Asset:  b.Asset,
			Free:   b.Free,
			Locked: b.Locked,
		}
	}
	return balances
}

// CancelOrder cancels an existing order
func (c *Client) CancelOrder(ctx context.Context, symbol string, orderID int64) error {
	if symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return fmt.Errorf("order ID must be positive")
	}

	c.logger.Info().
		Str("symbol", symbol).
		Int64("order_id", orderID).
		Msg("Canceling order")

	// Use REST client to cancel order
	err := c.restClient.CancelOrder(ctx, symbol, orderID)
	if err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", symbol).
			Int64("order_id", orderID).
			Msg("Failed to cancel order")
		return err
	}

	c.logger.Info().
		Str("symbol", symbol).
		Int64("order_id", orderID).
		Msg("Order canceled successfully")

	return nil
}

// GetOpenOrders retrieves open orders for a symbol
func (c *Client) GetOpenOrders(ctx context.Context, symbol string) ([]*Order, error) {
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	c.logger.Debug().
		Str("symbol", symbol).
		Msg("Retrieving open orders")

	// Get open orders from REST client
	restOrders, err := c.restClient.GetOpenOrders(ctx, symbol)
	if err != nil {
		c.logger.Error().
			Err(err).
			Str("symbol", symbol).
			Msg("Failed to get open orders")
		return nil, fmt.Errorf("failed to get open orders: %w", err)
	}

	// Convert REST orders to our Order type
	orders := make([]*Order, len(restOrders))
	for i, o := range restOrders {
		orders[i] = &Order{
			Symbol:        o.Symbol,
			OrderID:       o.OrderID,
			ClientOrderID: o.ClientOrderID,
			Price:         o.Price,
			OrigQty:       o.OrigQty,
			ExecutedQty:   o.ExecutedQty,
			Status:        o.Status,
			TimeInForce:   o.TimeInForce,
			Type:          o.Type,
			Side:          o.Side,
			Time:          o.Time,
			UpdateTime:    o.UpdateTime,
		}
	}

	c.logger.Debug().
		Str("symbol", symbol).
		Int("order_count", len(orders)).
		Msg("Retrieved open orders")

	return orders, nil
}

// Validation functions

func (c *Client) validateSpotOrder(order SpotOrderRequest) error {
	if order.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if order.Side != "BUY" && order.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", order.Side)
	}
	validTypes := map[string]bool{
		"MARKET":            true,
		"LIMIT":             true,
		"STOP_LOSS":         true,
		"STOP_LOSS_LIMIT":   true,
		"TAKE_PROFIT":       true,
		"TAKE_PROFIT_LIMIT": true,
		"LIMIT_MAKER":       true,
	}
	if !validTypes[order.Type] {
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

	// Validate stop price for stop orders
	stopTypes := map[string]bool{
		"STOP_LOSS":         true,
		"STOP_LOSS_LIMIT":   true,
		"TAKE_PROFIT":       true,
		"TAKE_PROFIT_LIMIT": true,
	}
	if stopTypes[order.Type] && order.StopPrice.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("stopPrice must be positive for %s orders", order.Type)
	}

	// Validate price for stop limit orders
	if (order.Type == "STOP_LOSS_LIMIT" || order.Type == "TAKE_PROFIT_LIMIT") && order.Price.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("price must be positive for %s orders", order.Type)
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

// RoundPrice rounds a price according to symbol rules
func (c *Client) RoundPrice(ctx context.Context, symbol string, price decimal.Decimal) (decimal.Decimal, error) {
	if c.exchangeInfoCache == nil {
		return price, nil // No rounding if cache not available
	}
	return c.exchangeInfoCache.RoundPrice(ctx, symbol, price, c.isFutures)
}

// RoundQuantity rounds a quantity according to symbol rules
func (c *Client) RoundQuantity(ctx context.Context, symbol string, quantity decimal.Decimal) (decimal.Decimal, error) {
	if c.exchangeInfoCache == nil {
		return quantity, nil // No rounding if cache not available
	}
	return c.exchangeInfoCache.RoundQuantity(ctx, symbol, quantity, c.isFutures)
}

// ValidateNotional validates order notional value
func (c *Client) ValidateNotional(ctx context.Context, symbol string, price, quantity decimal.Decimal) error {
	if c.exchangeInfoCache == nil {
		return nil // Skip validation if cache not available
	}
	return c.exchangeInfoCache.ValidateNotional(ctx, symbol, price, quantity, c.isFutures)
}
