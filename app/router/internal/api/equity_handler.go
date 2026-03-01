package api

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
)

type EquityVenue string

const (
	EquityVenueSpot EquityVenue = "SPOT"
	EquityVenueUSDM EquityVenue = "USD_M"
)

type EquitySnapshot struct {
	Venue     EquityVenue
	EquityUSD decimal.Decimal
	Timestamp time.Time
	Source    string
}

type EquityProvider interface {
	GetEquity(ctx context.Context, venue EquityVenue) (EquitySnapshot, error)
}

// EquityResponse is the JSON payload returned by GET /internal/equity.
//
// EquityUSD uses shopspring/decimal JSON marshaling to preserve precision.
type EquityResponse struct {
	Venue     string          `json:"venue"`
	EquityUSD decimal.Decimal `json:"equity_usd"`
	Timestamp time.Time       `json:"timestamp"`
	Source    string          `json:"source"`
}

func parseEquityVenue(raw string) (EquityVenue, bool) {
	if raw == "" {
		return "", true
	}
	normalized := strings.TrimSpace(strings.ToUpper(raw))
	switch normalized {
	case "SPOT":
		return EquityVenueSpot, true
	case "USD_M", "USDM", "FUTURES":
		return EquityVenueUSDM, true
	default:
		return "", false
	}
}

func NewEquityHandler(provider EquityProvider, logger zerolog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
			return
		}

		venueRaw := r.URL.Query().Get("venue")
		venue, ok := parseEquityVenue(venueRaw)
		if !ok {
			writeError(w, http.StatusBadRequest, "Invalid venue")
			return
		}

		snapshot, err := provider.GetEquity(r.Context(), venue)
		if err != nil {
			logger.Error().Err(err).Msg("Failed to fetch equity")
			writeError(w, http.StatusServiceUnavailable, "Equity unavailable")
			return
		}

		writeJSON(w, http.StatusOK, EquityResponse{
			Venue:     string(snapshot.Venue),
			EquityUSD: snapshot.EquityUSD,
			Timestamp: snapshot.Timestamp.UTC(),
			Source:    snapshot.Source,
		})
	}
}
