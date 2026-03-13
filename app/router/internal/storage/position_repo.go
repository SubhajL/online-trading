package storage

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
)

type ActivePosition struct {
	PositionID   uuid.UUID
	Venue        string
	Symbol       string
	Side         string
	Size         decimal.Decimal
	EntryPrice   decimal.Decimal
	EntryOrderID string

	CurrentPrice  decimal.Decimal
	UnrealizedPnL decimal.Decimal
	RealizedPnL   decimal.Decimal

	CommissionPaid decimal.Decimal
	FundingPaid    decimal.Decimal
	SlippagePaid   decimal.Decimal

	OpenedAt  time.Time
	UpdatedAt time.Time
}

type ActivePositionUpsert struct {
	Venue        string
	Symbol       string
	Side         string
	Size         decimal.Decimal
	EntryPrice   decimal.Decimal
	EntryOrderID string

	CurrentPrice decimal.Decimal

	RealizedPnL decimal.Decimal

	CommissionPaid decimal.Decimal
	FundingPaid    decimal.Decimal
	SlippagePaid   decimal.Decimal

	OpenedAt  time.Time
	UpdatedAt time.Time
}

type PositionClose struct {
	ClosedAt       time.Time
	CurrentPrice   decimal.Decimal
	RealizedPnL    decimal.Decimal
	CommissionPaid decimal.Decimal
	FundingPaid    decimal.Decimal
	SlippagePaid   decimal.Decimal
}

type PositionRepo struct{}

func NewPositionRepo() *PositionRepo {
	return &PositionRepo{}
}

func (r *PositionRepo) GetActive(
	ctx context.Context,
	tx pgx.Tx,
	venue string,
	symbol string,
) (*ActivePosition, bool, error) {
	if venue == "" {
		return nil, false, fmt.Errorf("venue is required")
	}
	if symbol == "" {
		return nil, false, fmt.Errorf("symbol is required")
	}

	row := tx.QueryRow(
		ctx,
		`SELECT position_id, venue, symbol, side, size, entry_price,
		        COALESCE(entry_order_id::text, ''),
		        current_price, unrealized_pnl, realized_pnl,
		        COALESCE(commission_paid, 0), COALESCE(funding_paid, 0), COALESCE(slippage_paid, 0),
		        opened_at, updated_at
		   FROM positions
		  WHERE venue = $1 AND symbol = $2 AND is_active = TRUE
		  LIMIT 1`,
		venue,
		symbol,
	)

	var pos ActivePosition
	if err := row.Scan(
		&pos.PositionID,
		&pos.Venue,
		&pos.Symbol,
		&pos.Side,
		&pos.Size,
		&pos.EntryPrice,
		&pos.EntryOrderID,
		&pos.CurrentPrice,
		&pos.UnrealizedPnL,
		&pos.RealizedPnL,
		&pos.CommissionPaid,
		&pos.FundingPaid,
		&pos.SlippagePaid,
		&pos.OpenedAt,
		&pos.UpdatedAt,
	); err != nil {
		if err == pgx.ErrNoRows {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("select active position: %w", err)
	}

	return &pos, true, nil
}

func (r *PositionRepo) UpsertActive(ctx context.Context, tx pgx.Tx, upsert ActivePositionUpsert) error {
	if upsert.Venue == "" {
		return fmt.Errorf("venue is required")
	}
	if upsert.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if upsert.Side != "BUY" && upsert.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", upsert.Side)
	}
	if upsert.Size.LessThan(decimal.Zero) {
		return fmt.Errorf("size must be non-negative")
	}
	if upsert.EntryPrice.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("entry_price must be positive")
	}
	if upsert.CurrentPrice.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("current_price must be positive")
	}

	unrealizedPnL := _unrealizedPnL(upsert.Side, upsert.EntryPrice, upsert.CurrentPrice, upsert.Size)

	// Use INSERT ... ON CONFLICT for atomic upsert (concurrency-safe).
	// The partial unique index uq_positions_active on (venue, symbol) WHERE is_active = TRUE
	// ensures only one active position per venue/symbol.
	_, err := tx.Exec(
		ctx,
		`INSERT INTO positions (
			venue, symbol, side, size, entry_price, current_price, unrealized_pnl, realized_pnl,
			margin_used, leverage, opened_at, updated_at, is_active,
			entry_order_id, commission_paid, funding_paid, slippage_paid
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8,
			0, 1, $9, $10, TRUE,
			NULLIF($11, '')::uuid, $12, $13, $14
		)
		ON CONFLICT (venue, symbol) WHERE is_active = TRUE
		DO UPDATE SET
			side = EXCLUDED.side,
			size = EXCLUDED.size,
			entry_price = EXCLUDED.entry_price,
			current_price = EXCLUDED.current_price,
			unrealized_pnl = EXCLUDED.unrealized_pnl,
			realized_pnl = EXCLUDED.realized_pnl,
			opened_at = EXCLUDED.opened_at,
			entry_order_id = EXCLUDED.entry_order_id,
			commission_paid = EXCLUDED.commission_paid,
			funding_paid = EXCLUDED.funding_paid,
			slippage_paid = EXCLUDED.slippage_paid,
			updated_at = EXCLUDED.updated_at`,
		upsert.Venue,
		upsert.Symbol,
		upsert.Side,
		upsert.Size,
		upsert.EntryPrice,
		upsert.CurrentPrice,
		unrealizedPnL,
		upsert.RealizedPnL,
		upsert.OpenedAt,
		upsert.UpdatedAt,
		upsert.EntryOrderID,
		upsert.CommissionPaid,
		upsert.FundingPaid,
		upsert.SlippagePaid,
	)
	if err != nil {
		return fmt.Errorf("upsert active position: %w", err)
	}
	return nil
}

func (r *PositionRepo) CloseActive(
	ctx context.Context,
	tx pgx.Tx,
	venue string,
	symbol string,
	close PositionClose,
) error {
	if venue == "" {
		return fmt.Errorf("venue is required")
	}
	if symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if close.CurrentPrice.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("current_price must be positive")
	}

	_, err := tx.Exec(
		ctx,
		`UPDATE positions
		    SET current_price = $1,
		        unrealized_pnl = 0,
		        realized_pnl = COALESCE(realized_pnl, 0) + $2,
		        commission_paid = COALESCE(commission_paid, 0) + $3,
		        funding_paid = COALESCE(funding_paid, 0) + $4,
		        slippage_paid = COALESCE(slippage_paid, 0) + $5,
		        size = 0,
		        updated_at = $6,
		        closed_at = $7,
		        is_active = FALSE
		  WHERE venue = $8 AND symbol = $9 AND is_active = TRUE`,
		close.CurrentPrice,
		close.RealizedPnL,
		close.CommissionPaid,
		close.FundingPaid,
		close.SlippagePaid,
		close.ClosedAt,
		close.ClosedAt,
		venue,
		symbol,
	)
	if err != nil {
		return fmt.Errorf("close active position: %w", err)
	}
	return nil
}

func _unrealizedPnL(
	side string,
	entryPrice decimal.Decimal,
	currentPrice decimal.Decimal,
	size decimal.Decimal,
) decimal.Decimal {
	sign := decimal.NewFromInt(1)
	if side == "SELL" {
		sign = decimal.NewFromInt(-1)
	}
	return currentPrice.Sub(entryPrice).Mul(size).Mul(sign)
}
