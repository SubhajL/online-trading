package storage

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

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
