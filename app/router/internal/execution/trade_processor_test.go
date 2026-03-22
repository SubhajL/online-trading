package execution

import (
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/pnl"
	"router/internal/storage"
	"router/internal/websocket"
)

func TestShouldProcessOrderTradeUpdate(t *testing.T) {
	t.Run("ignores non-trade execution types", func(t *testing.T) {
		ok := shouldProcessOrderTradeUpdate(&websocket.FuturesOrderTradeUpdateEvent{
			EventType: "ORDER_TRADE_UPDATE",
			OrderTradeUpdate: websocket.FuturesOrderTradeData{
				ExecutionType:        "NEW",
				LastExecutedQuantity: decimal.RequireFromString("0.01"),
				TradeID:              123,
			},
		})
		assert.False(t, ok)
	})

	t.Run("ignores empty fills", func(t *testing.T) {
		ok := shouldProcessOrderTradeUpdate(&websocket.FuturesOrderTradeUpdateEvent{
			EventType: "ORDER_TRADE_UPDATE",
			OrderTradeUpdate: websocket.FuturesOrderTradeData{
				ExecutionType:        "TRADE",
				LastExecutedQuantity: decimal.Zero,
				TradeID:              123,
			},
		})
		assert.False(t, ok)
	})

	t.Run("processes trade events with positive qty and trade id", func(t *testing.T) {
		ok := shouldProcessOrderTradeUpdate(&websocket.FuturesOrderTradeUpdateEvent{
			EventType: "ORDER_TRADE_UPDATE",
			OrderTradeUpdate: websocket.FuturesOrderTradeData{
				ExecutionType:        "TRADE",
				LastExecutedQuantity: decimal.RequireFromString("0.01"),
				TradeID:              123,
			},
		})
		assert.True(t, ok)
	})
}

func TestOrderTradeUpdateEventTime(t *testing.T) {
	got := futuresEventTimeUTC(1_700_000_000_000)
	require.Equal(t, time.UnixMilli(1_700_000_000_000).UTC(), got)
}

func TestApplyFillsToActivePosition(t *testing.T) {
	t.Run("aggregates realized pnl across multiple fills", func(t *testing.T) {
		current, realized, err := applyFillsToActivePosition(
			true,
			&storage.ActivePosition{
				Side:       "BUY",
				Size:       decimal.RequireFromString("0.02"),
				EntryPrice: decimal.RequireFromString("100"),
			},
			[]pnl.Fill{
				{
					Side:     "SELL",
					Quantity: decimal.RequireFromString("0.01"),
					Price:    decimal.RequireFromString("110"),
				},
				{
					Side:     "SELL",
					Quantity: decimal.RequireFromString("0.01"),
					Price:    decimal.RequireFromString("115"),
				},
			},
		)
		require.NoError(t, err)
		assert.Nil(t, current)
		assert.True(t, decimal.RequireFromString("0.25").Equal(realized))
	})
}

func TestBuildPositionPersistence(t *testing.T) {
	t.Run("preserves existing metadata when scaling same-side position", func(t *testing.T) {
		openedAt := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
		updateTime := openedAt.Add(time.Minute)
		result := buildPositionPersistence(
			"USD_M",
			"BTCUSDT",
			&pnl.Position{
				Side:       "BUY",
				Quantity:   decimal.RequireFromString("0.02"),
				EntryPrice: decimal.RequireFromString("101"),
			},
			true,
			&storage.ActivePosition{
				Side:           "BUY",
				OpenedAt:       openedAt,
				RealizedPnL:    decimal.RequireFromString("0.03"),
				CommissionPaid: decimal.RequireFromString("0.04"),
				FundingPaid:    decimal.RequireFromString("0.02"),
				SlippagePaid:   decimal.RequireFromString("0.01"),
				EntryOrderID:   "existing-entry",
			},
			"new-entry",
			decimal.RequireFromString("102"),
			decimal.Zero,
			decimal.RequireFromString("0.05"),
			decimal.Zero,
			decimal.RequireFromString("0.02"),
			updateTime,
		)
		require.Nil(t, result.close)
		require.NotNil(t, result.upsert)
		assert.Equal(t, "existing-entry", result.upsert.EntryOrderID)
		assert.Equal(t, openedAt, result.upsert.OpenedAt)
		assert.Equal(t, updateTime, result.upsert.UpdatedAt)
		assert.True(t, decimal.RequireFromString("0.03").Equal(result.upsert.RealizedPnL))
		assert.True(t, decimal.RequireFromString("0.09").Equal(result.upsert.CommissionPaid))
		assert.True(t, decimal.RequireFromString("0.02").Equal(result.upsert.FundingPaid))
		assert.True(t, decimal.RequireFromString("0.03").Equal(result.upsert.SlippagePaid))
	})
}
