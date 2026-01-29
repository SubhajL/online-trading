package execution

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"router/internal/storage"
	"router/internal/websocket"
)

func TestTradeProcessor_UpdatesOrdersFillsAndPositions(t *testing.T) {
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

	processor := &TradeProcessor{
		pool:      pool,
		orders:    ordersRepo,
		fills:     fillRepo,
		positions: posRepo,
		venue:     "USD_M",
	}

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
				commission_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				funding_paid NUMERIC(18,8) NOT NULL DEFAULT 0,
				slippage_paid NUMERIC(18,8) NOT NULL DEFAULT 0
			) ON COMMIT DROP
		`)
		require.NoError(t, err)

		_, err = ordersRepo.UpsertOrderIntent(ctx, tx, storage.OrderIntent{
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

		entryEvent := &websocket.FuturesOrderTradeUpdateEvent{
			EventType:       "ORDER_TRADE_UPDATE",
			TransactionTime: now.UnixMilli(),
			OrderTradeUpdate: websocket.FuturesOrderTradeData{
				Symbol:               "BTCUSDT",
				ClientOrderID:        "abc_entry",
				Side:                 "BUY",
				ExecutionType:        "TRADE",
				OrderStatus:          "FILLED",
				OrderID:              11,
				TradeID:              101,
				LastExecutedQuantity: decimal.RequireFromString("0.01"),
				LastExecutedPrice:    decimal.RequireFromString("101"),
				CumulativeFilledQty:  decimal.RequireFromString("0.01"),
				AvgPrice:             decimal.RequireFromString("101"),
				CommissionAmount:     decimal.RequireFromString("0.04"),
				CommissionAsset:      "USDT",
			},
		}
		require.NoError(t, processor.handleFuturesOrderTradeUpdateTx(ctx, tx, entryEvent))

		pos, found, err := posRepo.GetActive(ctx, tx, "USD_M", "BTCUSDT")
		require.NoError(t, err)
		require.True(t, found)
		require.Equal(t, "BUY", pos.Side)
		require.True(t, decimal.RequireFromString("0.01").Equal(pos.Size))

		_, err = ordersRepo.UpsertOrderIntent(ctx, tx, storage.OrderIntent{
			Venue:          "USD_M",
			Symbol:         "BTCUSDT",
			ClientOrderID:  "abc_tp1",
			Side:           "SELL",
			Type:           "LIMIT",
			TimeInForce:    "GTC",
			Quantity:       decimal.RequireFromString("0.01"),
			Price:          decimal.RequireFromString("110"),
			RequestedPrice: decimal.RequireFromString("110"),
			SignalID:       "sig-1",
			Timeframe:      "5m",
			ReduceOnly:     true,
		})
		require.NoError(t, err)

		exitEvent := &websocket.FuturesOrderTradeUpdateEvent{
			EventType:       "ORDER_TRADE_UPDATE",
			TransactionTime: now.Add(time.Minute).UnixMilli(),
			OrderTradeUpdate: websocket.FuturesOrderTradeData{
				Symbol:               "BTCUSDT",
				ClientOrderID:        "abc_tp1",
				Side:                 "SELL",
				ExecutionType:        "TRADE",
				OrderStatus:          "FILLED",
				OrderID:              12,
				TradeID:              102,
				LastExecutedQuantity: decimal.RequireFromString("0.01"),
				LastExecutedPrice:    decimal.RequireFromString("110"),
				CumulativeFilledQty:  decimal.RequireFromString("0.01"),
				AvgPrice:             decimal.RequireFromString("110"),
				CommissionAmount:     decimal.RequireFromString("0.04"),
				CommissionAsset:      "USDT",
			},
		}
		require.NoError(t, processor.handleFuturesOrderTradeUpdateTx(ctx, tx, exitEvent))

		_, found, err = posRepo.GetActive(ctx, tx, "USD_M", "BTCUSDT")
		require.NoError(t, err)
		require.False(t, found)

		return nil
	}))
}
