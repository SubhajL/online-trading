package orders

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
)

func TestStopLossLimitPriceForSpotBracket(t *testing.T) {
	t.Run("BUY rounds stop-loss limit down to tick", func(t *testing.T) {
		stop := decimal.RequireFromString("100.01")
		tick := decimal.RequireFromString("0.1")

		limit := stopLossLimitPriceForSpotBracket(stop, "BUY", tick)

		// 100.01 * 0.995 = 99.50995 -> floor to 99.5
		assert.Equal(t, decimal.RequireFromString("99.5"), limit)
		assert.True(t, limit.LessThan(stop))
	})

	t.Run("SELL rounds stop-loss limit up to tick", func(t *testing.T) {
		stop := decimal.RequireFromString("100.01")
		tick := decimal.RequireFromString("0.1")

		limit := stopLossLimitPriceForSpotBracket(stop, "SELL", tick)

		// 100.01 * 1.005 = 100.51005 -> ceil to 100.6
		assert.Equal(t, decimal.RequireFromString("100.6"), limit)
		assert.True(t, limit.GreaterThan(stop))
	})

	t.Run("zero tick size returns unrounded computed value", func(t *testing.T) {
		stop := decimal.RequireFromString("100")
		tick := decimal.Zero

		limit := stopLossLimitPriceForSpotBracket(stop, "BUY", tick)
		assert.True(t, limit.Equal(decimal.RequireFromString("99.5")))
	})
}
