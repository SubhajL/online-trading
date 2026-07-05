package storage

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"
)

// Bracket lifecycle statuses.
const (
	BracketStatusReserved    = "RESERVED"
	BracketStatusEntryPlaced = "ENTRY_PLACED"
	BracketStatusEntryFilled = "ENTRY_FILLED"
	BracketStatusLegsPlaced  = "LEGS_PLACED"
	BracketStatusClosed      = "CLOSED"
	BracketStatusFailed      = "FAILED"
)

// Bracket leg statuses.
const (
	LegStatusPlanned  = "PLANNED"
	LegStatusPlacing  = "PLACING"
	LegStatusPlaced   = "PLACED"
	LegStatusFilled   = "FILLED"
	LegStatusCanceled = "CANCELED"
	LegStatusExpired  = "EXPIRED"
	LegStatusFailed   = "FAILED"
)

type BracketLegRecord struct {
	LegID           uuid.UUID
	BracketID       uuid.UUID
	Role            string // ENTRY | TP | SL
	TPIndex         int
	ClientOrderID   string
	ExchangeOrderID int64
	Price           decimal.Decimal
	StopPrice       decimal.Decimal
	Quantity        decimal.Decimal
	Status          string
}

type BracketRecord struct {
	BracketID          uuid.UUID
	Venue              string
	Symbol             string
	Side               string
	Quantity           decimal.Decimal
	EntryPrice         decimal.Decimal
	StopLossPrice      decimal.Decimal
	EntryClientOrderID string
	Status             string
	LegsOnFill         bool
	CreatedAt          time.Time
	Legs               []BracketLegRecord
}

type BracketRepo struct {
	pool *pgxpool.Pool
}

func NewBracketRepo(pool *pgxpool.Pool) *BracketRepo {
	return &BracketRepo{pool: pool}
}

// Reserve atomically claims (venue, entry_client_order_id). Exactly one
// caller wins the insert; losers get the existing record (with legs) back.
func (r *BracketRepo) Reserve(ctx context.Context, rec BracketRecord) (*BracketRecord, bool, error) {
	if rec.Venue == "" || rec.EntryClientOrderID == "" {
		return nil, false, fmt.Errorf("venue and entry client order id are required")
	}
	if rec.BracketID == uuid.Nil {
		rec.BracketID = uuid.New()
	}
	if rec.Status == "" {
		rec.Status = BracketStatusReserved
	}

	var inserted bool
	err := RunInTx(ctx, r.pool, func(tx pgx.Tx) error {
		var insertedID uuid.UUID
		err := tx.QueryRow(ctx, `
			INSERT INTO brackets (
				bracket_id, venue, symbol, side, quantity, entry_price,
				stop_loss_price, entry_client_order_id, status, legs_on_fill
			) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
			ON CONFLICT (venue, entry_client_order_id) DO NOTHING
			RETURNING bracket_id`,
			rec.BracketID, rec.Venue, rec.Symbol, rec.Side, rec.Quantity,
			rec.EntryPrice, rec.StopLossPrice, rec.EntryClientOrderID,
			rec.Status, rec.LegsOnFill,
		).Scan(&insertedID)
		if errors.Is(err, pgx.ErrNoRows) {
			inserted = false
			return nil
		}
		if err != nil {
			return fmt.Errorf("insert bracket: %w", err)
		}
		inserted = true

		for _, leg := range rec.Legs {
			legID := leg.LegID
			if legID == uuid.Nil {
				legID = uuid.New()
			}
			status := leg.Status
			if status == "" {
				status = LegStatusPlanned
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO bracket_legs (
					leg_id, bracket_id, role, tp_index, client_order_id,
					price, stop_price, quantity, status
				) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
				legID, rec.BracketID, leg.Role, leg.TPIndex, leg.ClientOrderID,
				leg.Price, leg.StopPrice, leg.Quantity, status,
			); err != nil {
				return fmt.Errorf("insert bracket leg %s: %w", leg.ClientOrderID, err)
			}
		}
		return nil
	})
	if err != nil {
		return nil, false, err
	}

	if inserted {
		stored := rec
		return &stored, true, nil
	}

	existing, err := r.getByEntryClientOrderID(ctx, rec.Venue, rec.EntryClientOrderID)
	if err != nil {
		return nil, false, err
	}
	return existing, false, nil
}

func (r *BracketRepo) UpdateBracketStatus(ctx context.Context, bracketID uuid.UUID, status string) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE brackets SET status = $2, updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1`, bracketID, status)
	if err != nil {
		return fmt.Errorf("update bracket status: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("update bracket status: no bracket %s", bracketID)
	}
	return nil
}

func (r *BracketRepo) UpdateLegStatus(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE bracket_legs
		SET status = $3,
		    exchange_order_id = NULLIF($4, 0),
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2`,
		bracketID, clientOrderID, status, exchangeOrderID)
	if err != nil {
		return fmt.Errorf("update bracket leg status: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("update bracket leg status: no leg %s in bracket %s", clientOrderID, bracketID)
	}
	return nil
}

// TryMarkLegPlacing claims a leg for placement (compare-and-set to PLACING).
// Exactly one caller wins per leg, making duplicate fill events unable to
// double-place protective legs. FAILED legs are re-claimable: a transient
// POST failure must not permanently strand a position unprotected, and
// #193's submit resolution dedupes any raced re-POST against the exchange.
func (r *BracketRepo) TryMarkLegPlacing(ctx context.Context, bracketID uuid.UUID, clientOrderID string) (bool, error) {
	tag, err := r.pool.Exec(ctx, `
		UPDATE bracket_legs
		SET status = $3, updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2 AND status IN ($4, $5)`,
		bracketID, clientOrderID, LegStatusPlacing, LegStatusPlanned, LegStatusFailed)
	if err != nil {
		return false, fmt.Errorf("mark bracket leg placing: %w", err)
	}
	return tag.RowsAffected() == 1, nil
}

// UpdateBracketStatusIf transitions a bracket's status only from an expected
// prior state; reports whether the transition applied.
func (r *BracketRepo) UpdateBracketStatusIf(ctx context.Context, bracketID uuid.UUID, expected, status string) (bool, error) {
	tag, err := r.pool.Exec(ctx, `
		UPDATE brackets SET status = $3, updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND status = $2`,
		bracketID, expected, status)
	if err != nil {
		return false, fmt.Errorf("conditional bracket status update: %w", err)
	}
	return tag.RowsAffected() == 1, nil
}

// GetByEntryClientOrderID loads a bracket (with legs) by its entry client
// order id; returns nil when none exists.
func (r *BracketRepo) GetByEntryClientOrderID(ctx context.Context, venue, entryClientOrderID string) (*BracketRecord, error) {
	rec, err := r.getByEntryClientOrderID(ctx, venue, entryClientOrderID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, err
	}
	return rec, nil
}

// GetByLegClientOrderID loads the bracket (with legs) owning any leg with the
// given client order id; returns nil when none exists.
func (r *BracketRepo) GetByLegClientOrderID(ctx context.Context, venue, clientOrderID string) (*BracketRecord, error) {
	var bracketID uuid.UUID
	err := r.pool.QueryRow(ctx, `
		SELECT l.bracket_id
		FROM bracket_legs l
		JOIN brackets b ON b.bracket_id = l.bracket_id
		WHERE b.venue = $1 AND l.client_order_id = $2`,
		venue, clientOrderID,
	).Scan(&bracketID)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("load bracket by leg client order id: %w", err)
	}

	var rec BracketRecord
	err = r.pool.QueryRow(ctx, `
		SELECT bracket_id, venue, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets WHERE bracket_id = $1`, bracketID,
	).Scan(
		&rec.BracketID, &rec.Venue, &rec.Symbol, &rec.Side, &rec.Quantity,
		&rec.EntryPrice, &rec.StopLossPrice, &rec.EntryClientOrderID,
		&rec.Status, &rec.LegsOnFill, &rec.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("load bracket by id: %w", err)
	}
	legs, err := r.loadLegs(ctx, rec.BracketID)
	if err != nil {
		return nil, err
	}
	rec.Legs = legs
	return &rec, nil
}

// LoadOpenBrackets returns non-terminal brackets created within lookback,
// legs included — the work list for startup reconciliation.
func (r *BracketRepo) LoadOpenBrackets(ctx context.Context, lookback time.Duration) ([]BracketRecord, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT bracket_id, venue, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets
		WHERE status NOT IN ('CLOSED', 'FAILED')
		  AND created_at >= CURRENT_TIMESTAMP - $1::interval`,
		fmt.Sprintf("%d seconds", int(lookback.Seconds())))
	if err != nil {
		return nil, fmt.Errorf("load open brackets: %w", err)
	}
	defer rows.Close()

	var records []BracketRecord
	for rows.Next() {
		var rec BracketRecord
		if err := rows.Scan(
			&rec.BracketID, &rec.Venue, &rec.Symbol, &rec.Side, &rec.Quantity,
			&rec.EntryPrice, &rec.StopLossPrice, &rec.EntryClientOrderID,
			&rec.Status, &rec.LegsOnFill, &rec.CreatedAt,
		); err != nil {
			return nil, fmt.Errorf("scan bracket: %w", err)
		}
		records = append(records, rec)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	for i := range records {
		legs, err := r.loadLegs(ctx, records[i].BracketID)
		if err != nil {
			return nil, err
		}
		records[i].Legs = legs
	}
	return records, nil
}

func (r *BracketRepo) getByEntryClientOrderID(ctx context.Context, venue, entryClientOrderID string) (*BracketRecord, error) {
	var rec BracketRecord
	err := r.pool.QueryRow(ctx, `
		SELECT bracket_id, venue, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets
		WHERE venue = $1 AND entry_client_order_id = $2`,
		venue, entryClientOrderID,
	).Scan(
		&rec.BracketID, &rec.Venue, &rec.Symbol, &rec.Side, &rec.Quantity,
		&rec.EntryPrice, &rec.StopLossPrice, &rec.EntryClientOrderID,
		&rec.Status, &rec.LegsOnFill, &rec.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("load bracket by entry client order id: %w", err)
	}

	legs, err := r.loadLegs(ctx, rec.BracketID)
	if err != nil {
		return nil, err
	}
	rec.Legs = legs
	return &rec, nil
}

func (r *BracketRepo) loadLegs(ctx context.Context, bracketID uuid.UUID) ([]BracketLegRecord, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT leg_id, bracket_id, role, tp_index, client_order_id,
		       COALESCE(exchange_order_id, 0), COALESCE(price, 0),
		       COALESCE(stop_price, 0), quantity, status
		FROM bracket_legs
		WHERE bracket_id = $1
		ORDER BY role, tp_index`,
		bracketID)
	if err != nil {
		return nil, fmt.Errorf("load bracket legs: %w", err)
	}
	defer rows.Close()

	var legs []BracketLegRecord
	for rows.Next() {
		var leg BracketLegRecord
		if err := rows.Scan(
			&leg.LegID, &leg.BracketID, &leg.Role, &leg.TPIndex, &leg.ClientOrderID,
			&leg.ExchangeOrderID, &leg.Price, &leg.StopPrice, &leg.Quantity, &leg.Status,
		); err != nil {
			return nil, fmt.Errorf("scan bracket leg: %w", err)
		}
		legs = append(legs, leg)
	}
	return legs, rows.Err()
}
