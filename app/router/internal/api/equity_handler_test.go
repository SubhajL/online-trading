package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
)

type stubEquityProvider struct {
	snapshot EquitySnapshot
	err      error
}

func (s stubEquityProvider) GetEquity(ctx context.Context, venue EquityVenue) (EquitySnapshot, error) {
	_ = ctx
	if venue != "" {
		return EquitySnapshot{
			Venue:     venue,
			EquityUSD: s.snapshot.EquityUSD,
			Timestamp: s.snapshot.Timestamp,
			Source:    s.snapshot.Source,
		}, s.err
	}
	return s.snapshot, s.err
}

func TestEquityHandler_ReturnsJSON(t *testing.T) {
	now := time.Date(2026, 2, 6, 12, 0, 0, 0, time.UTC)
	provider := stubEquityProvider{
		snapshot: EquitySnapshot{
			Venue:     EquityVenueUSDM,
			EquityUSD: decimal.RequireFromString("1234.56"),
			Timestamp: now,
			Source:    "test",
		},
	}

	handler := NewEquityHandler(provider, zerolog.Nop())
	req := httptest.NewRequest(http.MethodGet, "/internal/equity?venue=USD_M", nil)
	w := httptest.NewRecorder()

	handler(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", w.Code, w.Body.String())
	}

	var payload EquityResponse
	if err := json.Unmarshal(w.Body.Bytes(), &payload); err != nil {
		t.Fatalf("unmarshal response: %v", err)
	}

	if payload.Venue != string(EquityVenueUSDM) {
		t.Fatalf("expected venue %s, got %s", EquityVenueUSDM, payload.Venue)
	}
	if payload.EquityUSD.String() != "1234.56" {
		t.Fatalf("expected equity 1234.56, got %s", payload.EquityUSD.String())
	}
	if payload.Timestamp.IsZero() {
		t.Fatalf("expected non-zero timestamp")
	}
}

func TestEquityHandler_RejectsInvalidVenue(t *testing.T) {
	provider := stubEquityProvider{
		snapshot: EquitySnapshot{
			Venue:     EquityVenueSpot,
			EquityUSD: decimal.RequireFromString("1"),
			Timestamp: time.Now().UTC(),
			Source:    "test",
		},
	}

	handler := NewEquityHandler(provider, zerolog.Nop())
	req := httptest.NewRequest(http.MethodGet, "/internal/equity?venue=NOPE", nil)
	w := httptest.NewRecorder()

	handler(w, req)

	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d: %s", w.Code, w.Body.String())
	}
}
