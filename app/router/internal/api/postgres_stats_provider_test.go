package api

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"router/internal/storage"
)

func TestPostgresStatsProvider_ComputesNetPnLFromClosedPositions(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	provider := NewPostgresStatsProvider(pool)

	require.NoError(t, storage.RunInTx(ctx, pool, func(tx pgx.Tx) error {
		_, err = tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
		require.NoError(t, err)

		_, err := tx.Exec(ctx, `
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
				commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				opened_at TIMESTAMPTZ NOT NULL,
				updated_at TIMESTAMPTZ NOT NULL,
				closed_at TIMESTAMPTZ,
				is_active BOOLEAN NOT NULL DEFAULT TRUE
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			INSERT INTO positions (
				venue, symbol, side, size, entry_price, current_price, unrealized_pnl, realized_pnl,
				commission_paid, funding_paid, slippage_paid,
				opened_at, updated_at, closed_at, is_active
			) VALUES
				('futures','BTCUSDT','BUY',0,100,110,0, 10, 1, 0, 0, now(), now(), now(), false),
				('futures','ETHUSDT','BUY',0,100, 90,0,-10, 1, 0, 0, now(), now(), now(), false)
		`)
		require.NoError(t, err)

		stats, err := provider.computeStatsTx(ctx, tx)
		require.NoError(t, err)
		require.Equal(t, 2, stats.TotalTrades)
		require.Equal(t, 1, stats.WinCount)
		require.Equal(t, 1, stats.LossCount)
		require.True(t, decimal.RequireFromString("-2").Equal(decimal.RequireFromString(stats.NetPnL)))
		return nil
	}))
}
