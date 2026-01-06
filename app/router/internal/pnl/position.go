package pnl

import (
	"fmt"

	"github.com/shopspring/decimal"
)

type Position struct {
	Side       string
	Quantity   decimal.Decimal
	EntryPrice decimal.Decimal
}

type Fill struct {
	Side     string
	Quantity decimal.Decimal
	Price    decimal.Decimal
}

func ApplyFillToPosition(pos *Position, fill Fill) (*Position, decimal.Decimal, error) {
	if fill.Side != "BUY" && fill.Side != "SELL" {
		return nil, decimal.Zero, fmt.Errorf("invalid fill side: %s", fill.Side)
	}
	if fill.Quantity.LessThanOrEqual(decimal.Zero) {
		return nil, decimal.Zero, fmt.Errorf("fill quantity must be positive")
	}
	if fill.Price.LessThanOrEqual(decimal.Zero) {
		return nil, decimal.Zero, fmt.Errorf("fill price must be positive")
	}

	if pos == nil || pos.Quantity.IsZero() {
		return &Position{
			Side:       fill.Side,
			Quantity:   fill.Quantity,
			EntryPrice: fill.Price,
		}, decimal.Zero, nil
	}

	if pos.Side != "BUY" && pos.Side != "SELL" {
		return nil, decimal.Zero, fmt.Errorf("invalid position side: %s", pos.Side)
	}
	if pos.Quantity.LessThanOrEqual(decimal.Zero) {
		return nil, decimal.Zero, fmt.Errorf("position quantity must be positive")
	}
	if pos.EntryPrice.LessThanOrEqual(decimal.Zero) {
		return nil, decimal.Zero, fmt.Errorf("position entry price must be positive")
	}

	if pos.Side == fill.Side {
		newQty := pos.Quantity.Add(fill.Quantity)
		weightedNotional := pos.EntryPrice.Mul(pos.Quantity).Add(fill.Price.Mul(fill.Quantity))
		newEntry := weightedNotional.Div(newQty)
		return &Position{
			Side:       pos.Side,
			Quantity:   newQty,
			EntryPrice: newEntry,
		}, decimal.Zero, nil
	}

	closingQty := decimal.Min(pos.Quantity, fill.Quantity)
	remainingPosQty := pos.Quantity.Sub(closingQty)
	remainingFillQty := fill.Quantity.Sub(closingQty)

	sign := decimal.NewFromInt(1)
	if pos.Side == "SELL" {
		sign = decimal.NewFromInt(-1)
	}
	realized := fill.Price.Sub(pos.EntryPrice).Mul(closingQty).Mul(sign)

	if remainingPosQty.IsZero() && remainingFillQty.IsZero() {
		return nil, realized, nil
	}

	if remainingPosQty.GreaterThan(decimal.Zero) {
		return &Position{
			Side:       pos.Side,
			Quantity:   remainingPosQty,
			EntryPrice: pos.EntryPrice,
		}, realized, nil
	}

	return &Position{
		Side:       fill.Side,
		Quantity:   remainingFillQty,
		EntryPrice: fill.Price,
	}, realized, nil
}
