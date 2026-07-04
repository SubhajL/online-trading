package rest

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/auth"
)

func TestSignedRetrySignsFreshParamsPerAttempt(t *testing.T) {
	// Reusing the signed param set across attempts computes attempt N's HMAC
	// over a query still containing attempt N-1's signature (-1022 on every
	// retry). Each attempt must carry exactly one signature.
	var queries []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		queries = append(queries, r.URL.RawQuery)
		if len(queries) == 1 {
			w.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write([]byte(`{"balances":[]}`))
	}))
	defer server.Close()

	client := NewClient(server.URL, auth.NewSigner("key", "secret"), WithMaxRetries(2))
	_, err := client.doRequest(context.Background(), "GET", "/api/v3/account", nil, true)
	require.NoError(t, err)

	require.Len(t, queries, 2)
	for i, query := range queries {
		values, parseErr := url.ParseQuery(query)
		require.NoError(t, parseErr)
		assert.Len(t, values["signature"], 1, "attempt %d must carry exactly one signature", i+1)
		assert.Len(t, values["timestamp"], 1, "attempt %d must carry exactly one timestamp", i+1)
	}
}

func TestPostNetworkFailureIsAmbiguousNotRetried(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		// Kill the connection mid-response: the client sees a network error
		// but the order may already have been accepted.
		hj, ok := w.(http.Hijacker)
		require.True(t, ok)
		conn, _, _ := hj.Hijack()
		_ = conn.Close()
	}))
	defer server.Close()

	client := NewClient(server.URL, auth.NewSigner("key", "secret"), WithMaxRetries(3))
	_, err := client.doRequest(context.Background(), "POST", "/api/v3/order", nil, true)

	require.ErrorIs(t, err, ErrAmbiguousSubmit)
	assert.Equal(t, 1, attempts)
}

func TestGetOrderByClientIDPaths(t *testing.T) {
	var paths []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		paths = append(paths, r.URL.Path)
		assert.Equal(t, "ord-1", r.URL.Query().Get("origClientOrderId"))
		_ = json.NewEncoder(w).Encode(OrderResponse{Symbol: "BTCUSDT", OrderID: 42, Status: "FILLED"})
	}))
	defer server.Close()

	client := NewClient(server.URL, auth.NewSigner("key", "secret"))

	spot, err := client.GetOrderByClientID(context.Background(), "BTCUSDT", "ord-1", false)
	require.NoError(t, err)
	assert.Equal(t, int64(42), spot.OrderID)

	futures, err := client.GetOrderByClientID(context.Background(), "BTCUSDT", "ord-1", true)
	require.NoError(t, err)
	assert.Equal(t, "FILLED", futures.Status)

	assert.Equal(t, []string{"/api/v3/order", "/fapi/v1/order"}, paths)
}

func TestIsDuplicateClientOrderID(t *testing.T) {
	assert.True(t, IsDuplicateClientOrderID(&BinanceError{Code: -2010, Message: "Duplicate order sent."}))
	assert.True(t, IsDuplicateClientOrderID(&BinanceError{Code: -4116, Message: "clientOrderId is duplicated"}))
	assert.False(t, IsDuplicateClientOrderID(&BinanceError{Code: -2010, Message: "Account has insufficient balance"}))
	assert.False(t, IsDuplicateClientOrderID(&BinanceError{Code: -1013, Message: "Filter failure"}))
	assert.False(t, IsDuplicateClientOrderID(nil))
}
