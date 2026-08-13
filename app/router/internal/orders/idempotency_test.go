package orders

import (
	"errors"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/storage"
)

func idempotentBracketRequest() *PlaceBracketRequest {
	return &PlaceBracketRequest{
		IdempotencyKey:   "decision-123",
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.00100000"),
		EntryPrice:       decimal.RequireFromString("50000.00"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000.00")},
		StopLossPrice:    decimal.RequireFromString("49000.00"),
		OrderType:        "LIMIT",
		ClientOrderIDs: &ClientOrderIDs{
			Main:        "decision-entry",
			TakeProfits: []string{"decision-tp1"},
			StopLoss:    "decision-sl",
		},
	}
}

func TestCanonicalBracketRequestHashNormalizesDecimalScale(t *testing.T) {
	first := idempotentBracketRequest()
	second := idempotentBracketRequest()
	second.Quantity = decimal.RequireFromString("0.001")
	second.EntryPrice = decimal.RequireFromString("50000")

	firstHash, err := canonicalBracketRequestHash(first)
	require.NoError(t, err)
	secondHash, err := canonicalBracketRequestHash(second)
	require.NoError(t, err)

	assert.Equal(t, firstHash, secondHash)
}

func TestIdempotencyKeyPayloadConflict(t *testing.T) {
	request := idempotentBracketRequest()
	hash, err := canonicalBracketRequestHash(request)
	require.NoError(t, err)
	record := bracketRecordFromRequest(request, false)
	record.RequestHash = hash

	request.Quantity = decimal.RequireFromString("0.002")
	err = validateReplayMatchesReservation(&record, request)

	var conflict *IdempotencyConflictError
	require.ErrorAs(t, err, &conflict)
	assert.True(t, errors.Is(err, ErrIdempotencyConflict))
}

func TestBracketRecordCarriesIdempotencyIdentity(t *testing.T) {
	request := idempotentBracketRequest()
	record := bracketRecordFromRequest(request, false)
	hash, err := canonicalBracketRequestHash(request)
	require.NoError(t, err)

	assert.Equal(t, request.IdempotencyKey, record.IdempotencyKey)
	assert.Equal(t, hash, record.RequestHash)
	assert.Equal(t, storage.BracketStatusReserved, record.Status)
}
