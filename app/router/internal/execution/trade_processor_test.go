package execution

import (
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

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
