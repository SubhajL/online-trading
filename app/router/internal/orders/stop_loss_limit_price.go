package orders

import "github.com/shopspring/decimal"

// stopLossLimitPriceForSpotBracket computes a STOP_LOSS_LIMIT limit price and rounds it to tick size
// in a direction that keeps the limit "worse" than the stop price (more likely to fill) while
// preserving the required relation between stop and limit:
// - Entry side BUY (stop order is SELL): limit must be below stop -> round down
// - Entry side SELL (stop order is BUY): limit must be above stop -> round up
func stopLossLimitPriceForSpotBracket(
	stopLossPrice decimal.Decimal,
	entrySide string,
	tickSize decimal.Decimal,
) decimal.Decimal {
	var raw decimal.Decimal
	if entrySide == "BUY" {
		raw = stopLossPrice.Mul(decimal.RequireFromString("0.995"))
	} else {
		raw = stopLossPrice.Mul(decimal.RequireFromString("1.005"))
	}

	if !tickSize.IsPositive() {
		return raw
	}

	q := raw.Div(tickSize)
	var rounded decimal.Decimal
	if entrySide == "BUY" {
		rounded = q.Floor().Mul(tickSize)
		if !rounded.LessThan(stopLossPrice) {
			rounded = rounded.Sub(tickSize)
		}
	} else {
		rounded = q.Ceil().Mul(tickSize)
		if !rounded.GreaterThan(stopLossPrice) {
			rounded = rounded.Add(tickSize)
		}
	}

	return rounded
}
