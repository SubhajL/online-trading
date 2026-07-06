package storage

import (
	"context"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newBracketTestRepo(t *testing.T) (*BracketRepo, context.Context) {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	t.Cleanup(cancel)

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	// Temp tables would vanish per-connection under a pool; use real tables
	// with a unique-suffix-free schema and clean up after ourselves.
	_, err = pool.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
	require.NoError(t, err)
	for _, file := range []string{
		"../../../../db/migrations/030_brackets.sql",
		"../../../../db/migrations/031_bracket_leg_placing.sql",
	} {
		migration, err := os.ReadFile(file)
		require.NoError(t, err)
		_, err = pool.Exec(ctx, string(migration))
		require.NoError(t, err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = pool.Exec(cleanupCtx, `DELETE FROM bracket_legs`)
		_, _ = pool.Exec(cleanupCtx, `DELETE FROM brackets`)
	})

	return NewBracketRepo(pool), ctx
}

func sampleBracket(entryID string) BracketRecord {
	return BracketRecord{
		Venue:              "SPOT",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		Quantity:           decimal.RequireFromString("0.02"),
		EntryPrice:         decimal.RequireFromString("50000"),
		StopLossPrice:      decimal.RequireFromString("49000"),
		EntryClientOrderID: entryID,
		LegsOnFill:         false,
		Legs: []BracketLegRecord{
			{Role: "ENTRY", ClientOrderID: entryID, Price: decimal.RequireFromString("50000"), Quantity: decimal.RequireFromString("0.02")},
			{Role: "TP", TPIndex: 1, ClientOrderID: entryID + "-tp1", Price: decimal.RequireFromString("51000"), Quantity: decimal.RequireFromString("0.02")},
			{Role: "SL", ClientOrderID: entryID + "-sl", StopPrice: decimal.RequireFromString("49000"), Quantity: decimal.RequireFromString("0.02")},
		},
	}
}

func TestBracketRepo_ReserveInsertsOnceAndRoundTripsLegs(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]

	first, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	second, insertedAgain, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	assert.False(t, insertedAgain)
	assert.Equal(t, first.BracketID, second.BracketID)
	require.Len(t, second.Legs, 3)
	assert.Equal(t, StatusRolesFromLegs(second.Legs), map[string]string{
		"ENTRY": LegStatusPlanned, "TP": LegStatusPlanned, "SL": LegStatusPlanned,
	})
}

// StatusRolesFromLegs maps role -> status for compact whole-structure asserts.
func StatusRolesFromLegs(legs []BracketLegRecord) map[string]string {
	out := make(map[string]string, len(legs))
	for _, leg := range legs {
		out[leg.Role] = leg.Status
	}
	return out
}

func TestBracketRepo_ConcurrentReservesElectSingleWinner(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]

	const racers = 8
	var wins atomic.Int64
	var wg sync.WaitGroup
	for i := 0; i < racers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
			assert.NoError(t, err)
			if inserted {
				wins.Add(1)
			}
		}()
	}
	wg.Wait()

	assert.Equal(t, int64(1), wins.Load())
}

func TestBracketRepo_StatusTransitionsAndOpenBracketScan(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]

	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateBracketStatus(ctx, rec.BracketID, BracketStatusEntryPlaced))
	require.NoError(t, repo.UpdateLegStatus(ctx, rec.BracketID, entryID, LegStatusPlaced, 12345))

	open, err := repo.LoadOpenBrackets(ctx, time.Hour)
	require.NoError(t, err)
	var found *BracketRecord
	for i := range open {
		if open[i].EntryClientOrderID == entryID {
			found = &open[i]
		}
	}
	require.NotNil(t, found)
	assert.Equal(t, BracketStatusEntryPlaced, found.Status)
	for _, leg := range found.Legs {
		if leg.Role == "ENTRY" {
			assert.Equal(t, [2]any{LegStatusPlaced, int64(12345)}, [2]any{leg.Status, leg.ExchangeOrderID})
		}
	}

	require.NoError(t, repo.UpdateBracketStatus(ctx, rec.BracketID, BracketStatusClosed))
	open, err = repo.LoadOpenBrackets(ctx, time.Hour)
	require.NoError(t, err)
	for i := range open {
		assert.NotEqual(t, entryID, open[i].EntryClientOrderID, "closed bracket must leave the open scan")
	}
}

func TestBracketRepo_TryMarkLegPlacingClaimsExactlyOnce(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]
	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	first, err := repo.TryMarkLegPlacing(ctx, rec.BracketID, entryID+"-sl")
	require.NoError(t, err)
	second, err := repo.TryMarkLegPlacing(ctx, rec.BracketID, entryID+"-sl")
	require.NoError(t, err)
	assert.Equal(t, [2]bool{true, false}, [2]bool{first, second})

	// FAILED legs are re-claimable so transient errors cannot strand a position
	require.NoError(t, repo.UpdateLegStatus(ctx, rec.BracketID, entryID+"-sl", LegStatusFailed, 0))
	reclaimed, err := repo.TryMarkLegPlacing(ctx, rec.BracketID, entryID+"-sl")
	require.NoError(t, err)
	assert.True(t, reclaimed)
}

func TestBracketRepo_GetByLegClientOrderIDRoundTrips(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]
	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	found, err := repo.GetByLegClientOrderID(ctx, "SPOT", entryID+"-tp1")
	require.NoError(t, err)
	require.NotNil(t, found)
	assert.Equal(t, rec.BracketID, found.BracketID)
	assert.Len(t, found.Legs, 3)

	missing, err := repo.GetByLegClientOrderID(ctx, "SPOT", "no-such-leg")
	require.NoError(t, err)
	assert.Nil(t, missing)

	wrongVenue, err := repo.GetByLegClientOrderID(ctx, "USD_M", entryID+"-tp1")
	require.NoError(t, err)
	assert.Nil(t, wrongVenue)
}

func TestBracketRepo_UpdateBracketStatusIfGuardsTransition(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]
	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	applied, err := repo.UpdateBracketStatusIf(ctx, rec.BracketID, BracketStatusReserved, BracketStatusEntryPlaced)
	require.NoError(t, err)
	assert.True(t, applied)

	notApplied, err := repo.UpdateBracketStatusIf(ctx, rec.BracketID, BracketStatusReserved, BracketStatusEntryPlaced)
	require.NoError(t, err)
	assert.False(t, notApplied, "guarded transition must not fire from the wrong state")
}

func TestBracketRepo_UpdateLegStatusIfGuardsLegTransition(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]
	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateLegStatus(ctx, rec.BracketID, entryID+"-tp1", LegStatusPlacing, 0))

	applied, err := repo.UpdateLegStatusIf(ctx, rec.BracketID, entryID+"-tp1", LegStatusPlacing, LegStatusFailed, 0)
	require.NoError(t, err)
	assert.True(t, applied, "a PLACING leg must demote to FAILED")

	// A concurrent armer already moved it PLACED: the guard must not fire
	require.NoError(t, repo.UpdateLegStatus(ctx, rec.BracketID, entryID+"-tp1", LegStatusPlaced, 999))
	applied, err = repo.UpdateLegStatusIf(ctx, rec.BracketID, entryID+"-tp1", LegStatusPlacing, LegStatusFailed, 0)
	require.NoError(t, err)
	assert.False(t, applied, "the demote must lose to a fresher PLACED write")

	found, err := repo.GetByLegClientOrderID(ctx, "SPOT", entryID+"-tp1")
	require.NoError(t, err)
	for _, leg := range found.Legs {
		if leg.ClientOrderID == entryID+"-tp1" {
			assert.Equal(t, [2]any{LegStatusPlaced, int64(999)}, [2]any{leg.Status, leg.ExchangeOrderID})
		}
	}
}

func TestBracketRepo_InsertLegAddsDerivedStopSlice(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "it-" + uuid.NewString()[:8]
	rec, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	derived := BracketLegRecord{
		BracketID:       rec.BracketID,
		Role:            "SL",
		ClientOrderID:   entryID + "-sl-1",
		StopPrice:       decimal.RequireFromString("49000"),
		Quantity:        decimal.RequireFromString("0.01"),
		Status:          LegStatusPlaced,
		ExchangeOrderID: 9009,
	}
	require.NoError(t, repo.InsertLeg(ctx, derived))
	// Conflicting re-insert must be a no-op, not an error
	require.NoError(t, repo.InsertLeg(ctx, derived))

	found, err := repo.GetByLegClientOrderID(ctx, "SPOT", entryID+"-sl-1")
	require.NoError(t, err)
	require.NotNil(t, found)
	assert.Len(t, found.Legs, 4)
}
