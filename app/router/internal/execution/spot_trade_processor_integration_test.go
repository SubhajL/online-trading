package execution

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"router/internal/orders"
	"router/internal/storage"
)

func TestSpotTradeProcessor_PersistsFillsAndPositions(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	pool, err := storage.NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	ordersRepo := storage.NewOrderRepo()
	fillRepo := storage.NewFillRepo()
	posRepo := storage.NewPositionRepo()

	processor, err := NewSpotTradeProcessor(
		pool,
		ordersRepo,
		fillRepo,
		posRepo,
	)
	require.NoError(t, err)

	now := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

	require.NoError(t, storage.RunInTx(ctx, pool, func(tx pgx.Tx) error {
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
				decision_ts TIMESTAMPTZ,
				expected_price NUMERIC(20,8),
				router_received_ts TIMESTAMPTZ,
				router_sent_ts TIMESTAMPTZ,
				exchange_ack_ts TIMESTAMPTZ,
				first_fill_ts TIMESTAMPTZ,
				filled_ts TIMESTAMPTZ,
				timeframe TEXT,
				zone JSONB,
				CONSTRAINT uq_orders_client_order_id UNIQUE (venue, client_order_id)
			) ON COMMIT DROP
		`)
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
				entry_order_id UUID,
				commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE UNIQUE INDEX uq_positions_active
			ON positions (venue, symbol)
			WHERE is_active = TRUE
		`)
		require.NoError(t, err)

		_, err = ordersRepo.UpsertOrderIntent(ctx, tx, storage.OrderIntent{
			Venue:          "SPOT",
			Symbol:         "BTCUSDT",
			ClientOrderID:  "spot_entry",
			Side:           "BUY",
			Type:           "LIMIT",
			TimeInForce:    "GTC",
			Quantity:       decimal.RequireFromString("0.02"),
			Price:          decimal.RequireFromString("50000"),
			RequestedPrice: decimal.RequireFromString("50000"),
			SignalID:       "sig-spot-entry",
			Timeframe:      "5m",
		})
		require.NoError(t, err)

		entrySnapshot := orders.SpotExecutionSnapshot{
			Symbol:        "BTCUSDT",
			OrderID:       100,
			ClientOrderID: "spot_entry",
			Side:          "BUY",
			OrderType:     "LIMIT",
			Price:         decimal.RequireFromString("50000"),
			Quantity:      decimal.RequireFromString("0.02"),
			ExecutedQty:   decimal.RequireFromString("0.02"),
			Status:        "FILLED",
			UpdateTime:    now,
			Trades: []orders.SpotExecutionTrade{
				{
					TradeID:         701,
					Price:           decimal.RequireFromString("50010"),
					Quantity:        decimal.RequireFromString("0.02"),
					Commission:      decimal.RequireFromString("0.10"),
					CommissionAsset: "USDT",
					Time:            now,
				},
			},
		}
		require.NoError(t, processor.persistSpotExecutionTx(ctx, tx, entrySnapshot))

		pos, found, err := posRepo.GetActive(ctx, tx, "SPOT", "BTCUSDT")
		require.NoError(t, err)
		require.True(t, found)
		require.Equal(t, "BUY", pos.Side)
		require.True(t, decimal.RequireFromString("0.02").Equal(pos.Size))
		require.True(t, decimal.RequireFromString("50010").Equal(pos.EntryPrice))

		var fillCount int
		err = tx.QueryRow(ctx, `SELECT COUNT(*) FROM fills WHERE venue = $1 AND symbol = $2`, "SPOT", "BTCUSDT").Scan(&fillCount)
		require.NoError(t, err)
		require.Equal(t, 1, fillCount)

		_, err = ordersRepo.UpsertOrderIntent(ctx, tx, storage.OrderIntent{
			Venue:          "SPOT",
			Symbol:         "BTCUSDT",
			ClientOrderID:  "spot_tp",
			Side:           "SELL",
			Type:           "LIMIT",
			TimeInForce:    "GTC",
			Quantity:       decimal.RequireFromString("0.02"),
			Price:          decimal.RequireFromString("51000"),
			RequestedPrice: decimal.RequireFromString("51000"),
			SignalID:       "sig-spot-exit",
			Timeframe:      "5m",
		})
		require.NoError(t, err)

		exitSnapshot := orders.SpotExecutionSnapshot{
			Symbol:        "BTCUSDT",
			OrderID:       101,
			ClientOrderID: "spot_tp",
			Side:          "SELL",
			OrderType:     "LIMIT",
			Price:         decimal.RequireFromString("51000"),
			Quantity:      decimal.RequireFromString("0.02"),
			ExecutedQty:   decimal.RequireFromString("0.02"),
			Status:        "FILLED",
			UpdateTime:    now.Add(time.Minute),
			Trades: []orders.SpotExecutionTrade{
				{
					TradeID:         702,
					Price:           decimal.RequireFromString("51000"),
					Quantity:        decimal.RequireFromString("0.02"),
					Commission:      decimal.RequireFromString("0.11"),
					CommissionAsset: "USDT",
					Time:            now.Add(time.Minute),
				},
			},
		}
		require.NoError(t, processor.persistSpotExecutionTx(ctx, tx, exitSnapshot))

		pos, found, err = posRepo.GetActive(ctx, tx, "SPOT", "BTCUSDT")
		require.NoError(t, err)
		require.False(t, found)
		require.Nil(t, pos)

		err = tx.QueryRow(ctx, `SELECT COUNT(*) FROM fills WHERE venue = $1 AND symbol = $2`, "SPOT", "BTCUSDT").Scan(&fillCount)
		require.NoError(t, err)
		require.Equal(t, 2, fillCount)

		var entryStatus string
		var entryFilledQty decimal.Decimal
		err = tx.QueryRow(ctx, `
			SELECT status, filled_quantity
			FROM orders
			WHERE venue = $1 AND client_order_id = $2
		`, "SPOT", "spot_entry").Scan(&entryStatus, &entryFilledQty)
		require.NoError(t, err)
		require.Equal(t, "FILLED", entryStatus)
		require.True(t, decimal.RequireFromString("0.02").Equal(entryFilledQty))

		return nil
	}))
}

func TestSpotTradeProcessor_RejectsExecutedSnapshotWithoutTrades(t *testing.T) {
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	pool, err := storage.NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	ordersRepo := storage.NewOrderRepo()
	fillRepo := storage.NewFillRepo()
	posRepo := storage.NewPositionRepo()

	processor, err := NewSpotTradeProcessor(pool, ordersRepo, fillRepo, posRepo)
	require.NoError(t, err)

	now := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)

	require.NoError(t, storage.RunInTx(ctx, pool, func(tx pgx.Tx) error {
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
				decision_ts TIMESTAMPTZ,
				expected_price NUMERIC(20,8),
				router_received_ts TIMESTAMPTZ,
				router_sent_ts TIMESTAMPTZ,
				exchange_ack_ts TIMESTAMPTZ,
				first_fill_ts TIMESTAMPTZ,
				filled_ts TIMESTAMPTZ,
				timeframe TEXT,
				zone JSONB,
				CONSTRAINT uq_orders_client_order_id UNIQUE (venue, client_order_id)
			) ON COMMIT DROP
		`)
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
				entry_order_id UUID,
				commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = tx.Exec(ctx, `
			CREATE UNIQUE INDEX uq_positions_active
			ON positions (venue, symbol)
			WHERE is_active = TRUE
		`)
		require.NoError(t, err)

		_, err = ordersRepo.UpsertOrderIntent(ctx, tx, storage.OrderIntent{
			Venue:          "SPOT",
			Symbol:         "BTCUSDT",
			ClientOrderID:  "spot_entry",
			Side:           "BUY",
			Type:           "LIMIT",
			TimeInForce:    "GTC",
			Quantity:       decimal.RequireFromString("0.02"),
			Price:          decimal.RequireFromString("50000"),
			RequestedPrice: decimal.RequireFromString("50000"),
			SignalID:       "sig-spot-entry",
			Timeframe:      "5m",
		})
		require.NoError(t, err)

		err = processor.persistSpotExecutionTx(ctx, tx, orders.SpotExecutionSnapshot{
			Symbol:        "BTCUSDT",
			OrderID:       100,
			ClientOrderID: "spot_entry",
			Side:          "BUY",
			OrderType:     "LIMIT",
			Price:         decimal.RequireFromString("50000"),
			Quantity:      decimal.RequireFromString("0.02"),
			ExecutedQty:   decimal.RequireFromString("0.02"),
			Status:        "FILLED",
			UpdateTime:    now,
		})
		require.Error(t, err)

		return nil
	}))
}
