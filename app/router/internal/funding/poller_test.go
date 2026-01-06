package funding

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"router/internal/rest"
	"router/internal/storage"
)

func TestApplyFundingIncomeTx_UpdatesActivePosition(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := storage.NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	require.NoError(t, storage.RunInTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE TEMP TABLE positions (
				position_id UUID NOT NULL DEFAULT gen_random_uuid(),
				venue TEXT NOT NULL,
				symbol TEXT NOT NULL,
				is_active BOOLEAN NOT NULL DEFAULT TRUE,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `INSERT INTO positions (venue, symbol, is_active, funding_paid) VALUES ('futures','BTCUSDT', true, 0)`)
		require.NoError(t, err)

		records := []rest.FuturesIncomeRecord{
			{IncomeType: "FUNDING_FEE", Income: "-0.01", Symbol: "BTCUSDT"},
		}
		require.NoError(t, applyFundingIncomeTx(ctx, tx, records))

		row := tx.QueryRow(ctx, `SELECT funding_paid FROM positions WHERE venue='futures' AND symbol='BTCUSDT' AND is_active=true`)
		var got decimal.Decimal
		require.NoError(t, row.Scan(&got))
		require.True(t, decimal.RequireFromString("-0.01").Equal(got))
		return nil
	}))
}
