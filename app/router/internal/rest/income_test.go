package rest

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"

	"router/internal/auth"
)

func TestClient_GetFuturesIncome(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assert.Equal(t, "/fapi/v1/income", r.URL.Path)
		assert.Equal(t, "GET", r.Method)
		assert.Equal(t, "test-key", r.Header.Get("X-MBX-APIKEY"))
		assert.Equal(t, "FUNDING_FEE", r.URL.Query().Get("incomeType"))
		assert.NotEmpty(t, r.URL.Query().Get("timestamp"))
		assert.NotEmpty(t, r.URL.Query().Get("signature"))
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`[{"incomeType":"FUNDING_FEE","income":"-0.01","asset":"USDT","time":1700000000000}]`))
	}))
	defer server.Close()

	signer := auth.NewSigner("test-key", "test-secret")
	client := NewClient(server.URL, signer)

	records, err := client.GetFuturesIncome(context.Background(), FuturesIncomeQuery{
		IncomeType: "FUNDING_FEE",
		StartTime:  1700000000000,
		EndTime:    1700003600000,
		Limit:      1000,
	})
	assert.NoError(t, err)
	assert.Len(t, records, 1)
	assert.Equal(t, "FUNDING_FEE", records[0].IncomeType)
	assert.Equal(t, "USDT", records[0].Asset)
}
