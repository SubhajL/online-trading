package orders

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestOrderUpdate() *OrderUpdate {
	return &OrderUpdate{
		EventType:     "order_update.v1",
		Symbol:        "BTCUSDT",
		OrderID:       12345,
		ClientOrderID: "test-client-order-123",
		Status:        "NEW",
		Side:          "BUY",
		OrderType:     "LIMIT",
		Price:         decimal.RequireFromString("50000"),
		Quantity:      decimal.RequireFromString("0.001"),
		ExecutedQty:   decimal.Zero,
		UpdateTime:    time.Now(),
	}
}

func TestHTTPEventEmitter_ReturnsErrorOnHTTPFailure(t *testing.T) {
	tests := []struct {
		name           string
		statusCode     int
		wantErrContain string
	}{
		{
			name:           "internal server error",
			statusCode:     http.StatusInternalServerError,
			wantErrContain: "unexpected status code: 500",
		},
		{
			name:           "bad gateway",
			statusCode:     http.StatusBadGateway,
			wantErrContain: "unexpected status code: 502",
		},
		{
			name:           "service unavailable",
			statusCode:     http.StatusServiceUnavailable,
			wantErrContain: "unexpected status code: 503",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
			}))
			defer srv.Close()

			emitter := NewHTTPEventEmitter(srv.URL)
			update := newTestOrderUpdate()

			err := emitter.EmitOrderUpdate(context.Background(), update)

			require.Error(t, err)
			assert.Contains(t, err.Error(), tt.wantErrContain)
		})
	}
}

func TestHTTPEventEmitter_ReturnsErrorOnNetworkFailure(t *testing.T) {
	// Use a URL that will fail to connect
	emitter := NewHTTPEventEmitter("http://localhost:59999")
	update := newTestOrderUpdate()

	err := emitter.EmitOrderUpdate(context.Background(), update)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to send order update")
}

func TestHTTPEventEmitter_SkipsEmissionWhenURLEmpty(t *testing.T) {
	emitter := NewHTTPEventEmitter("")
	update := newTestOrderUpdate()

	err := emitter.EmitOrderUpdate(context.Background(), update)

	require.NoError(t, err, "empty URL should skip emission without error")
}

func TestHTTPEventEmitter_SucceedsOnOKStatus(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
	}{
		{
			name:       "OK status",
			statusCode: http.StatusOK,
		},
		{
			name:       "Accepted status",
			statusCode: http.StatusAccepted,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				// Verify request
				assert.Equal(t, "POST", r.Method)
				assert.Equal(t, "application/json", r.Header.Get("Content-Type"))
				w.WriteHeader(tt.statusCode)
			}))
			defer srv.Close()

			emitter := NewHTTPEventEmitter(srv.URL)
			update := newTestOrderUpdate()

			err := emitter.EmitOrderUpdate(context.Background(), update)

			require.NoError(t, err)
		})
	}
}

func TestHTTPEventEmitter_AddsBearerTokenWhenConfigured(t *testing.T) {
	t.Setenv("ENGINE_INTERNAL_API_TOKEN", "engine-secret")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "Bearer engine-secret", r.Header.Get("Authorization"))
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	emitter := NewHTTPEventEmitter(srv.URL)
	update := newTestOrderUpdate()

	err := emitter.EmitOrderUpdate(context.Background(), update)

	require.NoError(t, err)
}

func TestHTTPEventEmitter_SendsCorrectPayload(t *testing.T) {
	var receivedBody []byte
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		receivedBody = make([]byte, r.ContentLength)
		_, _ = r.Body.Read(receivedBody)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	emitter := NewHTTPEventEmitter(srv.URL)
	update := newTestOrderUpdate()

	err := emitter.EmitOrderUpdate(context.Background(), update)

	require.NoError(t, err)
	assert.Contains(t, string(receivedBody), "BTCUSDT")
	assert.Contains(t, string(receivedBody), "test-client-order-123")
}

func TestHTTPEventEmitter_RespectsContextCancellation(t *testing.T) {
	// Server that delays response longer than context timeout
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(500 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
	}))
	defer srv.Close()

	emitter := NewHTTPEventEmitter(srv.URL)
	update := newTestOrderUpdate()

	// Context times out before server responds
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	err := emitter.EmitOrderUpdate(ctx, update)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "failed to send order update")
}
