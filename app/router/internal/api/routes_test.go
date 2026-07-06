package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
)

func TestRegisterHealthRoutes(t *testing.T) {
	logger := zerolog.Nop()
	mockManager := new(MockOrderManager)

	handlers := NewHandlers(mockManager, logger, nil, nil)

	mux := http.NewServeMux()
	RegisterHealthRoutes(mux, handlers)

	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)

	assertHealthOk := func(path string) {
		t.Helper()

		resp, err := http.Get(server.URL + path)
		assert.NoError(t, err)
		t.Cleanup(func() { _ = resp.Body.Close() })

		assert.Equal(t, http.StatusOK, resp.StatusCode)

		var body map[string]string
		err = json.NewDecoder(resp.Body).Decode(&body)
		assert.NoError(t, err)
		assert.Equal(t, "order-router", body["service"])
	}

	assertHealthOk("/health")
	assertHealthOk("/healthz")

	resp, err := http.Get(server.URL + "/ready")
	assert.NoError(t, err)
	t.Cleanup(func() { _ = resp.Body.Close() })
	assert.Equal(t, http.StatusOK, resp.StatusCode)

	resp, err = http.Get(server.URL + "/readyz")
	assert.NoError(t, err)
	t.Cleanup(func() { _ = resp.Body.Close() })
	assert.Equal(t, http.StatusOK, resp.StatusCode)
}
