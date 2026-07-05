package orders

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
)

func init() {
	// The repoll bridge is timing behavior; tests only assert call counts.
	ambiguityRepollDelay = 0
}

type getScript struct {
	status      int    // 200 serves an order; 400 serves -2013 not found
	orderStatus string // order status served on 200 (default FILLED)
	executedQty string // executed quantity served on 200 (default "1")
}

type fakeExchange struct {
	orderPath    string // "/api/v3/order" or "/fapi/v1/order"
	postStatuses []int  // per-POST: 200 NEW | 400 duplicate | 500 ambiguous
	dupCode      int    // duplicate error code for 400 POSTs (default -2010)
	getScripts   []getScript
	postCount    atomic.Int64
	getCount     atomic.Int64
}

func (f *fakeExchange) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != f.orderPath {
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"code":-1121,"msg":"Invalid symbol."}`))
			return
		}
		clientOrderID := r.URL.Query().Get("newClientOrderId")
		if clientOrderID == "" {
			clientOrderID = r.URL.Query().Get("origClientOrderId")
		}

		switch r.Method {
		case http.MethodPost:
			call := int(f.postCount.Add(1)) - 1
			status := http.StatusOK
			if call < len(f.postStatuses) {
				status = f.postStatuses[call]
			}
			switch status {
			case http.StatusOK:
				_ = json.NewEncoder(w).Encode(map[string]any{
					"symbol": "BTCUSDT", "orderId": 100 + call, "clientOrderId": clientOrderID,
					"transactTime": 1, "price": "100", "origQty": "1", "executedQty": "0",
					"status": "NEW", "timeInForce": "GTC", "type": "LIMIT", "side": "BUY",
				})
			case http.StatusBadRequest:
				dupCode := f.dupCode
				if dupCode == 0 {
					dupCode = -2010
				}
				w.WriteHeader(http.StatusBadRequest)
				_, _ = fmt.Fprintf(w, `{"code":%d,"msg":"Duplicate order sent."}`, dupCode)
			default:
				w.WriteHeader(status)
				_, _ = w.Write([]byte(`upstream exploded`))
			}
		case http.MethodGet:
			call := int(f.getCount.Add(1)) - 1
			script := getScript{status: http.StatusBadRequest}
			if call < len(f.getScripts) {
				script = f.getScripts[call]
			}
			if script.status != http.StatusOK {
				w.WriteHeader(script.status)
				_, _ = w.Write([]byte(`{"code":-2013,"msg":"Order does not exist."}`))
				return
			}
			orderStatus := script.orderStatus
			if orderStatus == "" {
				orderStatus = "FILLED"
			}
			executedQty := script.executedQty
			if executedQty == "" {
				executedQty = "1"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 555, "clientOrderId": clientOrderID,
				"price": "100", "origQty": "1", "executedQty": executedQty,
				"status": orderStatus, "timeInForce": "GTC", "type": "LIMIT", "side": "BUY",
			})
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	}
}

func newSubmitFixture(
	t *testing.T,
	fake *fakeExchange,
) (*binance.Client, func(context.Context) (*binance.OrderResponse, error)) {
	t.Helper()
	if fake.orderPath == "" {
		fake.orderPath = "/api/v3/order"
	}
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	restClient := rest.NewClient(server.URL, signer)

	var client *binance.Client
	var err error
	if fake.orderPath == "/fapi/v1/order" {
		client, err = binance.NewFuturesClient(server.URL, signer, restClient, zerolog.Nop())
	} else {
		client, err = binance.NewSpotClient(server.URL, signer, restClient, zerolog.Nop())
	}
	require.NoError(t, err)

	order := binance.SpotOrderRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Type:             "LIMIT",
		Quantity:         decimal.NewFromInt(1),
		Price:            decimal.NewFromInt(100),
		TimeInForce:      "GTC",
		NewClientOrderID: "cid-1",
	}
	futuresOrder := binance.FuturesOrderRequest{
		Symbol:           order.Symbol,
		Side:             order.Side,
		Type:             order.Type,
		Quantity:         order.Quantity,
		Price:            order.Price,
		TimeInForce:      order.TimeInForce,
		NewClientOrderID: order.NewClientOrderID,
	}
	post := func(ctx context.Context) (*binance.OrderResponse, error) {
		if fake.orderPath == "/fapi/v1/order" {
			return client.PlaceFuturesOrder(ctx, futuresOrder)
		}
		return client.PlaceSpotOrder(ctx, order)
	}
	return client, post
}

func resolve(
	t *testing.T,
	client *binance.Client,
	allowRetry bool,
	post func(context.Context) (*binance.OrderResponse, error),
) (*binance.OrderResponse, error) {
	t.Helper()
	return submitResolvingAmbiguity(
		context.Background(), zerolog.Nop(), client, "BTCUSDT", "cid-1", allowRetry, post)
}

func TestSubmitResolvingAmbiguity_CleanSubmitPassesThrough(t *testing.T) {
	fake := &fakeExchange{postStatuses: []int{http.StatusOK}}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "NEW", resp.Status)
	assert.Equal(t, [2]int64{1, 0}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_AmbiguousResolvesViaQuery(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError},
		getScripts:   []getScript{{status: http.StatusOK}},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "FILLED", resp.Status)
	assert.Equal(t, int64(555), resp.OrderID)
	assert.Equal(t, [2]int64{1, 1}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_DuplicateAdoptsExistingOrder(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusBadRequest},
		getScripts:   []getScript{{status: http.StatusOK}},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "FILLED", resp.Status)
	assert.Equal(t, [2]int64{1, 1}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_VisibilityLagBridgedByRepoll(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError},
		getScripts:   []getScript{{status: http.StatusBadRequest}, {status: http.StatusOK}},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "FILLED", resp.Status)
	assert.Equal(t, [2]int64{1, 2}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_NotFoundAfterRepollsRetriesOnce(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError, http.StatusOK},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "NEW", resp.Status)
	// initial query + 2 repolls, all -2013, then exactly one retry POST
	assert.Equal(t, [2]int64{2, 3}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_RetryAmbiguousAgainFailsClosed(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError, http.StatusInternalServerError},
	}
	client, post := newSubmitFixture(t, fake)

	_, err := resolve(t, client, true, post)

	require.Error(t, err)
	assert.ErrorIs(t, err, rest.ErrAmbiguousSubmit)
	assert.Equal(t, int64(2), fake.postCount.Load())
}

func TestSubmitResolvingAmbiguity_RetryDuplicateAdoptsExchangeState(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError, http.StatusBadRequest},
		getScripts: []getScript{
			{status: http.StatusBadRequest},
			{status: http.StatusBadRequest},
			{status: http.StatusBadRequest},
			{status: http.StatusOK},
		},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "FILLED", resp.Status)
	assert.Equal(t, [2]int64{2, 4}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_MarketOrderNeverRetries(t *testing.T) {
	fake := &fakeExchange{postStatuses: []int{http.StatusInternalServerError}}
	client, post := newSubmitFixture(t, fake)

	_, err := resolve(t, client, false, post)

	require.Error(t, err)
	assert.ErrorIs(t, err, rest.ErrAmbiguousSubmit)
	assert.Equal(t, [2]int64{1, 3}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_DuplicateButInvisibleFailsClosed(t *testing.T) {
	fake := &fakeExchange{postStatuses: []int{http.StatusBadRequest}}
	client, post := newSubmitFixture(t, fake)

	_, err := resolve(t, client, true, post)

	require.Error(t, err)
	assert.True(t, rest.IsDuplicateClientOrderID(err),
		"original duplicate error must survive the wrap")
	assert.Equal(t, int64(1), fake.postCount.Load())
}

func TestSubmitResolvingAmbiguity_DeadAdoptedOrderFailsClosed(t *testing.T) {
	fake := &fakeExchange{
		postStatuses: []int{http.StatusInternalServerError},
		getScripts:   []getScript{{status: http.StatusOK, orderStatus: "CANCELED", executedQty: "0"}},
	}
	client, post := newSubmitFixture(t, fake)

	_, err := resolve(t, client, true, post)

	require.Error(t, err)
	assert.ErrorIs(t, err, rest.ErrAmbiguousSubmit)
	assert.Equal(t, [2]int64{1, 1}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_UnrelatedErrorFailsClosedWithoutQuery(t *testing.T) {
	fake := &fakeExchange{postStatuses: []int{http.StatusTeapot}}
	client, post := newSubmitFixture(t, fake)

	_, err := resolve(t, client, true, post)

	require.Error(t, err)
	assert.Equal(t, [2]int64{1, 0}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}

func TestSubmitResolvingAmbiguity_FuturesDuplicateAdoptsViaFapiPath(t *testing.T) {
	fake := &fakeExchange{
		orderPath:    "/fapi/v1/order",
		postStatuses: []int{http.StatusBadRequest},
		dupCode:      -4116,
		getScripts:   []getScript{{status: http.StatusOK}},
	}
	client, post := newSubmitFixture(t, fake)

	resp, err := resolve(t, client, true, post)

	require.NoError(t, err)
	assert.Equal(t, "FILLED", resp.Status)
	assert.Equal(t, [2]int64{1, 1}, [2]int64{fake.postCount.Load(), fake.getCount.Load()})
}
