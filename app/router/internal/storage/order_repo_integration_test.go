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

func TestOrderRepo_ApplyFillUpdate_UpdatesTotalsAndStatus(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	repo := NewOrderRepo()

	require.NoError(t, RunInTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE TEMP TABLE orders (
				order_id UUID NOT NULL DEFAULT gen_random_uuid(),
				client_order_id TEXT NOT NULL,
				venue TEXT NOT NULL,
				symbol TEXT NOT NULL,
				side TEXT NOT NULL,
				type TEXT NOT NULL,
				quantity NUMERIC(18,8) NOT NULL,
				price NUMERIC(18,8),
				stop_price NUMERIC(18,8),
				time_in_force TEXT NOT NULL,
				status TEXT NOT NULL,
				filled_quantity NUMERIC(18,8) NOT NULL DEFAULT 0,
				average_fill_price NUMERIC(18,8),
				created_at TIMESTAMPTZ NOT NULL,
				updated_at TIMESTAMPTZ,
				exchange_order_id TEXT,
				last_update_time TIMESTAMPTZ,
				commission NUMERIC(18,8) NOT NULL DEFAULT 0,
				commission_asset TEXT,
				reduce_only BOOLEAN NOT NULL DEFAULT FALSE,
				close_position BOOLEAN NOT NULL DEFAULT FALSE,
				requested_price NUMERIC(18,8),
				total_commission NUMERIC(18,8) NOT NULL DEFAULT 0,
				total_slippage NUMERIC(18,8) NOT NULL DEFAULT 0,
				signal_id TEXT,
				timeframe TEXT,
				zone JSONB,
				decision_ts TIMESTAMPTZ,
				expected_price NUMERIC(20,8),
				router_received_ts TIMESTAMPTZ,
				CONSTRAINT uq_orders_client_order_id UNIQUE (venue, client_order_id)
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = repo.UpsertOrderIntent(ctx, tx, OrderIntent{
			Venue:          "USD_M",
			Symbol:         "BTCUSDT",
			ClientOrderID:  "abc_entry",
			Side:           "BUY",
			Type:           "LIMIT",
			TimeInForce:    "GTC",
			Quantity:       decimal.RequireFromString("0.01"),
			Price:          decimal.RequireFromString("100"),
			RequestedPrice: decimal.RequireFromString("100"),
			SignalID:       "sig-1",
			Timeframe:      "5m",
		})
		require.NoError(t, err)

		rec, found, err := repo.ApplyFillUpdate(ctx, tx, "USD_M", "abc_entry", OrderFillUpdate{
			Status:           "FILLED",
			FilledQuantity:   decimal.RequireFromString("0.01"),
			AverageFillPrice: decimal.RequireFromString("101.25"),
			ExchangeOrderID:  "12345",
			LastUpdateTime:   time.Unix(0, 0).UTC(),
			CommissionDelta:  decimal.RequireFromString("0.04"),
			CommissionAsset:  "USDT",
			SlippageDelta:    decimal.RequireFromString("0.01"),
		})
		require.NoError(t, err)
		require.True(t, found)
		require.Equal(t, "abc_entry", rec.ClientOrderID)
		require.True(t, decimal.RequireFromString("0.04").Equal(rec.TotalCommission))
		require.True(t, decimal.RequireFromString("0.01").Equal(rec.TotalSlippage))
		var averageFillPrice decimal.Decimal
		err = tx.QueryRow(
			ctx,
			`SELECT average_fill_price FROM orders WHERE venue = $1 AND client_order_id = $2`,
			"USD_M",
			"abc_entry",
		).Scan(&averageFillPrice)
		require.NoError(t, err)
		require.True(t, decimal.RequireFromString("101.25").Equal(averageFillPrice))
		return nil
	}))
}
