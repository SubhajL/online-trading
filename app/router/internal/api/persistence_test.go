package api

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"router/internal/orders"
	"router/internal/storage"
)

func TestBuildBracketOrderIntents_FuturesOneTP(t *testing.T) {
	req := orders.PlaceBracketRequest{
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.01"),
		EntryPrice:       decimal.RequireFromString("100"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("110")},
		StopLossPrice:    decimal.RequireFromString("95"),
		OrderType:        "LIMIT",
		IsFutures:        true,
		Metadata: map[string]any{
			"signal_id": "sig-1",
			"timeframe": "5m",
			"zone": map[string]any{
				"kind": "OB",
			},
		},
	}
	resp := orders.PlaceBracketResponse{
		ClientOrderIDs: orders.ClientOrderIDs{
			Main:        "main",
			TakeProfits: []string{"tp1"},
			StopLoss:    "sl",
		},
	}

	intents, err := buildBracketOrderIntents(req, resp)
	require.NoError(t, err)
	require.Len(t, intents, 3)

	require.Equal(t, "main", intents[0].ClientOrderID)
	require.False(t, intents[0].ReduceOnly)

	require.Equal(t, "tp1", intents[1].ClientOrderID)
	require.True(t, intents[1].ReduceOnly)

	require.Equal(t, "sl", intents[2].ClientOrderID)
	require.True(t, intents[2].ReduceOnly)
	require.True(t, intents[2].ClosePosition)

	for _, intent := range intents {
		require.Equal(t, "USD_M", intent.Venue)
		require.Equal(t, "sig-1", intent.SignalID)
		require.Equal(t, "5m", intent.Timeframe)
		require.NotNil(t, intent.Zone)
	}

	require.Equal(t, storage.OrderIntent{Venue: "USD_M"}, storage.OrderIntent{Venue: intents[0].Venue})
}
