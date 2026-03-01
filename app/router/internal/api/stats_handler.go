package api

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/rs/zerolog"
)

type RouterStats struct {
	TotalTrades int     `json:"total_trades"`
	WinCount    int     `json:"win_count"`
	LossCount   int     `json:"loss_count"`
	WinRate     float64 `json:"win_rate"`

	TotalPnL      string  `json:"total_pnl,omitempty"`
	TotalFees     string  `json:"total_fees,omitempty"`
	TotalFunding  string  `json:"total_funding,omitempty"`
	TotalSlippage string  `json:"total_slippage,omitempty"`
	NetPnL        string  `json:"net_pnl,omitempty"`
	ProfitFactor  float64 `json:"profit_factor,omitempty"`
}

type StatsProvider interface {
	ComputeStats(ctx context.Context) (RouterStats, error)
}

func NewStatsHandler(provider StatsProvider, logger zerolog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
			return
		}
		if provider == nil {
			writeError(w, http.StatusServiceUnavailable, "Stats unavailable")
			return
		}

		stats, err := provider.ComputeStats(r.Context())
		if err != nil {
			logger.Error().Err(err).Msg("stats computation failed")
			writeError(w, http.StatusServiceUnavailable, "Stats unavailable")
			return
		}

		payload, err := json.Marshal(stats)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "Failed to encode response")
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(payload)
	}
}
