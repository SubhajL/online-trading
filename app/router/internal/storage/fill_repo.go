package storage

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
)

type FillRecord struct {
	Venue           string
	Symbol          string
	TradeID         int64
	ClientOrderID   string
	Side            string
	Price           decimal.Decimal
	Quantity        decimal.Decimal
	Commission      decimal.Decimal
	CommissionAsset string
	RealizedPnL     decimal.Decimal
	Slippage        decimal.Decimal
}

type FillRepo struct{}

func NewFillRepo() *FillRepo {
	return &FillRepo{}
}

func (r *FillRepo) InsertFillIfNew(ctx context.Context, tx pgx.Tx, fill FillRecord) (bool, error) {
	if fill.Venue == "" {
		return false, fmt.Errorf("venue is required")
	}
	if fill.Symbol == "" {
		return false, fmt.Errorf("symbol is required")
	}
	if fill.ClientOrderID == "" {
		return false, fmt.Errorf("client_order_id is required")
	}
	if fill.TradeID <= 0 {
		return false, fmt.Errorf("trade_id must be positive")
	}
	if fill.Side != "BUY" && fill.Side != "SELL" {
		return false, fmt.Errorf("invalid side: %s", fill.Side)
	}
	if fill.Price.LessThanOrEqual(decimal.Zero) {
		return false, fmt.Errorf("price must be positive")
	}
	if fill.Quantity.LessThanOrEqual(decimal.Zero) {
		return false, fmt.Errorf("quantity must be positive")
	}

	cmd, err := tx.Exec(
		ctx,
		`INSERT INTO fills (
			venue, symbol, trade_id, client_order_id, side, price, quantity,
			commission, commission_asset, realized_pnl, slippage
		) VALUES (
			$1,$2,$3,$4,$5,$6,$7,
			$8, NULLIF($9,''), NULLIF($10,0), $11
		)
		ON CONFLICT (venue, symbol, trade_id) DO NOTHING`,
		fill.Venue,
		fill.Symbol,
		fill.TradeID,
		fill.ClientOrderID,
		fill.Side,
		fill.Price,
		fill.Quantity,
		fill.Commission,
		fill.CommissionAsset,
		fill.RealizedPnL,
		fill.Slippage,
	)
	if err != nil {
		return false, fmt.Errorf("insert fill: %w", err)
	}

	return cmd.RowsAffected() == 1, nil
}
