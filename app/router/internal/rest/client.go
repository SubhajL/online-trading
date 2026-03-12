package rest

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/shopspring/decimal"

	"router/internal/auth"
)

// Client represents a REST client for Binance API
type Client struct {
	baseURL     string
	httpClient  *http.Client
	signer      *auth.Signer
	rateLimiter *RateLimiter
	maxRetries  int
}

type FuturesIncomeQuery struct {
	IncomeType string
	Symbol     string
	StartTime  int64
	EndTime    int64
	Limit      int
}

type FuturesIncomeRecord struct {
	IncomeType string `json:"incomeType"`
	Income     string `json:"income"`
	Asset      string `json:"asset"`
	Time       int64  `json:"time"`
	Symbol     string `json:"symbol,omitempty"`
	Info       string `json:"info,omitempty"`
	TranID     int64  `json:"tranId,omitempty"`
	TradeID    int64  `json:"tradeId,omitempty"`
}

// Option configures the client
type Option func(*Client)

// WithTimeout sets the HTTP timeout
func WithTimeout(timeout time.Duration) Option {
	return func(c *Client) {
		c.httpClient.Timeout = timeout
	}
}

// WithMaxRetries sets the maximum number of retries
func WithMaxRetries(maxRetries int) Option {
	return func(c *Client) {
		c.maxRetries = maxRetries
	}
}

// WithRateLimit sets rate limiting
func WithRateLimit(requestsPerSecond float64, burst int) Option {
	return func(c *Client) {
		c.rateLimiter = NewRateLimiter(requestsPerSecond, burst)
	}
}

// NewClient creates a new REST client
func NewClient(baseURL string, signer *auth.Signer, opts ...Option) *Client {
	client := &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 5 * time.Second,
		},
		signer:      signer,
		rateLimiter: NewRateLimiter(10, 5), // Default: 10 req/sec, burst 5
		maxRetries:  3,
	}

	for _, opt := range opts {
		opt(client)
	}

	return client
}

// BaseURL returns the base URL
func (c *Client) BaseURL() string {
	return c.baseURL
}

// Timeout returns the HTTP timeout
func (c *Client) Timeout() time.Duration {
	return c.httpClient.Timeout
}

// MaxRetries returns the maximum number of retries
func (c *Client) MaxRetries() int {
	return c.maxRetries
}

// GetExchangeInfo fetches trading rules and symbol information
func (c *Client) GetExchangeInfo(ctx context.Context) (*ExchangeInfo, error) {
	body, err := c.doRequest(ctx, "GET", "/api/v3/exchangeInfo", nil, false)
	if err != nil {
		return nil, ErrorWithContext(err, "GetExchangeInfo")
	}

	var exchangeInfo ExchangeInfo
	if err := json.Unmarshal(body, &exchangeInfo); err != nil {
		return nil, ErrorWithContext(err, "GetExchangeInfo")
	}

	return &exchangeInfo, nil
}

// GetOrderBook retrieves order book depth for a symbol
func (c *Client) GetOrderBook(ctx context.Context, symbol string, limit int) (*OrderBook, error) {
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	// Validate limit parameter
	validLimits := []int{5, 10, 20, 50, 100, 500, 1000, 5000}
	validLimit := false
	for _, vl := range validLimits {
		if limit == vl {
			validLimit = true
			break
		}
	}
	if !validLimit {
		return nil, fmt.Errorf("invalid limit: %d. Valid limits are: 5, 10, 20, 50, 100, 500, 1000, 5000", limit)
	}

	params := url.Values{}
	params.Set("symbol", symbol)
	params.Set("limit", strconv.Itoa(limit))

	body, err := c.doRequest(ctx, "GET", "/api/v3/depth", params, false)
	if err != nil {
		return nil, ErrorWithContext(err, "GetOrderBook")
	}

	var rawOrderBook struct {
		LastUpdateID int64      `json:"lastUpdateId"`
		Bids         [][]string `json:"bids"`
		Asks         [][]string `json:"asks"`
	}

	if err := json.Unmarshal(body, &rawOrderBook); err != nil {
		return nil, ErrorWithContext(err, "GetOrderBook")
	}

	// Convert string arrays to PriceLevel structs
	orderBook := &OrderBook{
		LastUpdateID: rawOrderBook.LastUpdateID,
		Bids:         make([]PriceLevel, len(rawOrderBook.Bids)),
		Asks:         make([]PriceLevel, len(rawOrderBook.Asks)),
	}

	for i, bid := range rawOrderBook.Bids {
		price, _ := decimal.NewFromString(bid[0])
		quantity, _ := decimal.NewFromString(bid[1])
		orderBook.Bids[i] = PriceLevel{Price: price, Quantity: quantity}
	}

	for i, ask := range rawOrderBook.Asks {
		price, _ := decimal.NewFromString(ask[0])
		quantity, _ := decimal.NewFromString(ask[1])
		orderBook.Asks[i] = PriceLevel{Price: price, Quantity: quantity}
	}

	return orderBook, nil
}

// GetAccount gets current account information
func (c *Client) GetAccount(ctx context.Context) (*AccountResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetAccount")
	}

	body, err := c.doRequest(ctx, "GET", "/api/v3/account", nil, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetAccount")
	}

	var account AccountResponse
	if err := json.Unmarshal(body, &account); err != nil {
		return nil, ErrorWithContext(err, "GetAccount")
	}

	return &account, nil
}

// PlaceOrder places a new order
func (c *Client) PlaceOrder(ctx context.Context, req *OrderRequest) (*OrderResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for PlaceOrder")
	}

	// Validate required fields
	if req.Symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if req.Side == "" {
		return nil, fmt.Errorf("side is required")
	}
	if req.Type == "" {
		return nil, fmt.Errorf("type is required")
	}
	if req.Quantity.IsZero() {
		return nil, fmt.Errorf("quantity is required")
	}
	if req.Type == "LIMIT" && req.Price.IsZero() {
		return nil, fmt.Errorf("price is required for LIMIT orders")
	}
	if strings.Contains(req.Type, "STOP") && req.StopPrice.IsZero() {
		return nil, fmt.Errorf("stopPrice is required for STOP orders")
	}
	if (req.Type == "STOP_LOSS_LIMIT" || req.Type == "TAKE_PROFIT_LIMIT") && req.Price.IsZero() {
		return nil, fmt.Errorf("price is required for %s orders", req.Type)
	}

	// Build parameters
	params := url.Values{}
	params.Set("symbol", req.Symbol)
	params.Set("side", req.Side)
	params.Set("type", req.Type)
	params.Set("quantity", req.Quantity.String())

	if !req.Price.IsZero() {
		params.Set("price", req.Price.String())
	}
	if !req.StopPrice.IsZero() {
		params.Set("stopPrice", req.StopPrice.String())
	}
	if req.TimeInForce != "" {
		params.Set("timeInForce", req.TimeInForce)
	}
	if req.NewClientOrderID != "" {
		params.Set("newClientOrderId", req.NewClientOrderID)
	}
	if req.RecvWindow > 0 {
		params.Set("recvWindow", strconv.FormatInt(req.RecvWindow, 10))
	}

	body, err := c.doRequest(ctx, "POST", "/api/v3/order", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "PlaceOrder")
	}

	var orderResp OrderResponse
	if err := json.Unmarshal(body, &orderResp); err != nil {
		return nil, ErrorWithContext(err, "PlaceOrder")
	}

	return &orderResp, nil
}

// CancelOrder cancels an active order.
func (c *Client) CancelOrder(ctx context.Context, symbol string, orderID int64) (*CancelResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for CancelOrder")
	}
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return nil, fmt.Errorf("orderID is required")
	}

	params := url.Values{}
	params.Set("symbol", symbol)
	params.Set("orderId", strconv.FormatInt(orderID, 10))

	body, err := c.doRequest(ctx, "DELETE", "/api/v3/order", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "CancelOrder")
	}

	var cancelResp CancelResponse
	if err := json.Unmarshal(body, &cancelResp); err != nil {
		return nil, ErrorWithContext(err, "CancelOrder")
	}

	return &cancelResp, nil
}

// CancelFuturesOrder cancels an active futures order
func (c *Client) CancelFuturesOrder(ctx context.Context, symbol string, orderID int64) error {
	if c.signer == nil {
		return fmt.Errorf("signer required for CancelFuturesOrder")
	}
	if symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return fmt.Errorf("orderID is required")
	}

	params := url.Values{}
	params.Set("symbol", symbol)
	params.Set("orderId", strconv.FormatInt(orderID, 10))

	_, err := c.doRequest(ctx, "DELETE", "/fapi/v1/order", params, true)
	if err != nil {
		return ErrorWithContext(err, "CancelFuturesOrder")
	}

	return nil
}

// GetTicker24hr retrieves 24 hour ticker statistics for a symbol
func (c *Client) GetTicker24hr(ctx context.Context, symbol string) (*Ticker24hr, error) {
	params := url.Values{}
	params.Set("symbol", symbol)

	body, err := c.doRequest(ctx, "GET", "/api/v3/ticker/24hr", params, false)
	if err != nil {
		return nil, ErrorWithContext(err, "GetTicker24hr")
	}

	var ticker Ticker24hr
	if err := json.Unmarshal(body, &ticker); err != nil {
		return nil, ErrorWithContext(err, "GetTicker24hr")
	}

	return &ticker, nil
}

// GetTickerPrice retrieves the last traded price for a single symbol.
func (c *Client) GetTickerPrice(ctx context.Context, symbol string) (*TickerPrice, error) {
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	params := url.Values{}
	params.Set("symbol", symbol)

	body, err := c.doRequest(ctx, "GET", "/api/v3/ticker/price", params, false)
	if err != nil {
		return nil, ErrorWithContext(err, "GetTickerPrice")
	}

	var ticker TickerPrice
	if err := json.Unmarshal(body, &ticker); err != nil {
		return nil, ErrorWithContext(err, "GetTickerPrice")
	}

	return &ticker, nil
}

// GetTickerPrices retrieves last traded prices for all spot symbols.
func (c *Client) GetTickerPrices(ctx context.Context) ([]TickerPrice, error) {
	body, err := c.doRequest(ctx, "GET", "/api/v3/ticker/price", nil, false)
	if err != nil {
		return nil, ErrorWithContext(err, "GetTickerPrices")
	}

	var tickers []TickerPrice
	if err := json.Unmarshal(body, &tickers); err != nil {
		return nil, ErrorWithContext(err, "GetTickerPrices")
	}

	return tickers, nil
}

// GetOpenOrders lists all open orders for a symbol
func (c *Client) GetOpenOrders(ctx context.Context, symbol string) ([]Order, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetOpenOrders")
	}
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	params := url.Values{}
	params.Set("symbol", symbol)

	body, err := c.doRequest(ctx, "GET", "/api/v3/openOrders", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetOpenOrders")
	}

	var orders []Order
	if err := json.Unmarshal(body, &orders); err != nil {
		return nil, ErrorWithContext(err, "GetOpenOrders")
	}

	return orders, nil
}

// GetOrder retrieves a single spot order by exchange order ID.
func (c *Client) GetOrder(ctx context.Context, symbol string, orderID int64) (*Order, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetOrder")
	}
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return nil, fmt.Errorf("order ID must be positive")
	}

	params := url.Values{}
	params.Set("symbol", symbol)
	params.Set("orderId", strconv.FormatInt(orderID, 10))

	body, err := c.doRequest(ctx, "GET", "/api/v3/order", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetOrder")
	}

	var order Order
	if err := json.Unmarshal(body, &order); err != nil {
		return nil, ErrorWithContext(err, "GetOrder")
	}

	return &order, nil
}

func (c *Client) GetMyTrades(ctx context.Context, symbol string, orderID int64) ([]Trade, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetMyTrades")
	}
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if orderID <= 0 {
		return nil, fmt.Errorf("order ID must be positive")
	}

	params := url.Values{}
	params.Set("symbol", symbol)
	params.Set("orderId", strconv.FormatInt(orderID, 10))

	body, err := c.doRequest(ctx, "GET", "/api/v3/myTrades", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetMyTrades")
	}

	var trades []Trade
	if err := json.Unmarshal(body, &trades); err != nil {
		return nil, ErrorWithContext(err, "GetMyTrades")
	}

	return trades, nil
}

// GetFuturesOpenOrders lists all open futures orders for a symbol
func (c *Client) GetFuturesOpenOrders(ctx context.Context, symbol string) ([]Order, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetFuturesOpenOrders")
	}
	if symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}

	params := url.Values{}
	params.Set("symbol", symbol)

	body, err := c.doRequest(ctx, "GET", "/fapi/v1/openOrders", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetFuturesOpenOrders")
	}

	var orders []Order
	if err := json.Unmarshal(body, &orders); err != nil {
		return nil, ErrorWithContext(err, "GetFuturesOpenOrders")
	}

	return orders, nil
}

type _listenKeyResponse struct {
	ListenKey string `json:"listenKey"`
}

func (c *Client) CreateFuturesListenKey(ctx context.Context) (string, error) {
	if c.signer == nil {
		return "", fmt.Errorf("signer required for CreateFuturesListenKey")
	}

	body, err := c.doRequest(ctx, "POST", "/fapi/v1/listenKey", nil, false)
	if err != nil {
		return "", ErrorWithContext(err, "CreateFuturesListenKey")
	}

	var resp _listenKeyResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return "", ErrorWithContext(err, "CreateFuturesListenKey")
	}
	if resp.ListenKey == "" {
		return "", fmt.Errorf("listenKey missing in response")
	}
	return resp.ListenKey, nil
}

func (c *Client) KeepAliveFuturesListenKey(ctx context.Context, listenKey string) error {
	if c.signer == nil {
		return fmt.Errorf("signer required for KeepAliveFuturesListenKey")
	}
	if listenKey == "" {
		return fmt.Errorf("listenKey is required")
	}

	params := url.Values{}
	params.Set("listenKey", listenKey)

	_, err := c.doRequest(ctx, "PUT", "/fapi/v1/listenKey", params, false)
	if err != nil {
		return ErrorWithContext(err, "KeepAliveFuturesListenKey")
	}
	return nil
}

func (c *Client) DeleteFuturesListenKey(ctx context.Context, listenKey string) error {
	if c.signer == nil {
		return fmt.Errorf("signer required for DeleteFuturesListenKey")
	}
	if listenKey == "" {
		return fmt.Errorf("listenKey is required")
	}

	params := url.Values{}
	params.Set("listenKey", listenKey)

	_, err := c.doRequest(ctx, "DELETE", "/fapi/v1/listenKey", params, false)
	if err != nil {
		return ErrorWithContext(err, "DeleteFuturesListenKey")
	}
	return nil
}

func (c *Client) GetFuturesIncome(ctx context.Context, query FuturesIncomeQuery) ([]FuturesIncomeRecord, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetFuturesIncome")
	}

	params := url.Values{}
	if query.IncomeType != "" {
		params.Set("incomeType", query.IncomeType)
	}
	if query.Symbol != "" {
		params.Set("symbol", query.Symbol)
	}
	if query.StartTime > 0 {
		params.Set("startTime", strconv.FormatInt(query.StartTime, 10))
	}
	if query.EndTime > 0 {
		params.Set("endTime", strconv.FormatInt(query.EndTime, 10))
	}
	if query.Limit > 0 {
		params.Set("limit", strconv.Itoa(query.Limit))
	}

	body, err := c.doRequest(ctx, "GET", "/fapi/v1/income", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetFuturesIncome")
	}

	var records []FuturesIncomeRecord
	if err := json.Unmarshal(body, &records); err != nil {
		return nil, ErrorWithContext(err, "GetFuturesIncome")
	}

	return records, nil
}

// PlaceFuturesOrder places a futures order
func (c *Client) PlaceFuturesOrder(ctx context.Context, req *FuturesOrderRequest) (*FuturesOrderResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for PlaceFuturesOrder")
	}

	// Validate required fields
	if req.Symbol == "" {
		return nil, fmt.Errorf("symbol is required")
	}
	if req.Side == "" {
		return nil, fmt.Errorf("side is required")
	}
	if req.Type == "" {
		return nil, fmt.Errorf("type is required")
	}
	if req.Quantity.IsZero() && !req.ClosePosition {
		return nil, fmt.Errorf("quantity is required")
	}
	if req.Type == "LIMIT" && req.Price.IsZero() {
		return nil, fmt.Errorf("price is required for LIMIT orders")
	}
	if strings.Contains(req.Type, "STOP") && req.StopPrice.IsZero() {
		return nil, fmt.Errorf("stopPrice is required for STOP orders")
	}

	// Build parameters
	params := url.Values{}
	params.Set("symbol", req.Symbol)
	params.Set("side", req.Side)
	params.Set("type", req.Type)

	if !req.Quantity.IsZero() {
		params.Set("quantity", req.Quantity.String())
	}
	if !req.Price.IsZero() {
		params.Set("price", req.Price.String())
	}
	if !req.StopPrice.IsZero() {
		params.Set("stopPrice", req.StopPrice.String())
	}
	if req.TimeInForce != "" {
		params.Set("timeInForce", req.TimeInForce)
	}
	if req.ReduceOnly {
		params.Set("reduceOnly", "true")
	}
	if req.ClosePosition {
		params.Set("closePosition", "true")
	}
	if !req.ActivationPrice.IsZero() {
		params.Set("activationPrice", req.ActivationPrice.String())
	}
	if !req.CallbackRate.IsZero() {
		params.Set("callbackRate", req.CallbackRate.String())
	}
	if req.WorkingType != "" {
		params.Set("workingType", req.WorkingType)
	}
	if req.PriceProtect {
		params.Set("priceProtect", "true")
	}
	if req.NewClientOrderID != "" {
		params.Set("newClientOrderId", req.NewClientOrderID)
	}
	if req.RecvWindow > 0 {
		params.Set("recvWindow", strconv.FormatInt(req.RecvWindow, 10))
	}

	body, err := c.doRequest(ctx, "POST", "/fapi/v1/order", params, true)
	if err != nil {
		return nil, ErrorWithContext(err, "PlaceFuturesOrder")
	}

	var orderResp FuturesOrderResponse
	if err := json.Unmarshal(body, &orderResp); err != nil {
		return nil, ErrorWithContext(err, "PlaceFuturesOrder")
	}

	return &orderResp, nil
}

// GetFuturesAccount gets futures account information
func (c *Client) GetFuturesAccount(ctx context.Context) (*FuturesAccountResponse, error) {
	if c.signer == nil {
		return nil, fmt.Errorf("signer required for GetFuturesAccount")
	}

	body, err := c.doRequest(ctx, "GET", "/fapi/v2/account", nil, true)
	if err != nil {
		return nil, ErrorWithContext(err, "GetFuturesAccount")
	}

	var account FuturesAccountResponse
	if err := json.Unmarshal(body, &account); err != nil {
		return nil, ErrorWithContext(err, "GetFuturesAccount")
	}

	return &account, nil
}

// doRequest handles request execution with retries and rate limiting
func (c *Client) doRequest(ctx context.Context, method, path string, params url.Values, signed bool) ([]byte, error) {
	var lastErr error

	for attempt := 0; attempt <= c.maxRetries; attempt++ {
		// Wait for rate limiter
		if c.rateLimiter != nil {
			if err := c.rateLimiter.Wait(ctx); err != nil {
				return nil, err
			}
		}

		// Prepare request
		var body io.Reader
		var requestURL string

		if params == nil {
			params = url.Values{}
		}

		// Sign request if required
		if signed {
			if c.signer == nil {
				return nil, fmt.Errorf("signer required for signed request")
			}
			params = c.signer.SignedRequest(params)
		}

		// Binance API expects all parameters in query string, even for POST
		requestURL = c.baseURL + path
		if len(params) > 0 {
			requestURL += "?" + params.Encode()
		}

		// Create request
		req, err := http.NewRequestWithContext(ctx, method, requestURL, body)
		if err != nil {
			return nil, fmt.Errorf("failed to create request: %w", err)
		}

		// Set headers
		if c.signer != nil {
			req.Header.Set("X-MBX-APIKEY", c.signer.APIKey())
		}

		// Execute request
		resp, err := c.httpClient.Do(req)
		if err != nil {
			lastErr = err
			if attempt < c.maxRetries && isNetworkError(err) {
				c.waitForRetry(attempt)
				continue
			}
			return nil, err
		}

		// Read response body
		respBody, readErr := io.ReadAll(resp.Body)
		closeErr := resp.Body.Close()
		if readErr != nil {
			lastErr = readErr
			if attempt < c.maxRetries {
				c.waitForRetry(attempt)
				continue
			}
			return nil, readErr
		}
		if closeErr != nil {
			lastErr = closeErr
			if attempt < c.maxRetries {
				c.waitForRetry(attempt)
				continue
			}
			return nil, closeErr
		}

		// Check for success
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return respBody, nil
		}

		// Parse error
		resp.Body = io.NopCloser(bytes.NewReader(respBody))
		apiErr := ParseAPIError(resp)
		lastErr = apiErr

		// Retry if error is retryable
		if attempt < c.maxRetries && IsRetryableError(apiErr) {
			c.waitForRetry(attempt)
			continue
		}

		return nil, apiErr
	}

	return nil, lastErr
}

// waitForRetry implements exponential backoff with jitter
func (c *Client) waitForRetry(attempt int) {
	baseDelay := 100 * time.Millisecond
	maxDelay := 2 * time.Second

	// Exponential backoff: 100ms, 200ms, 400ms, etc.
	delay := time.Duration(float64(baseDelay) * math.Pow(2, float64(attempt)))
	if delay > maxDelay {
		delay = maxDelay
	}

	// Add small jitter (±20%)
	jitterFactor := float64(time.Now().UnixNano()%100) / 100.0 // 0.0 to 1.0
	jitter := time.Duration(float64(delay) * 0.2 * (2*jitterFactor - 1))
	delay += jitter

	time.Sleep(delay)
}

// isNetworkError checks if an error is a network-related error
func isNetworkError(err error) bool {
	if err == nil {
		return false
	}
	// Check for common network error patterns
	errStr := err.Error()
	networkErrors := []string{
		"connection refused",
		"no such host",
		"timeout",
		"network unreachable",
		"connection reset",
	}

	for _, netErr := range networkErrors {
		if strings.Contains(strings.ToLower(errStr), netErr) {
			return true
		}
	}

	return false
}
