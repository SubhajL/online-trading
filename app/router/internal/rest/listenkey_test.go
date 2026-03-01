package rest

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"

	"router/internal/auth"
)

func TestListenKeyLifecycle_Futures(t *testing.T) {
	var calls []string

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls = append(calls, r.Method+" "+r.URL.Path)

		assert.Equal(t, "test-key", r.Header.Get("X-MBX-APIKEY"))

		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/fapi/v1/listenKey":
			_ = json.NewEncoder(w).Encode(map[string]string{"listenKey": "lk-1"})
		case r.Method == http.MethodPut && r.URL.Path == "/fapi/v1/listenKey":
			assert.Equal(t, "lk-1", r.URL.Query().Get("listenKey"))
			_ = json.NewEncoder(w).Encode(map[string]any{})
		case r.Method == http.MethodDelete && r.URL.Path == "/fapi/v1/listenKey":
			assert.Equal(t, "lk-1", r.URL.Query().Get("listenKey"))
			_ = json.NewEncoder(w).Encode(map[string]any{})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}))
	t.Cleanup(server.Close)

	signer := auth.NewSigner("test-key", "test-secret")
	client := NewClient(server.URL, signer)

	ctx := context.Background()

	key, err := client.CreateFuturesListenKey(ctx)
	assert.NoError(t, err)
	assert.Equal(t, "lk-1", key)

	assert.NoError(t, client.KeepAliveFuturesListenKey(ctx, key))
	assert.NoError(t, client.DeleteFuturesListenKey(ctx, key))

	assert.Equal(t, []string{
		"POST /fapi/v1/listenKey",
		"PUT /fapi/v1/listenKey",
		"DELETE /fapi/v1/listenKey",
	}, calls)
}
