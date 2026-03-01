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

func TestFillRepo_InsertFillIfNew_DedupesByTradeID(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewFillRepo()

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE TEMP TABLE fills (
				fill_id UUID NOT NULL DEFAULT gen_random_uuid(),
				venue TEXT NOT NULL,
				symbol TEXT NOT NULL,
				trade_id BIGINT NOT NULL,
				client_order_id TEXT NOT NULL,
				side TEXT NOT NULL,
				price NUMERIC(18,8) NOT NULL,
				quantity NUMERIC(18,8) NOT NULL,
				commission NUMERIC(18,8) NOT NULL DEFAULT 0,
				commission_asset TEXT,
				realized_pnl NUMERIC(18,8),
				slippage NUMERIC(18,8) NOT NULL DEFAULT 0,
				created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
				CONSTRAINT uq_fills_trade UNIQUE (venue, symbol, trade_id)
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		inserted, err := repo.InsertFillIfNew(ctx, tx, FillRecord{
			Venue:         "USD_M",
			Symbol:        "BTCUSDT",
			TradeID:       123,
			ClientOrderID: "abc",
			Side:          "BUY",
			Price:         decimal.RequireFromString("101"),
			Quantity:      decimal.RequireFromString("0.01"),
			Commission:    decimal.RequireFromString("0.04"),
			Slippage:      decimal.RequireFromString("0.01"),
		})
		require.NoError(t, err)
		require.True(t, inserted)

		inserted, err = repo.InsertFillIfNew(ctx, tx, FillRecord{
			Venue:         "USD_M",
			Symbol:        "BTCUSDT",
			TradeID:       123,
			ClientOrderID: "abc",
			Side:          "BUY",
			Price:         decimal.RequireFromString("101"),
			Quantity:      decimal.RequireFromString("0.01"),
			Commission:    decimal.RequireFromString("0.04"),
			Slippage:      decimal.RequireFromString("0.01"),
		})
		require.NoError(t, err)
		require.False(t, inserted)
		return nil
	}))
}
