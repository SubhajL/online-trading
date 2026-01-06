package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"
)

type stubStatsProvider struct {
	stats RouterStats
	err   error
}

func (s stubStatsProvider) ComputeStats(_ context.Context) (RouterStats, error) {
	return s.stats, s.err
}

func TestStatsHandler_ReturnsJSON(t *testing.T) {
	handler := NewStatsHandler(
		stubStatsProvider{
			stats: RouterStats{
				TotalTrades: 10,
				WinCount:    6,
				LossCount:   4,
				WinRate:     0.6,
				NetPnL:      "12.34",
			},
		},
		zerolog.Nop(),
	)

	req := httptest.NewRequest(http.MethodGet, "/stats", nil)
	w := httptest.NewRecorder()
	handler(w, req)

	require.Equal(t, http.StatusOK, w.Code)
	var got map[string]any
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &got))
	require.Equal(t, float64(10), got["total_trades"])
	require.Equal(t, "12.34", got["net_pnl"])
}
