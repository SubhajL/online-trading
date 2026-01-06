package storage

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

func TestComputeSignedSlippage(t *testing.T) {
	t.Run("buy above requested is positive cost", func(t *testing.T) {
		got, err := ComputeSignedSlippage(
			"BUY",
			decimal.RequireFromString("100"),
			decimal.RequireFromString("101"),
			decimal.RequireFromString("2"),
		)
		assert.NoError(t, err)
		assert.True(t, decimal.RequireFromString("2").Equal(got))
	})

	t.Run("buy below requested is negative (better than requested)", func(t *testing.T) {
		got, err := ComputeSignedSlippage(
			"BUY",
			decimal.RequireFromString("100"),
			decimal.RequireFromString("99"),
			decimal.RequireFromString("2"),
		)
		assert.NoError(t, err)
		assert.True(t, decimal.RequireFromString("-2").Equal(got))
	})

	t.Run("sell below requested is positive cost", func(t *testing.T) {
		got, err := ComputeSignedSlippage(
			"SELL",
			decimal.RequireFromString("100"),
			decimal.RequireFromString("99"),
			decimal.RequireFromString("2"),
		)
		assert.NoError(t, err)
		assert.True(t, decimal.RequireFromString("2").Equal(got))
	})

	t.Run("sell above requested is negative (better than requested)", func(t *testing.T) {
		got, err := ComputeSignedSlippage(
			"SELL",
			decimal.RequireFromString("100"),
			decimal.RequireFromString("101"),
			decimal.RequireFromString("2"),
		)
		assert.NoError(t, err)
		assert.True(t, decimal.RequireFromString("-2").Equal(got))
	})

	t.Run("zero requested price returns zero without error", func(t *testing.T) {
		got, err := ComputeSignedSlippage(
			"BUY",
			decimal.Zero,
			decimal.RequireFromString("101"),
			decimal.RequireFromString("2"),
		)
		assert.NoError(t, err)
		assert.True(t, decimal.Zero.Equal(got))
	})
}
