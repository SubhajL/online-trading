package storage

import (
	"context"
	"encoding/json"
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
		"../../../../db/migrations/034_execution_safety.sql",
		"../../../../db/migrations/035_order_update_delivery.sql",
		"../../../../db/migrations/037_order_update_stop_price.sql",
		"../../../../db/migrations/040_order_update_average_fill_price.sql",
		"../../../../db/migrations/042_partial_entry_execution.sql",
		"../../../../db/migrations/043_bracket_leg_execution_observed_at.sql",
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
		_, _ = pool.Exec(cleanupCtx, `DELETE FROM router_order_update_outbox`)
		_, _ = pool.Exec(cleanupCtx, `DELETE FROM router_order_update_sequences`)
	})

	return NewBracketRepo(pool), ctx
}

func loadAllOpenBrackets(
	t *testing.T,
	repo *BracketRepo,
	ctx context.Context,
	pageSize int,
) []BracketRecord {
	t.Helper()
	var all []BracketRecord
	var cursor *OpenBracketCursor
	for {
		page, next, err := repo.LoadOpenBracketPage(ctx, cursor, pageSize)
		require.NoError(t, err)
		require.LessOrEqual(t, len(page), pageSize)
		all = append(all, page...)
		if next == nil {
			return all
		}
		cursor = next
	}
}

func TestStateAndOutboxCommitAtomically(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "atomic-" + uuid.NewString()[:8]
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateLegStatus(ctx, record.BracketID, entryID, LegStatusPlaced, 99001))

	var legStatus string
	var outboxStatus string
	var aggregateID string
	err = repo.pool.QueryRow(ctx, `
		SELECT leg.status, outbox.status, outbox.aggregate_id
		FROM bracket_legs leg
		JOIN router_order_update_outbox outbox
		  ON outbox.aggregate_id = 'SPOT:' || leg.client_order_id
		WHERE leg.bracket_id = $1 AND leg.client_order_id = $2
	`, record.BracketID, entryID).Scan(&legStatus, &outboxStatus, &aggregateID)
	require.NoError(t, err)
	assert.Equal(t, LegStatusPlaced, legStatus)
	assert.Equal(t, "PENDING", outboxStatus)
	assert.Equal(t, "SPOT:"+entryID, aggregateID)
}

func TestFilledLegOutboxCarriesAuthoritativeAverageFillPrice(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "average-fill-" + uuid.NewString()[:8]
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateLegExecution(
		ctx,
		record.BracketID,
		entryID,
		LegStatusFilled,
		99001,
		decimal.RequireFromString("50020"),
	))

	var payloadBytes []byte
	err = repo.pool.QueryRow(ctx, `
		SELECT payload FROM router_order_update_outbox
		WHERE aggregate_id = 'SPOT:' || $1
		ORDER BY sequence DESC LIMIT 1
	`, entryID).Scan(&payloadBytes)
	require.NoError(t, err)

	var payload map[string]any
	require.NoError(t, json.Unmarshal(payloadBytes, &payload))
	assert.Equal(t, "FILLED", payload["status"])
	assert.Equal(t, float64(50000), payload["price"])
	assert.Equal(t, float64(50020), payload["average_fill_price"])
	assert.Equal(t, float64(0.02), payload["executed_qty"])
}

func TestFilledLegOutboxPrefersNewAverageOverCanonicalAndPrior(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "average-precedence-" + uuid.NewString()[:8]
	aggregateID := "SPOT:" + entryID
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)
	t.Cleanup(func() {
		_, _ = repo.pool.Exec(context.Background(), `DELETE FROM orders WHERE venue='SPOT' AND client_order_id=$1`, entryID)
	})

	_, err = repo.pool.Exec(ctx, `
		INSERT INTO orders (
			client_order_id, venue, symbol, side, type, quantity, price,
			status, filled_quantity, average_fill_price, exchange_order_id, created_at
		) VALUES ($1,'SPOT','BTCUSDT','BUY','LIMIT',0.02,50000,
			'PARTIALLY_FILLED',0.01,50010,'99001',NOW())
	`, entryID)
	require.NoError(t, err)
	_, err = repo.pool.Exec(ctx, `
		INSERT INTO router_order_update_sequences (aggregate_id, next_sequence)
		VALUES ($1, 2)
		ON CONFLICT (aggregate_id) DO UPDATE SET next_sequence=2
	`, aggregateID)
	require.NoError(t, err)
	_, err = repo.pool.Exec(ctx, `
		INSERT INTO router_order_update_outbox (
			event_id, aggregate_id, sequence, event_version, event_type,
			payload, payload_hash, event_key_hash, status, next_attempt_at
		) VALUES (
			gen_random_uuid(), $1, 1, 1, 'order_update.v1',
			jsonb_build_object('average_fill_price', 50000, 'update_time', CURRENT_TIMESTAMP),
			repeat('1',64), repeat('2',64), 'DELIVERED', CURRENT_TIMESTAMP
		)
	`, aggregateID)
	require.NoError(t, err)

	require.NoError(t, repo.UpdateLegExecution(
		ctx, record.BracketID, entryID, LegStatusFilled, 99001,
		decimal.RequireFromString("50020"),
	))

	var averageFillPrice string
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT payload->>'average_fill_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1 ORDER BY sequence DESC LIMIT 1
	`, aggregateID).Scan(&averageFillPrice))
	assert.Equal(t, "50020.00000000", averageFillPrice)
}

func TestStopLossOutboxUsesCanonicalStopPrice(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	migration, err := os.ReadFile("../../../../db/migrations/037_order_update_stop_price.sql")
	require.NoError(t, err)
	_, err = repo.pool.Exec(ctx, string(migration))
	require.NoError(t, err)
	_, err = repo.pool.Exec(ctx, string(migration))
	require.NoError(t, err)
	latestMigration, err := os.ReadFile("../../../../db/migrations/040_order_update_average_fill_price.sql")
	require.NoError(t, err)
	_, err = repo.pool.Exec(ctx, string(latestMigration))
	require.NoError(t, err)

	entryID := "stop-price-" + uuid.NewString()[:8]
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	stopClientOrderID := entryID + "-sl"
	require.NoError(t, repo.UpdateLegExecution(
		ctx,
		record.BracketID,
		stopClientOrderID,
		LegStatusFilled,
		99002,
		decimal.RequireFromString("49005"),
	))

	var payloadBytes []byte
	err = repo.pool.QueryRow(ctx, `
		SELECT payload
		FROM router_order_update_outbox
		WHERE aggregate_id = 'SPOT:' || $1
		ORDER BY sequence DESC
		LIMIT 1
	`, stopClientOrderID).Scan(&payloadBytes)
	require.NoError(t, err)

	var payload map[string]any
	require.NoError(t, json.Unmarshal(payloadBytes, &payload))
	assert.Equal(t, "STOP_LOSS_LIMIT", payload["order_type"])
	assert.Equal(t, float64(48950), payload["price"])
	assert.Equal(t, float64(49000), payload["stop_price"])
	assert.Equal(t, float64(49005), payload["average_fill_price"])
}

func sampleBracket(entryID string) BracketRecord {
	return BracketRecord{
		Venue:              "SPOT",
		IdempotencyKey:     "test:" + entryID,
		RequestHash:        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
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
			{Role: "SL", ClientOrderID: entryID + "-sl", Price: decimal.RequireFromString("48950"), StopPrice: decimal.RequireFromString("49000"), Quantity: decimal.RequireFromString("0.02")},
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

func TestBracketRepo_LoadOpenBracketsIncludesActiveEntriesOlderThanLookback(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	record, inserted, err := repo.Reserve(ctx, sampleBracket("old-open-"+uuid.NewString()[:8]))
	require.NoError(t, err)
	require.True(t, inserted)
	_, err = repo.pool.Exec(ctx, `
		UPDATE brackets
		SET status = $2, created_at = CURRENT_TIMESTAMP - INTERVAL '8 days'
		WHERE bracket_id = $1
	`, record.BracketID, BracketStatusEntryPlaced)
	require.NoError(t, err)

	open := loadAllOpenBrackets(t, repo, ctx, 2)
	found := false
	for _, item := range open {
		found = found || item.BracketID == record.BracketID
	}
	assert.True(t, found)
}

func TestBracketRepo_LoadOpenBracketPageIsBoundedStableAndComplete(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	createdAt := time.Date(2026, 8, 20, 0, 0, 0, 0, time.UTC)
	initial := make([]BracketRecord, 3)
	for i := range initial {
		record, inserted, err := repo.Reserve(ctx, sampleBracket("paged-open-"+uuid.NewString()[:8]))
		require.NoError(t, err)
		require.True(t, inserted)
		initial[i] = *record
		_, err = repo.pool.Exec(ctx, `
			UPDATE brackets SET status=$2, created_at=$3 WHERE bracket_id=$1
		`, record.BracketID, BracketStatusEntryPlaced, createdAt)
		require.NoError(t, err)
	}
	closed, inserted, err := repo.Reserve(ctx, sampleBracket("paged-closed-"+uuid.NewString()[:8]))
	require.NoError(t, err)
	require.True(t, inserted)
	require.NoError(t, repo.UpdateBracketStatus(ctx, closed.BracketID, BracketStatusClosed))

	var firstPass []BracketRecord
	var cursor *OpenBracketCursor
	for pageNumber := 0; ; pageNumber++ {
		page, next, err := repo.LoadOpenBracketPage(ctx, cursor, 1)
		require.NoError(t, err)
		require.LessOrEqual(t, len(page), 1)
		firstPass = append(firstPass, page...)
		if pageNumber == 0 {
			late, inserted, err := repo.Reserve(ctx, sampleBracket("paged-late-"+uuid.NewString()[:8]))
			require.NoError(t, err)
			require.True(t, inserted)
			require.NoError(t, repo.UpdateBracketStatus(ctx, late.BracketID, BracketStatusEntryPlaced))
		}
		if next == nil {
			break
		}
		cursor = next
	}

	require.Len(t, firstPass, len(initial), "high-water cursor excludes inserts after the pass starts")
	seen := map[uuid.UUID]bool{}
	for _, record := range firstPass {
		seen[record.BracketID] = true
	}
	for _, record := range initial {
		assert.True(t, seen[record.BracketID])
	}
	assert.False(t, seen[closed.BracketID])
	assert.Len(t, loadAllOpenBrackets(t, repo, ctx, 2), len(initial)+1)
}

func TestBracketRepo_UpdateLegQuantityCannotResizeClaimedPlacement(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	record, inserted, err := repo.Reserve(ctx, sampleBracket("claimed-qty-"+uuid.NewString()[:8]))
	require.NoError(t, err)
	require.True(t, inserted)
	tpID := record.EntryClientOrderID + "-tp1"
	claimed, err := repo.TryMarkLegPlacing(ctx, record.BracketID, tpID)
	require.NoError(t, err)
	require.True(t, claimed)

	require.NoError(t, repo.UpdateLegQuantity(ctx, record.BracketID, tpID, decimal.RequireFromString("0.02")))
	require.Error(t, repo.UpdateLegQuantity(ctx, record.BracketID, tpID, decimal.RequireFromString("0.01")))
}

func TestBracketRepo_UpdateLegExecutionProgressRejectsDelayedAverageRegression(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "monotonic-average-" + uuid.NewString()[:8]
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, "PARTIALLY_FILLED", 99001,
		decimal.RequireFromString("0.01"), decimal.RequireFromString("50010"),
		time.Date(2026, 3, 21, 20, 5, 0, 0, time.UTC),
	))
	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, LegStatusFilled, 99001,
		decimal.RequireFromString("0.02"), decimal.RequireFromString("50020"),
		time.Date(2026, 3, 21, 20, 6, 0, 0, time.UTC),
	))
	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, "PARTIALLY_FILLED", 99001,
		decimal.RequireFromString("0.01"), decimal.RequireFromString("50010"),
		time.Date(2026, 3, 21, 20, 5, 0, 0, time.UTC),
	))

	var status, executedQuantity, averageFillPrice string
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT status, executed_quantity::text, average_fill_price::text
		FROM bracket_legs
		WHERE bracket_id = $1 AND client_order_id = $2
	`, record.BracketID, entryID).Scan(&status, &executedQuantity, &averageFillPrice))
	assert.Equal(t, LegStatusFilled, status)
	assert.Equal(t, "0.02000000", executedQuantity)
	assert.Equal(t, "50020.00000000", averageFillPrice)

	var payload map[string]any
	var payloadBytes []byte
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT payload
		FROM router_order_update_outbox
		WHERE aggregate_id = 'SPOT:' || $1
		ORDER BY sequence DESC LIMIT 1
	`, entryID).Scan(&payloadBytes))
	require.NoError(t, json.Unmarshal(payloadBytes, &payload))
	assert.Equal(t, "FILLED", payload["status"])
	assert.Equal(t, float64(0.02), payload["executed_qty"])
	assert.Equal(t, float64(50020), payload["average_fill_price"])
}

func TestBracketRepo_UpdateLegExecutionProgressFencesSameQuantityAverageCorrectionsByObservationTime(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	entryID := "same-quantity-average-" + uuid.NewString()[:8]
	record, inserted, err := repo.Reserve(ctx, sampleBracket(entryID))
	require.NoError(t, err)
	require.True(t, inserted)

	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, "PARTIALLY_FILLED", 99001,
		decimal.RequireFromString("0.01"), decimal.RequireFromString("50010"),
		time.Date(2026, 3, 21, 20, 5, 0, 0, time.UTC),
	))
	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, "PARTIALLY_FILLED", 99001,
		decimal.RequireFromString("0.01"), decimal.RequireFromString("50012"),
		time.Date(2026, 3, 21, 20, 6, 0, 0, time.UTC),
	))
	require.NoError(t, repo.UpdateLegExecutionProgress(
		ctx, record.BracketID, entryID, "PARTIALLY_FILLED", 99001,
		decimal.RequireFromString("0.01"), decimal.RequireFromString("50008"),
		time.Date(2026, 3, 21, 20, 4, 0, 0, time.UTC),
	))

	var status, executedQuantity, averageFillPrice string
	var executionObservedAt time.Time
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT status, executed_quantity::text, average_fill_price::text, execution_observed_at
		FROM bracket_legs
		WHERE bracket_id = $1 AND client_order_id = $2
	`, record.BracketID, entryID).Scan(
		&status, &executedQuantity, &averageFillPrice, &executionObservedAt,
	))
	assert.Equal(t, LegStatusPlaced, status)
	assert.Equal(t, "0.01000000", executedQuantity)
	assert.Equal(t, "50012.00000000", averageFillPrice)
	assert.True(t, executionObservedAt.Equal(time.Date(2026, 3, 21, 20, 6, 0, 0, time.UTC)))

	var payload map[string]any
	var payloadBytes []byte
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT payload
		FROM router_order_update_outbox
		WHERE aggregate_id = 'SPOT:' || $1
		ORDER BY sequence DESC LIMIT 1
	`, entryID).Scan(&payloadBytes))
	require.NoError(t, json.Unmarshal(payloadBytes, &payload))
	assert.Equal(t, "PARTIALLY_FILLED", payload["status"])
	assert.Equal(t, float64(0.01), payload["executed_qty"])
	assert.Equal(t, float64(50012), payload["average_fill_price"])
	updateTime, ok := payload["update_time"].(string)
	require.True(t, ok)
	parsedUpdateTime, err := time.Parse(time.RFC3339Nano, updateTime)
	require.NoError(t, err)
	assert.Equal(t, time.Date(2026, 3, 21, 20, 6, 0, 0, time.UTC), parsedUpdateTime.UTC())
}

func TestBracketRepo_ReserveConflictsOnVenueAndIdempotencyKey(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	first := sampleBracket("it-" + uuid.NewString()[:8])
	second := sampleBracket("it-" + uuid.NewString()[:8])
	second.IdempotencyKey = first.IdempotencyKey
	second.RequestHash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"

	stored, inserted, err := repo.Reserve(ctx, first)
	require.NoError(t, err)
	require.True(t, inserted)
	replayed, inserted, err := repo.Reserve(ctx, second)
	require.NoError(t, err)

	assert.False(t, inserted)
	assert.Equal(t, stored.BracketID, replayed.BracketID)
	assert.Equal(t, first.RequestHash, replayed.RequestHash)
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

	open := loadAllOpenBrackets(t, repo, ctx, 2)
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
	open = loadAllOpenBrackets(t, repo, ctx, 2)
	for i := range open {
		assert.NotEqual(t, entryID, open[i].EntryClientOrderID, "closed bracket must leave the open scan")
	}
}

func TestBracketRepo_AdvanceBracketStatusRejectsRegression(t *testing.T) {
	repo, ctx := newBracketTestRepo(t)
	record, inserted, err := repo.Reserve(ctx, sampleBracket("status-advance-"+uuid.NewString()[:8]))
	require.NoError(t, err)
	require.True(t, inserted)

	advanced, err := repo.AdvanceBracketStatus(ctx, record.BracketID, BracketStatusEntryFilled)
	require.NoError(t, err)
	require.True(t, advanced)
	advanced, err = repo.AdvanceBracketStatus(ctx, record.BracketID, BracketStatusLegsPlaced)
	require.NoError(t, err)
	require.True(t, advanced)
	advanced, err = repo.AdvanceBracketStatus(ctx, record.BracketID, BracketStatusEntryFilled)
	require.NoError(t, err)
	assert.False(t, advanced)

	var status string
	require.NoError(t, repo.pool.QueryRow(ctx, `
		SELECT status FROM brackets WHERE bracket_id=$1
	`, record.BracketID).Scan(&status))
	assert.Equal(t, BracketStatusLegsPlaced, status)
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
