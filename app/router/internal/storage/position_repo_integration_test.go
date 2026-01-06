package storage

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// createTempTableWithPartialIndex creates a temporary positions table WITH the partial unique index
// required for testing ON CONFLICT behavior
func createTempTableWithPartialIndex(ctx context.Context, t *testing.T, tx pgx.Tx) {
	t.Helper()

	_, err := tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
	require.NoError(t, err)

	_, err = tx.Exec(ctx, `
		CREATE TEMP TABLE positions (
			position_id UUID NOT NULL DEFAULT gen_random_uuid(),
			venue TEXT NOT NULL,
			symbol TEXT NOT NULL,
			side TEXT NOT NULL,
			size NUMERIC(18,8) NOT NULL,
			entry_price NUMERIC(18,8) NOT NULL,
			current_price NUMERIC(18,8) NOT NULL,
			unrealized_pnl NUMERIC(18,8) NOT NULL,
			realized_pnl NUMERIC(18,8) NOT NULL DEFAULT 0,
			margin_used NUMERIC(18,8) NOT NULL DEFAULT 0,
			leverage NUMERIC(5,2) NOT NULL DEFAULT 1,
			opened_at TIMESTAMPTZ NOT NULL,
			updated_at TIMESTAMPTZ NOT NULL,
			closed_at TIMESTAMPTZ,
			is_active BOOLEAN NOT NULL DEFAULT TRUE,
			commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
			funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
			slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0
		) ON COMMIT DROP
	`)
	require.NoError(t, err)

	// Create the partial unique index - required for ON CONFLICT to work
	_, err = tx.Exec(ctx, `
		CREATE UNIQUE INDEX uq_positions_active
		ON positions (venue, symbol)
		WHERE is_active = TRUE
	`)
	require.NoError(t, err)
}

// countActivePositions returns count of active positions for venue/symbol
func countActivePositions(ctx context.Context, tx pgx.Tx, venue, symbol string) (int, error) {
	var count int
	err := tx.QueryRow(ctx,
		`SELECT COUNT(*) FROM positions WHERE venue = $1 AND symbol = $2 AND is_active = TRUE`,
		venue, symbol,
	).Scan(&count)
	return count, err
}

// getPositionID retrieves the position_id for an active position
func getPositionID(ctx context.Context, tx pgx.Tx, venue, symbol string) (uuid.UUID, error) {
	var id uuid.UUID
	err := tx.QueryRow(ctx,
		`SELECT position_id FROM positions WHERE venue = $1 AND symbol = $2 AND is_active = TRUE`,
		venue, symbol,
	).Scan(&id)
	return id, err
}

func TestPositionRepo_UpsertAndCloseActivePosition(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewPositionRepo()

	now := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE TEMP TABLE positions (
				position_id UUID NOT NULL DEFAULT gen_random_uuid(),
				venue TEXT NOT NULL,
				symbol TEXT NOT NULL,
				side TEXT NOT NULL,
				size NUMERIC(18,8) NOT NULL,
				entry_price NUMERIC(18,8) NOT NULL,
				current_price NUMERIC(18,8) NOT NULL,
				unrealized_pnl NUMERIC(18,8) NOT NULL,
				realized_pnl NUMERIC(18,8) NOT NULL DEFAULT 0,
				margin_used NUMERIC(18,8) NOT NULL DEFAULT 0,
				leverage NUMERIC(5,2) NOT NULL DEFAULT 1,
				opened_at TIMESTAMPTZ NOT NULL,
				updated_at TIMESTAMPTZ NOT NULL,
				closed_at TIMESTAMPTZ,
				is_active BOOLEAN NOT NULL DEFAULT TRUE,
				commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		require.NoError(t, repo.UpsertActive(ctx, tx, ActivePositionUpsert{
			Venue:          "futures",
			Symbol:         "BTCUSDT",
			Side:           "BUY",
			Size:           decimal.RequireFromString("0.01"),
			EntryPrice:     decimal.RequireFromString("100"),
			CurrentPrice:   decimal.RequireFromString("100"),
			RealizedPnL:    decimal.Zero,
			CommissionPaid: decimal.Zero,
			FundingPaid:    decimal.Zero,
			SlippagePaid:   decimal.Zero,
			OpenedAt:       now,
			UpdatedAt:      now,
		}))

		pos, found, err := repo.GetActive(ctx, tx, "futures", "BTCUSDT")
		require.NoError(t, err)
		require.True(t, found)
		require.Equal(t, "BUY", pos.Side)

		require.NoError(t, repo.CloseActive(ctx, tx, "futures", "BTCUSDT", PositionClose{
			ClosedAt:       now.Add(time.Minute),
			CurrentPrice:   decimal.RequireFromString("110"),
			RealizedPnL:    decimal.RequireFromString("1"),
			CommissionPaid: decimal.RequireFromString("0.04"),
			SlippagePaid:   decimal.RequireFromString("0.01"),
		}))

		_, found, err = repo.GetActive(ctx, tx, "futures", "BTCUSDT")
		require.NoError(t, err)
		require.False(t, found)
		return nil
	}))
}

// =============================================================================
// Tests for Position Upsert Concurrency (P1 #5)
// =============================================================================

func TestPositionRepo_UpsertActive_PreservesPositionID(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewPositionRepo()
	now := time.Date(2026, 1, 7, 12, 0, 0, 0, time.UTC)

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		createTempTableWithPartialIndex(ctx, t, tx)

		// First upsert - creates position
		err := repo.UpsertActive(ctx, tx, ActivePositionUpsert{
			Venue:          "futures",
			Symbol:         "ETHUSDT",
			Side:           "BUY",
			Size:           decimal.RequireFromString("1.0"),
			EntryPrice:     decimal.RequireFromString("3000"),
			CurrentPrice:   decimal.RequireFromString("3000"),
			RealizedPnL:    decimal.Zero,
			CommissionPaid: decimal.Zero,
			FundingPaid:    decimal.Zero,
			SlippagePaid:   decimal.Zero,
			OpenedAt:       now,
			UpdatedAt:      now,
		})
		require.NoError(t, err)

		// Record original position_id
		originalID, err := getPositionID(ctx, tx, "futures", "ETHUSDT")
		require.NoError(t, err)
		require.NotEqual(t, uuid.Nil, originalID, "position_id should be generated")

		// Second upsert - updates position with different values
		err = repo.UpsertActive(ctx, tx, ActivePositionUpsert{
			Venue:          "futures",
			Symbol:         "ETHUSDT",
			Side:           "SELL", // Changed side
			Size:           decimal.RequireFromString("2.0"),
			EntryPrice:     decimal.RequireFromString("3100"),
			CurrentPrice:   decimal.RequireFromString("3050"),
			RealizedPnL:    decimal.RequireFromString("100"),
			CommissionPaid: decimal.RequireFromString("0.5"),
			FundingPaid:    decimal.RequireFromString("0.1"),
			SlippagePaid:   decimal.RequireFromString("0.05"),
			OpenedAt:       now,
			UpdatedAt:      now.Add(time.Minute),
		})
		require.NoError(t, err)

		// Verify position_id is preserved
		newID, err := getPositionID(ctx, tx, "futures", "ETHUSDT")
		require.NoError(t, err)
		assert.Equal(t, originalID, newID, "position_id should be preserved across upserts")

		// Verify fields were updated
		pos, found, err := repo.GetActive(ctx, tx, "futures", "ETHUSDT")
		require.NoError(t, err)
		require.True(t, found)
		assert.Equal(t, "SELL", pos.Side, "side should be updated")
		assert.True(t, pos.Size.Equal(decimal.RequireFromString("2.0")), "size should be updated")
		assert.True(t, pos.EntryPrice.Equal(decimal.RequireFromString("3100")), "entry_price should be updated")

		return nil
	}))
}

func TestPositionRepo_UpsertActive_UpdatesExistingFields(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewPositionRepo()
	now := time.Date(2026, 1, 7, 12, 0, 0, 0, time.UTC)

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		createTempTableWithPartialIndex(ctx, t, tx)

		// Initial insert
		initialUpsert := ActivePositionUpsert{
			Venue:          "spot",
			Symbol:         "SOLUSDT",
			Side:           "BUY",
			Size:           decimal.RequireFromString("10"),
			EntryPrice:     decimal.RequireFromString("100"),
			CurrentPrice:   decimal.RequireFromString("100"),
			RealizedPnL:    decimal.Zero,
			CommissionPaid: decimal.Zero,
			FundingPaid:    decimal.Zero,
			SlippagePaid:   decimal.Zero,
			OpenedAt:       now,
			UpdatedAt:      now,
		}
		require.NoError(t, repo.UpsertActive(ctx, tx, initialUpsert))

		// Verify initial state
		pos1, found, err := repo.GetActive(ctx, tx, "spot", "SOLUSDT")
		require.NoError(t, err)
		require.True(t, found)
		assert.Equal(t, "BUY", pos1.Side)
		assert.True(t, pos1.Size.Equal(decimal.RequireFromString("10")))
		assert.True(t, pos1.CommissionPaid.IsZero())

		// Update with new values
		updateUpsert := ActivePositionUpsert{
			Venue:          "spot",
			Symbol:         "SOLUSDT",
			Side:           "BUY",
			Size:           decimal.RequireFromString("15"),
			EntryPrice:     decimal.RequireFromString("105"),
			CurrentPrice:   decimal.RequireFromString("110"),
			RealizedPnL:    decimal.RequireFromString("50"),
			CommissionPaid: decimal.RequireFromString("1.5"),
			FundingPaid:    decimal.RequireFromString("0.3"),
			SlippagePaid:   decimal.RequireFromString("0.2"),
			OpenedAt:       now,
			UpdatedAt:      now.Add(5 * time.Minute),
		}
		require.NoError(t, repo.UpsertActive(ctx, tx, updateUpsert))

		// Verify all fields updated
		pos2, found, err := repo.GetActive(ctx, tx, "spot", "SOLUSDT")
		require.NoError(t, err)
		require.True(t, found)

		assert.True(t, pos2.Size.Equal(decimal.RequireFromString("15")), "size should update")
		assert.True(t, pos2.EntryPrice.Equal(decimal.RequireFromString("105")), "entry_price should update")
		assert.True(t, pos2.CurrentPrice.Equal(decimal.RequireFromString("110")), "current_price should update")
		assert.True(t, pos2.RealizedPnL.Equal(decimal.RequireFromString("50")), "realized_pnl should update")
		assert.True(t, pos2.CommissionPaid.Equal(decimal.RequireFromString("1.5")), "commission_paid should update")
		assert.True(t, pos2.FundingPaid.Equal(decimal.RequireFromString("0.3")), "funding_paid should update")
		assert.True(t, pos2.SlippagePaid.Equal(decimal.RequireFromString("0.2")), "slippage_paid should update")

		return nil
	}))
}

func TestPositionRepo_UpsertActive_NoDuplicatesWithMultipleUpserts(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewPositionRepo()
	now := time.Date(2026, 1, 7, 12, 0, 0, 0, time.UTC)

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		createTempTableWithPartialIndex(ctx, t, tx)

		// Perform 10 sequential upserts (simulating what concurrent upserts would do
		// with ON CONFLICT - they serialize at the database level)
		for i := 0; i < 10; i++ {
			err := repo.UpsertActive(ctx, tx, ActivePositionUpsert{
				Venue:          "futures",
				Symbol:         "BTCUSDT",
				Side:           "BUY",
				Size:           decimal.RequireFromString("0.001").Mul(decimal.NewFromInt(int64(i + 1))),
				EntryPrice:     decimal.RequireFromString("50000"),
				CurrentPrice:   decimal.RequireFromString("50100"),
				RealizedPnL:    decimal.Zero,
				CommissionPaid: decimal.Zero,
				FundingPaid:    decimal.Zero,
				SlippagePaid:   decimal.Zero,
				OpenedAt:       now,
				UpdatedAt:      now.Add(time.Duration(i) * time.Second),
			})
			require.NoError(t, err, "upsert %d should succeed", i)
		}

		// Count should be exactly 1
		count, err := countActivePositions(ctx, tx, "futures", "BTCUSDT")
		require.NoError(t, err)
		assert.Equal(t, 1, count, "multiple upserts should produce exactly one row")

		// Verify final state has last values
		pos, found, err := repo.GetActive(ctx, tx, "futures", "BTCUSDT")
		require.NoError(t, err)
		require.True(t, found)
		// Last upsert was i=9, so size = 0.001 * 10 = 0.01
		assert.True(t, pos.Size.Equal(decimal.RequireFromString("0.01")),
			"final size should be from last upsert: got %s", pos.Size)

		return nil
	}))
}

func TestPositionRepo_UpsertActive_DifferentSymbolsAreSeparate(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewPositionRepo()
	now := time.Date(2026, 1, 7, 12, 0, 0, 0, time.UTC)

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		createTempTableWithPartialIndex(ctx, t, tx)

		// Insert positions for different symbols
		symbols := []string{"BTCUSDT", "ETHUSDT", "SOLUSDT"}
		for _, symbol := range symbols {
			err := repo.UpsertActive(ctx, tx, ActivePositionUpsert{
				Venue:          "futures",
				Symbol:         symbol,
				Side:           "BUY",
				Size:           decimal.RequireFromString("1"),
				EntryPrice:     decimal.RequireFromString("100"),
				CurrentPrice:   decimal.RequireFromString("100"),
				RealizedPnL:    decimal.Zero,
				CommissionPaid: decimal.Zero,
				FundingPaid:    decimal.Zero,
				SlippagePaid:   decimal.Zero,
				OpenedAt:       now,
				UpdatedAt:      now,
			})
			require.NoError(t, err)
		}

		// Each symbol should have exactly one position
		for _, symbol := range symbols {
			count, err := countActivePositions(ctx, tx, "futures", symbol)
			require.NoError(t, err)
			assert.Equal(t, 1, count, "symbol %s should have exactly one position", symbol)
		}

		// Total count should be 3
		var totalCount int
		err := tx.QueryRow(ctx, `SELECT COUNT(*) FROM positions WHERE is_active = TRUE`).Scan(&totalCount)
		require.NoError(t, err)
		assert.Equal(t, 3, totalCount, "should have 3 separate positions")

		return nil
	}))
}
