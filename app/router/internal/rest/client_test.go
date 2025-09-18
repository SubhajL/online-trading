package rest

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"sync"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"

	"router/internal/auth"
)

func TestNewClient(t *testing.T) {
	t.Run("creates client with default configuration", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("https://api.binance.com", signer)

		assert.NotNil(t, client)
		assert.Equal(t, "https://api.binance.com", client.BaseURL())
		assert.Equal(t, 5*time.Second, client.Timeout())
		assert.Equal(t, 3, client.MaxRetries())
	})

	t.Run("applies custom options", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("https://api.binance.com", signer,
			WithTimeout(10*time.Second),
			WithMaxRetries(5),
			WithRateLimit(100, 10),
		)

		assert.NotNil(t, client)
		assert.Equal(t, 10*time.Second, client.Timeout())
		assert.Equal(t, 5, client.MaxRetries())
	})

	t.Run("handles nil signer", func(t *testing.T) {
		client := NewClient("https://api.binance.com", nil)
		assert.NotNil(t, client)
	})

	t.Run("validates base URL", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("", signer)
		assert.NotNil(t, client)
	})
}

func TestClient_GetExchangeInfo(t *testing.T) {
	t.Run("parses exchange info response correctly", func(t *testing.T) {
		mockResponse := `{
			"timezone": "UTC",
			"serverTime": 1499827319559,
			"symbols": [
				{
					"symbol": "BTCUSDT",
					"status": "TRADING",
					"baseAsset": "BTC",
					"baseAssetPrecision": 8,
					"quoteAsset": "USDT",
					"quoteAssetPrecision": 8,
					"orderTypes": ["LIMIT", "MARKET"],
					"icebergAllowed": true,
					"ocoAllowed": true,
					"isSpotTradingAllowed": true,
					"isMarginTradingAllowed": true
				}
			]
		}`

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/exchangeInfo", r.URL.Path)
			assert.Equal(t, "GET", r.Method)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(mockResponse))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil)
		ctx := context.Background()

		exchangeInfo, err := client.GetExchangeInfo(ctx)

		assert.NoError(t, err)
		assert.NotNil(t, exchangeInfo)
		assert.Equal(t, "UTC", exchangeInfo.Timezone)
		assert.Equal(t, int64(1499827319559), exchangeInfo.ServerTime)
		assert.Len(t, exchangeInfo.Symbols, 1)
		assert.Equal(t, "BTCUSDT", exchangeInfo.Symbols[0].Symbol)
		assert.Equal(t, "TRADING", exchangeInfo.Symbols[0].Status)
		assert.True(t, exchangeInfo.Symbols[0].IsSpotTradingAllowed)
	})

	t.Run("handles network error with retry", func(t *testing.T) {
		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			if callCount < 3 {
				w.WriteHeader(500)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{"timezone":"UTC","serverTime":123,"symbols":[]}`))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil, WithMaxRetries(3))
		ctx := context.Background()

		exchangeInfo, err := client.GetExchangeInfo(ctx)

		assert.NoError(t, err)
		assert.NotNil(t, exchangeInfo)
		assert.Equal(t, 3, callCount)
	})

	t.Run("gives up after max retries", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(500)
		}))
		defer server.Close()

		client := NewClient(server.URL, nil, WithMaxRetries(2))
		ctx := context.Background()

		exchangeInfo, err := client.GetExchangeInfo(ctx)

		assert.Error(t, err)
		assert.Nil(t, exchangeInfo)
		assert.Contains(t, err.Error(), "HTTP 500")
	})

	t.Run("respects context timeout", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			time.Sleep(100 * time.Millisecond)
			w.WriteHeader(200)
		}))
		defer server.Close()

		client := NewClient(server.URL, nil)
		ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
		defer cancel()

		exchangeInfo, err := client.GetExchangeInfo(ctx)

		assert.Error(t, err)
		assert.Nil(t, exchangeInfo)
		assert.Contains(t, err.Error(), "context deadline exceeded")
	})
}

func TestClient_GetOrderBook(t *testing.T) {
	t.Run("parses order book response correctly", func(t *testing.T) {
		mockResponse := `{
			"lastUpdateId": 1027024,
			"bids": [
				["4.00000000", "431.00000000"],
				["3.90000000", "9.00000000"]
			],
			"asks": [
				["4.00000200", "12.00000000"],
				["4.10000000", "10.00000000"]
			]
		}`

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/depth", r.URL.Path)
			assert.Equal(t, "BTCUSDT", r.URL.Query().Get("symbol"))
			assert.Equal(t, "100", r.URL.Query().Get("limit"))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(mockResponse))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil)
		ctx := context.Background()

		orderBook, err := client.GetOrderBook(ctx, "BTCUSDT", 100)

		assert.NoError(t, err)
		assert.NotNil(t, orderBook)
		assert.Equal(t, int64(1027024), orderBook.LastUpdateID)
		assert.Len(t, orderBook.Bids, 2)
		assert.Len(t, orderBook.Asks, 2)

		// Check first bid
		expectedPrice := decimal.NewFromFloat(4.0)
		expectedQty := decimal.NewFromFloat(431.0)
		assert.True(t, expectedPrice.Equal(orderBook.Bids[0].Price))
		assert.True(t, expectedQty.Equal(orderBook.Bids[0].Quantity))

		// Check first ask
		expectedAskPrice := decimal.NewFromFloat(4.000002)
		expectedAskQty := decimal.NewFromFloat(12.0)
		assert.True(t, expectedAskPrice.Equal(orderBook.Asks[0].Price))
		assert.True(t, expectedAskQty.Equal(orderBook.Asks[0].Quantity))
	})

	t.Run("validates limit parameter", func(t *testing.T) {
		client := NewClient("https://api.binance.com", nil)
		ctx := context.Background()

		// Invalid limits should return error
		invalidLimits := []int{0, -1, 3, 15, 999, 10000}
		for _, limit := range invalidLimits {
			orderBook, err := client.GetOrderBook(ctx, "BTCUSDT", limit)
			assert.Error(t, err, "Limit %d should be invalid", limit)
			assert.Nil(t, orderBook)
			assert.Contains(t, err.Error(), "invalid limit")
		}
	})

	t.Run("accepts valid limit parameters", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{"lastUpdateId":123,"bids":[],"asks":[]}`))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil)
		ctx := context.Background()

		// Valid limits according to Binance API
		validLimits := []int{5, 10, 20, 50, 100, 500, 1000, 5000}
		for _, limit := range validLimits {
			orderBook, err := client.GetOrderBook(ctx, "BTCUSDT", limit)
			assert.NoError(t, err, "Limit %d should be valid", limit)
			assert.NotNil(t, orderBook)
		}
	})

	t.Run("validates symbol parameter", func(t *testing.T) {
		client := NewClient("https://api.binance.com", nil)
		ctx := context.Background()

		orderBook, err := client.GetOrderBook(ctx, "", 100)
		assert.Error(t, err)
		assert.Nil(t, orderBook)
		assert.Contains(t, err.Error(), "symbol is required")
	})
}

func TestClient_GetAccount(t *testing.T) {
	t.Run("requires signature", func(t *testing.T) {
		requestSigned := false
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/account", r.URL.Path)
			assert.Equal(t, "test-key", r.Header.Get("X-MBX-APIKEY"))

			// Check for signature parameter
			signature := r.URL.Query().Get("signature")
			if signature != "" {
				requestSigned = true
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{
				"makerCommission": 10,
				"takerCommission": 10,
				"buyerCommission": 0,
				"sellerCommission": 0,
				"canTrade": true,
				"canWithdraw": true,
				"canDeposit": true,
				"updateTime": 123456789,
				"accountType": "SPOT",
				"balances": [],
				"permissions": ["SPOT"]
			}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		account, err := client.GetAccount(ctx)

		assert.NoError(t, err)
		assert.NotNil(t, account)
		assert.True(t, requestSigned, "Request should be signed")
		assert.True(t, account.CanTrade)
		assert.Equal(t, "SPOT", account.AccountType)
	})

	t.Run("parses balance data correctly", func(t *testing.T) {
		mockResponse := `{
			"makerCommission": 15,
			"takerCommission": 15,
			"buyerCommission": 0,
			"sellerCommission": 0,
			"canTrade": true,
			"canWithdraw": true,
			"canDeposit": true,
			"updateTime": 123456789,
			"accountType": "SPOT",
			"balances": [
				{
					"asset": "BTC",
					"free": "1.23456789",
					"locked": "0.00000000"
				},
				{
					"asset": "USDT",
					"free": "1000.00000000",
					"locked": "500.00000000"
				}
			],
			"permissions": ["SPOT"]
		}`

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(mockResponse))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		account, err := client.GetAccount(ctx)

		assert.NoError(t, err)
		assert.NotNil(t, account)
		assert.Equal(t, int64(15), account.MakerCommission)
		assert.Equal(t, int64(15), account.TakerCommission)
		assert.Len(t, account.Balances, 2)

		// Check BTC balance
		btcBalance := account.Balances[0]
		assert.Equal(t, "BTC", btcBalance.Asset)
		expectedFree := decimal.NewFromFloat(1.23456789)
		assert.True(t, expectedFree.Equal(btcBalance.Free))
		assert.True(t, decimal.Zero.Equal(btcBalance.Locked))

		// Check USDT balance
		usdtBalance := account.Balances[1]
		assert.Equal(t, "USDT", usdtBalance.Asset)
		expectedUsdtFree := decimal.NewFromFloat(1000.0)
		expectedUsdtLocked := decimal.NewFromFloat(500.0)
		assert.True(t, expectedUsdtFree.Equal(usdtBalance.Free))
		assert.True(t, expectedUsdtLocked.Equal(usdtBalance.Locked))

		assert.Contains(t, account.Permissions, "SPOT")
	})

	t.Run("fails without signer", func(t *testing.T) {
		client := NewClient("https://api.binance.com", nil)
		ctx := context.Background()

		account, err := client.GetAccount(ctx)

		assert.Error(t, err)
		assert.Nil(t, account)
		assert.Contains(t, err.Error(), "signer required")
	})
}

func TestClient_PlaceOrder(t *testing.T) {
	t.Run("validates required fields", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("https://api.binance.com", signer)
		ctx := context.Background()

		// Missing symbol
		req := &OrderRequest{
			Side:     "BUY",
			Type:     "LIMIT",
			Quantity: decimal.NewFromFloat(1.0),
			Price:    decimal.NewFromFloat(50000),
		}
		resp, err := client.PlaceOrder(ctx, req)
		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "symbol is required")

		// Missing side
		req = &OrderRequest{
			Symbol:   "BTCUSDT",
			Type:     "LIMIT",
			Quantity: decimal.NewFromFloat(1.0),
			Price:    decimal.NewFromFloat(50000),
		}
		resp, err = client.PlaceOrder(ctx, req)
		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "side is required")

		// Missing type
		req = &OrderRequest{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Quantity: decimal.NewFromFloat(1.0),
			Price:    decimal.NewFromFloat(50000),
		}
		resp, err = client.PlaceOrder(ctx, req)
		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "type is required")

		// Missing quantity
		req = &OrderRequest{
			Symbol: "BTCUSDT",
			Side:   "BUY",
			Type:   "LIMIT",
			Price:  decimal.NewFromFloat(50000),
		}
		resp, err = client.PlaceOrder(ctx, req)
		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "quantity is required")

		// Missing price for LIMIT order
		req = &OrderRequest{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Quantity: decimal.NewFromFloat(1.0),
		}
		resp, err = client.PlaceOrder(ctx, req)
		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "price is required for LIMIT orders")
	})

	t.Run("signs request correctly", func(t *testing.T) {
		requestSigned := false
		var receivedParams url.Values

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/order", r.URL.Path)
			assert.Equal(t, "POST", r.Method)
			assert.Equal(t, "test-key", r.Header.Get("X-MBX-APIKEY"))

			// Parse body parameters
			body, _ := io.ReadAll(r.Body)
			params, _ := url.ParseQuery(string(body))
			receivedParams = params

			if params.Get("signature") != "" {
				requestSigned = true
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{
				"symbol": "BTCUSDT",
				"orderId": 123456,
				"clientOrderId": "test-client-id",
				"transactTime": 1499827319559,
				"price": "50000.00",
				"origQty": "1.00000000",
				"executedQty": "0.00000000",
				"cummulativeQuoteQty": "0.00000000",
				"status": "NEW",
				"timeInForce": "GTC",
				"type": "LIMIT",
				"side": "BUY",
				"fills": []
			}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		req := &OrderRequest{
			Symbol:           "BTCUSDT",
			Side:             "BUY",
			Type:             "LIMIT",
			Quantity:         decimal.NewFromFloat(1.0),
			Price:            decimal.NewFromFloat(50000),
			TimeInForce:      "GTC",
			NewClientOrderID: "test-client-id",
		}

		resp, err := client.PlaceOrder(ctx, req)

		assert.NoError(t, err)
		assert.NotNil(t, resp)
		assert.True(t, requestSigned, "Request should be signed")

		// Verify parameters were sent correctly
		assert.Equal(t, "BTCUSDT", receivedParams.Get("symbol"))
		assert.Equal(t, "BUY", receivedParams.Get("side"))
		assert.Equal(t, "LIMIT", receivedParams.Get("type"))
		assert.Equal(t, "1", receivedParams.Get("quantity"))
		assert.Equal(t, "50000", receivedParams.Get("price"))
		assert.Equal(t, "GTC", receivedParams.Get("timeInForce"))
		assert.Equal(t, "test-client-id", receivedParams.Get("newClientOrderId"))
		assert.NotEmpty(t, receivedParams.Get("timestamp"))
		assert.NotEmpty(t, receivedParams.Get("signature"))

		// Verify response parsing
		assert.Equal(t, "BTCUSDT", resp.Symbol)
		assert.Equal(t, int64(123456), resp.OrderID)
		assert.Equal(t, "test-client-id", resp.ClientOrderID)
		assert.Equal(t, "NEW", resp.Status)
	})

	t.Run("handles insufficient balance error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(400)
			w.Write([]byte(`{"code":-2010,"msg":"Account has insufficient balance for requested action."}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		req := &OrderRequest{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Quantity: decimal.NewFromFloat(1000.0),
			Price:    decimal.NewFromFloat(50000),
		}

		resp, err := client.PlaceOrder(ctx, req)

		assert.Error(t, err)
		assert.Nil(t, resp)

		var binanceErr *BinanceError
		assert.True(t, errors.As(err, &binanceErr))
		assert.Equal(t, -2010, binanceErr.Code)
		assert.Contains(t, binanceErr.Message, "insufficient balance")
		assert.True(t, binanceErr.IsOrderError())
		assert.False(t, binanceErr.IsRetryable())
	})

	t.Run("handles minimum notional error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(400)
			w.Write([]byte(`{"code":-1013,"msg":"Filter failure: MIN_NOTIONAL"}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		req := &OrderRequest{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "LIMIT",
			Quantity: decimal.NewFromFloat(0.0001),
			Price:    decimal.NewFromFloat(1),
		}

		resp, err := client.PlaceOrder(ctx, req)

		assert.Error(t, err)
		assert.Nil(t, resp)
		assert.Contains(t, err.Error(), "MIN_NOTIONAL")
	})

	t.Run("handles MARKET order without price", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{
				"symbol": "BTCUSDT",
				"orderId": 789,
				"status": "FILLED",
				"type": "MARKET",
				"side": "BUY",
				"fills": [{"price":"50000","qty":"0.001","commission":"0.05","commissionAsset":"BNB","tradeId":123}]
			}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		req := &OrderRequest{
			Symbol:   "BTCUSDT",
			Side:     "BUY",
			Type:     "MARKET",
			Quantity: decimal.NewFromFloat(0.001),
			// No price for market order
		}

		resp, err := client.PlaceOrder(ctx, req)

		assert.NoError(t, err)
		assert.NotNil(t, resp)
		assert.Equal(t, "MARKET", resp.Type)
		assert.Equal(t, "FILLED", resp.Status)
		assert.Len(t, resp.Fills, 1)
	})
}

func TestClient_CancelOrder(t *testing.T) {
	t.Run("validates order ID parameter", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("https://api.binance.com", signer)
		ctx := context.Background()

		err := client.CancelOrder(ctx, "BTCUSDT", 0)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "orderID is required")

		err = client.CancelOrder(ctx, "", 123)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "symbol is required")
	})

	t.Run("successfully cancels order", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/order", r.URL.Path)
			assert.Equal(t, "DELETE", r.Method)

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{
				"symbol": "BTCUSDT",
				"orderId": 123456,
				"status": "CANCELED"
			}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		err := client.CancelOrder(ctx, "BTCUSDT", 123456)
		assert.NoError(t, err)
	})

	t.Run("handles order not found error", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(400)
			w.Write([]byte(`{"code":-2011,"msg":"Unknown order sent."}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		err := client.CancelOrder(ctx, "BTCUSDT", 999999)

		assert.Error(t, err)
		var binanceErr *BinanceError
		assert.True(t, errors.As(err, &binanceErr))
		assert.Equal(t, -2011, binanceErr.Code)
		assert.Contains(t, binanceErr.Message, "Unknown order")
	})
}

func TestClient_GetOpenOrders(t *testing.T) {
	t.Run("returns empty slice when no orders", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v3/openOrders", r.URL.Path)
			assert.Equal(t, "BTCUSDT", r.URL.Query().Get("symbol"))

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`[]`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		orders, err := client.GetOpenOrders(ctx, "BTCUSDT")

		assert.NoError(t, err)
		assert.NotNil(t, orders)
		assert.Len(t, orders, 0)
	})

	t.Run("parses multiple orders correctly", func(t *testing.T) {
		mockResponse := `[
			{
				"symbol": "BTCUSDT",
				"orderId": 123,
				"clientOrderId": "order1",
				"price": "50000.00",
				"origQty": "1.00000000",
				"executedQty": "0.00000000",
				"status": "NEW",
				"timeInForce": "GTC",
				"type": "LIMIT",
				"side": "BUY",
				"time": 1499827319559,
				"updateTime": 1499827319559
			},
			{
				"symbol": "BTCUSDT",
				"orderId": 456,
				"clientOrderId": "order2",
				"price": "51000.00",
				"origQty": "0.50000000",
				"executedQty": "0.00000000",
				"status": "NEW",
				"timeInForce": "GTC",
				"type": "LIMIT",
				"side": "SELL",
				"time": 1499827319560,
				"updateTime": 1499827319560
			}
		]`

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(mockResponse))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		orders, err := client.GetOpenOrders(ctx, "BTCUSDT")

		assert.NoError(t, err)
		assert.Len(t, orders, 2)

		// Check first order
		order1 := orders[0]
		assert.Equal(t, "BTCUSDT", order1.Symbol)
		assert.Equal(t, int64(123), order1.OrderID)
		assert.Equal(t, "order1", order1.ClientOrderID)
		assert.Equal(t, "BUY", order1.Side)
		assert.Equal(t, "NEW", order1.Status)

		expectedPrice := decimal.NewFromFloat(50000)
		assert.True(t, expectedPrice.Equal(order1.Price))

		// Check second order
		order2 := orders[1]
		assert.Equal(t, int64(456), order2.OrderID)
		assert.Equal(t, "SELL", order2.Side)

		expectedPrice2 := decimal.NewFromFloat(51000)
		assert.True(t, expectedPrice2.Equal(order2.Price))
	})

	t.Run("validates symbol parameter", func(t *testing.T) {
		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient("https://api.binance.com", signer)
		ctx := context.Background()

		orders, err := client.GetOpenOrders(ctx, "")
		assert.Error(t, err)
		assert.Nil(t, orders)
		assert.Contains(t, err.Error(), "symbol is required")
	})
}

func TestClient_DoRequest(t *testing.T) {
	t.Run("retries with exponential backoff", func(t *testing.T) {
		callCount := 0
		callTimes := make([]time.Time, 0)

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			callTimes = append(callTimes, time.Now())

			if callCount < 3 {
				w.WriteHeader(503) // Service unavailable - retryable
				return
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(`{"success": true}`))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil, WithMaxRetries(3))
		ctx := context.Background()

		params := url.Values{}
		params.Set("test", "value")

		body, err := client.doRequest(ctx, "GET", "/test", params, false)

		assert.NoError(t, err)
		assert.Contains(t, string(body), "success")
		assert.Equal(t, 3, callCount)

		// Verify exponential backoff (should have delays between calls)
		if len(callTimes) >= 2 {
			delay1 := callTimes[1].Sub(callTimes[0])
			assert.Greater(t, delay1, 50*time.Millisecond) // Base delay ~100ms with jitter
		}
		if len(callTimes) >= 3 {
			delay2 := callTimes[2].Sub(callTimes[1])
			assert.Greater(t, delay2, 100*time.Millisecond) // ~200ms second delay with jitter
		}
	})

	t.Run("stops after max retries", func(t *testing.T) {
		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			w.WriteHeader(503)
		}))
		defer server.Close()

		client := NewClient(server.URL, nil, WithMaxRetries(2))
		ctx := context.Background()

		params := url.Values{}
		body, err := client.doRequest(ctx, "GET", "/test", params, false)

		assert.Error(t, err)
		assert.Nil(t, body)
		assert.Equal(t, 3, callCount) // Initial + 2 retries
		assert.Contains(t, err.Error(), "HTTP 503")
	})

	t.Run("respects rate limit", func(t *testing.T) {
		requestTimes := make([]time.Time, 0)
		var mu sync.Mutex

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			mu.Lock()
			requestTimes = append(requestTimes, time.Now())
			mu.Unlock()

			w.WriteHeader(200)
			w.Write([]byte(`{}`))
		}))
		defer server.Close()

		// Very low rate limit: 2 req/sec, burst 1
		client := NewClient(server.URL, nil, WithRateLimit(2, 1))
		ctx := context.Background()

		params := url.Values{}

		// Make multiple requests quickly
		for i := 0; i < 3; i++ {
			_, err := client.doRequest(ctx, "GET", "/test", params, false)
			assert.NoError(t, err)
		}

		// Should have been rate limited
		assert.Len(t, requestTimes, 3)

		// First request immediate, second should be delayed
		if len(requestTimes) >= 2 {
			delay := requestTimes[1].Sub(requestTimes[0])
			assert.Greater(t, delay, 400*time.Millisecond) // ~500ms at 2 req/sec
		}
	})

	t.Run("adds API key header", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "test-api-key", r.Header.Get("X-MBX-APIKEY"))
			w.WriteHeader(200)
			w.Write([]byte(`{}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-api-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		params := url.Values{}
		_, err := client.doRequest(ctx, "GET", "/test", params, false)

		assert.NoError(t, err)
	})

	t.Run("signs requests when required", func(t *testing.T) {
		var receivedParams url.Values

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// For GET requests, check query parameters
			if r.Method == "GET" {
				receivedParams = r.URL.Query()
			} else {
				// For POST/other methods, check body
				body, _ := io.ReadAll(r.Body)
				params, _ := url.ParseQuery(string(body))
				receivedParams = params
			}

			w.WriteHeader(200)
			w.Write([]byte(`{}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		params := url.Values{}
		params.Set("symbol", "BTCUSDT")

		_, err := client.doRequest(ctx, "GET", "/test", params, true)

		assert.NoError(t, err)
		assert.NotEmpty(t, receivedParams.Get("timestamp"))
		assert.NotEmpty(t, receivedParams.Get("signature"))
		assert.NotEmpty(t, receivedParams.Get("recvWindow"))
		assert.Equal(t, "BTCUSDT", receivedParams.Get("symbol"))
	})

	t.Run("does not sign when not required", func(t *testing.T) {
		var receivedParams url.Values

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			receivedParams = r.URL.Query()
			w.WriteHeader(200)
			w.Write([]byte(`{}`))
		}))
		defer server.Close()

		signer := auth.NewSigner("test-key", "test-secret")
		client := NewClient(server.URL, signer)
		ctx := context.Background()

		params := url.Values{}
		params.Set("symbol", "BTCUSDT")

		_, err := client.doRequest(ctx, "GET", "/test", params, false)

		assert.NoError(t, err)
		assert.Empty(t, receivedParams.Get("timestamp"))
		assert.Empty(t, receivedParams.Get("signature"))
		assert.Equal(t, "BTCUSDT", receivedParams.Get("symbol"))
	})
}

func TestClient_ConcurrentRequests(t *testing.T) {
	t.Run("thread-safe for concurrent use", func(t *testing.T) {
		requestCount := 0
		var mu sync.Mutex

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			mu.Lock()
			requestCount++
			count := requestCount
			mu.Unlock()

			// Simulate some processing time
			time.Sleep(10 * time.Millisecond)

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(200)
			w.Write([]byte(fmt.Sprintf(`{"requestId": %d}`, count)))
		}))
		defer server.Close()

		client := NewClient(server.URL, nil, WithRateLimit(1000, 100)) // High limits
		ctx := context.Background()

		const numGoroutines = 20
		var wg sync.WaitGroup
		errors := make(chan error, numGoroutines)

		// Launch concurrent requests
		for i := 0; i < numGoroutines; i++ {
			wg.Add(1)
			go func(id int) {
				defer wg.Done()

				_, err := client.GetExchangeInfo(ctx)
				if err != nil {
					errors <- err
				}
			}(i)
		}

		wg.Wait()
		close(errors)

		// Check for any errors
		for err := range errors {
			t.Errorf("Concurrent request failed: %v", err)
		}

		// All requests should have been processed
		mu.Lock()
		finalCount := requestCount
		mu.Unlock()
		assert.Equal(t, numGoroutines, finalCount)
	})
}

func TestClient_ParsesAPIErrors(t *testing.T) {
	t.Run("extracts Binance error codes and messages", func(t *testing.T) {
		testCases := []struct {
			responseCode int
			responseBody string
			expectedCode int
			expectedMsg  string
		}{
			{
				400,
				`{"code":-1102,"msg":"Mandatory parameter 'symbol' was not sent, was empty/null, or malformed."}`,
				-1102,
				"Mandatory parameter 'symbol' was not sent, was empty/null, or malformed.",
			},
			{
				401,
				`{"code":-2014,"msg":"API-key format invalid."}`,
				-2014,
				"API-key format invalid.",
			},
			{
				429,
				`{"code":-1003,"msg":"Too much request weight used; current limit is 1200 request weight per 1 MINUTE."}`,
				-1003,
				"Too much request weight used; current limit is 1200 request weight per 1 MINUTE.",
			},
		}

		for _, tc := range testCases {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(tc.responseCode)
				w.Write([]byte(tc.responseBody))
			}))

			client := NewClient(server.URL, nil)
			ctx := context.Background()

			_, err := client.GetExchangeInfo(ctx)

			assert.Error(t, err)

			var binanceErr *BinanceError
			assert.True(t, errors.As(err, &binanceErr))
			assert.Equal(t, tc.expectedCode, binanceErr.Code)
			assert.Equal(t, tc.expectedMsg, binanceErr.Message)
			assert.Equal(t, tc.responseCode, binanceErr.HTTPStatus)

			server.Close()
		}
	})
}