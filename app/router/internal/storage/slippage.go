package storage

import (
	"fmt"

	"github.com/shopspring/decimal"
)

func ComputeSignedSlippage(
	side string,
	requestedPrice decimal.Decimal,
	fillPrice decimal.Decimal,
	quantity decimal.Decimal,
) (decimal.Decimal, error) {
	if side != "BUY" && side != "SELL" {
		return decimal.Zero, fmt.Errorf("invalid side: %s", side)
	}
	if quantity.LessThanOrEqual(decimal.Zero) {
		return decimal.Zero, fmt.Errorf("quantity must be positive")
	}
	if fillPrice.LessThanOrEqual(decimal.Zero) {
		return decimal.Zero, fmt.Errorf("fill price must be positive")
	}
	if requestedPrice.IsZero() {
		return decimal.Zero, nil
	}
	if requestedPrice.LessThan(decimal.Zero) {
		return decimal.Zero, fmt.Errorf("requested price must be non-negative")
	}

	if side == "BUY" {
		return fillPrice.Sub(requestedPrice).Mul(quantity), nil
	}
	return requestedPrice.Sub(fillPrice).Mul(quantity), nil
}
