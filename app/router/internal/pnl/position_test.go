package pnl

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

func TestApplyFillToPosition(t *testing.T) {
	t.Run("opens new position on first fill", func(t *testing.T) {
		pos, realized, err := ApplyFillToPosition(nil, Fill{
			Side:     "BUY",
			Quantity: decimal.RequireFromString("0.01"),
			Price:    decimal.RequireFromString("100"),
		})

		assert.NoError(t, err)
		assert.NotNil(t, pos)
		assert.Equal(t, "BUY", pos.Side)
		assert.True(t, decimal.RequireFromString("0.01").Equal(pos.Quantity))
		assert.True(t, decimal.RequireFromString("100").Equal(pos.EntryPrice))
		assert.True(t, decimal.Zero.Equal(realized))
	})

	t.Run("increases position and recalculates weighted entry", func(t *testing.T) {
		pos, realized, err := ApplyFillToPosition(&Position{
			Side:       "BUY",
			Quantity:   decimal.RequireFromString("1"),
			EntryPrice: decimal.RequireFromString("100"),
		}, Fill{
			Side:     "BUY",
			Quantity: decimal.RequireFromString("1"),
			Price:    decimal.RequireFromString("110"),
		})

		assert.NoError(t, err)
		assert.NotNil(t, pos)
		assert.Equal(t, "BUY", pos.Side)
		assert.True(t, decimal.RequireFromString("2").Equal(pos.Quantity))
		assert.True(t, decimal.RequireFromString("105").Equal(pos.EntryPrice))
		assert.True(t, decimal.Zero.Equal(realized))
	})

	t.Run("partially closes a long and realizes proportional pnl", func(t *testing.T) {
		pos, realized, err := ApplyFillToPosition(&Position{
			Side:       "BUY",
			Quantity:   decimal.RequireFromString("2"),
			EntryPrice: decimal.RequireFromString("100"),
		}, Fill{
			Side:     "SELL",
			Quantity: decimal.RequireFromString("0.5"),
			Price:    decimal.RequireFromString("110"),
		})

		assert.NoError(t, err)
		assert.NotNil(t, pos)
		assert.Equal(t, "BUY", pos.Side)
		assert.True(t, decimal.RequireFromString("1.5").Equal(pos.Quantity))
		assert.True(t, decimal.RequireFromString("100").Equal(pos.EntryPrice))
		assert.True(t, decimal.RequireFromString("5").Equal(realized))
	})

	t.Run("fully closes a short and realizes pnl", func(t *testing.T) {
		pos, realized, err := ApplyFillToPosition(&Position{
			Side:       "SELL",
			Quantity:   decimal.RequireFromString("1"),
			EntryPrice: decimal.RequireFromString("100"),
		}, Fill{
			Side:     "BUY",
			Quantity: decimal.RequireFromString("1"),
			Price:    decimal.RequireFromString("90"),
		})

		assert.NoError(t, err)
		assert.Nil(t, pos)
		assert.True(t, decimal.RequireFromString("10").Equal(realized))
	})

	t.Run("flips long to short in one fill", func(t *testing.T) {
		pos, realized, err := ApplyFillToPosition(&Position{
			Side:       "BUY",
			Quantity:   decimal.RequireFromString("1"),
			EntryPrice: decimal.RequireFromString("100"),
		}, Fill{
			Side:     "SELL",
			Quantity: decimal.RequireFromString("3"),
			Price:    decimal.RequireFromString("90"),
		})

		assert.NoError(t, err)
		assert.NotNil(t, pos)
		assert.Equal(t, "SELL", pos.Side)
		assert.True(t, decimal.RequireFromString("2").Equal(pos.Quantity))
		assert.True(t, decimal.RequireFromString("90").Equal(pos.EntryPrice))
		assert.True(t, decimal.RequireFromString("-10").Equal(realized))
	})
}
