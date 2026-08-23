package storage

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
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
	LegID            uuid.UUID
	BracketID        uuid.UUID
	Role             string // ENTRY | TP | SL
	TPIndex          int
	ClientOrderID    string
	ExchangeOrderID  int64
	Price            decimal.Decimal
	StopPrice        decimal.Decimal
	Quantity         decimal.Decimal
	ExecutedQuantity decimal.Decimal
	Status           string
}

type BracketRecord struct {
	BracketID          uuid.UUID
	Venue              string
	IdempotencyKey     string
	RequestHash        string
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

type OpenBracketCursor struct {
	AfterCreatedAt     time.Time
	AfterBracketID     uuid.UUID
	HighWaterCreatedAt time.Time
	HighWaterBracketID uuid.UUID
}

type BracketRepo struct {
	pool *pgxpool.Pool
}

func NewBracketRepo(pool *pgxpool.Pool) *BracketRepo {
	return &BracketRepo{pool: pool}
}

// Reserve atomically claims (venue, idempotency_key). Exactly one
// caller wins the insert; losers get the existing record (with legs) back.
func (r *BracketRepo) Reserve(ctx context.Context, rec BracketRecord) (*BracketRecord, bool, error) {
	if rec.Venue == "" || rec.IdempotencyKey == "" || rec.RequestHash == "" || rec.EntryClientOrderID == "" {
		return nil, false, fmt.Errorf("venue, idempotency key, request hash, and entry client order id are required")
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
				bracket_id, venue, idempotency_key, request_hash, symbol, side, quantity, entry_price,
				stop_loss_price, entry_client_order_id, status, legs_on_fill
			) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
			ON CONFLICT (venue, idempotency_key) DO NOTHING
			RETURNING bracket_id`,
			rec.BracketID, rec.Venue, rec.IdempotencyKey, rec.RequestHash,
			rec.Symbol, rec.Side, rec.Quantity, rec.EntryPrice, rec.StopLossPrice,
			rec.EntryClientOrderID, rec.Status, rec.LegsOnFill,
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

	existing, err := r.getByIdempotencyKey(ctx, rec.Venue, rec.IdempotencyKey)
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

func bracketStatusRank(status string) (int, bool) {
	switch status {
	case BracketStatusReserved:
		return 0, true
	case BracketStatusEntryPlaced:
		return 1, true
	case BracketStatusEntryFilled:
		return 2, true
	case BracketStatusLegsPlaced:
		return 3, true
	default:
		return 0, false
	}
}

// AdvanceBracketStatus applies only monotonic non-terminal bracket transitions.
func (r *BracketRepo) AdvanceBracketStatus(ctx context.Context, bracketID uuid.UUID, status string) (bool, error) {
	rank, ok := bracketStatusRank(status)
	if !ok {
		return false, fmt.Errorf("invalid non-terminal bracket status %q", status)
	}
	tag, err := r.pool.Exec(ctx, `
		UPDATE brackets
		SET status = $2, updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1
		  AND status IN ('RESERVED', 'ENTRY_PLACED', 'ENTRY_FILLED', 'LEGS_PLACED')
		  AND CASE status
				WHEN 'RESERVED' THEN 0
				WHEN 'ENTRY_PLACED' THEN 1
				WHEN 'ENTRY_FILLED' THEN 2
				WHEN 'LEGS_PLACED' THEN 3
			END <= $3`, bracketID, status, rank)
	if err != nil {
		return false, fmt.Errorf("advance bracket status: %w", err)
	}
	return tag.RowsAffected() == 1, nil
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
		    exchange_order_id = COALESCE(NULLIF($4, 0), exchange_order_id),
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

func (r *BracketRepo) UpdateLegExecution(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
	averageFillPrice decimal.Decimal,
) error {
	tag, err := r.pool.Exec(ctx, `
	UPDATE bracket_legs
		SET status = $3,
		    exchange_order_id = COALESCE(NULLIF($4, 0), exchange_order_id),
		    average_fill_price = CASE WHEN $5 > 0 THEN $5 ELSE average_fill_price END,
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2`,
		bracketID, clientOrderID, status, exchangeOrderID, averageFillPrice)
	if err != nil {
		return fmt.Errorf("update bracket leg execution: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("update bracket leg execution: no leg %s in bracket %s", clientOrderID, bracketID)
	}
	return nil
}

// UpdateLegExecutionProgress records monotonic cumulative entry execution.
// Working exchange statuses use PLACED in the durable leg state; the 042
// trigger projects a positive executed quantity as PARTIALLY_FILLED.
func (r *BracketRepo) UpdateLegExecutionProgress(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
	executedQuantity, averageFillPrice decimal.Decimal,
	observedAt time.Time,
) error {
	if executedQuantity.IsNegative() {
		return fmt.Errorf("executed quantity cannot be negative")
	}
	if status == "PARTIALLY_FILLED" {
		status = LegStatusPlaced
	}
	var observedAtArg any
	if !observedAt.IsZero() {
		observedAtArg = observedAt.UTC()
	}
	tag, err := r.pool.Exec(ctx, `
		UPDATE bracket_legs
		SET status = CASE
		        WHEN status = 'FILLED' THEN status
		        WHEN status IN ('CANCELED', 'EXPIRED') AND $3 = 'PLACED' THEN status
		        ELSE $3
		    END,
		    exchange_order_id = COALESCE(NULLIF($4, 0), exchange_order_id),
		    executed_quantity = GREATEST(executed_quantity, $5),
		    average_fill_price = CASE
		        WHEN $6 > 0 AND $5 > executed_quantity THEN $6
		        WHEN $6 > 0 AND $5 = executed_quantity
		             AND $7::timestamptz IS NOT NULL
		             AND (execution_observed_at IS NULL OR $7::timestamptz > execution_observed_at)
		            THEN $6
		        ELSE average_fill_price
		    END,
		    execution_observed_at = CASE
		        WHEN $7::timestamptz IS NULL THEN execution_observed_at
		        WHEN $5 > executed_quantity THEN $7::timestamptz
		        WHEN $5 = executed_quantity AND $6 > 0
		             AND (execution_observed_at IS NULL OR $7::timestamptz > execution_observed_at)
		            THEN $7::timestamptz
		        ELSE execution_observed_at
		    END,
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2 AND $5 <= quantity`,
		bracketID, clientOrderID, status, exchangeOrderID, executedQuantity, averageFillPrice, observedAtArg)
	if err != nil {
		return fmt.Errorf("update bracket leg execution progress: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("update bracket leg execution progress: no leg %s in bracket %s or quantity exceeds leg quantity", clientOrderID, bracketID)
	}
	return nil
}

// UpdateLegQuantity narrows durable protective-leg coverage to the finalized
// entry quantity before an exit claim can be made.
func (r *BracketRepo) UpdateLegQuantity(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID string,
	quantity decimal.Decimal,
) error {
	if quantity.IsNegative() {
		return fmt.Errorf("leg quantity cannot be negative")
	}
	tag, err := r.pool.Exec(ctx, `
		UPDATE bracket_legs
		SET quantity = $3, updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2
		  AND executed_quantity <= $3
		  AND (status IN ($4, $5) OR quantity = $3)`,
		bracketID, clientOrderID, quantity, LegStatusPlanned, LegStatusFailed)
	if err != nil {
		return fmt.Errorf("update bracket leg quantity: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("update bracket leg quantity: no leg %s in bracket %s or quantity below executed quantity", clientOrderID, bracketID)
	}
	return nil
}

// TryClaimEntryFinalization serializes cancel-and-finalize across the event
// stream, spot watcher, and startup reconciler while allowing crash recovery.
func (r *BracketRepo) TryClaimEntryFinalization(ctx context.Context, bracketID, leaseToken uuid.UUID) (bool, error) {
	tag, err := r.pool.Exec(ctx, `
		UPDATE brackets
		SET entry_finalization_lease_token = $2,
		    entry_finalization_lease_until = CURRENT_TIMESTAMP + INTERVAL '5 seconds',
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1
		  AND (entry_finalization_lease_until IS NULL
		       OR entry_finalization_lease_until <= CURRENT_TIMESTAMP
		       OR entry_finalization_lease_token = $2)`,
		bracketID, leaseToken)
	if err != nil {
		return false, fmt.Errorf("claim entry finalization: %w", err)
	}
	return tag.RowsAffected() == 1, nil
}

func (r *BracketRepo) ReleaseEntryFinalization(ctx context.Context, bracketID, leaseToken uuid.UUID) error {
	_, err := r.pool.Exec(ctx, `
		UPDATE brackets
		SET entry_finalization_lease_token = NULL,
		    entry_finalization_lease_until = NULL,
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND entry_finalization_lease_token = $2`,
		bracketID, leaseToken)
	if err != nil {
		return fmt.Errorf("release entry finalization: %w", err)
	}
	return nil
}

// UpdateLegStatusIf transitions a leg only from the expected status. The
// reconciler demotes crash-stale PLACING claims with it so a concurrent
// armer's fresher write can never be overwritten.
func (r *BracketRepo) UpdateLegStatusIf(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID, expected, status string,
	exchangeOrderID int64,
) (bool, error) {
	tag, err := r.pool.Exec(ctx, `
	UPDATE bracket_legs
		SET status = $4,
		    exchange_order_id = COALESCE(NULLIF($5, 0), exchange_order_id),
		    updated_at = CURRENT_TIMESTAMP
		WHERE bracket_id = $1 AND client_order_id = $2 AND status = $3`,
		bracketID, clientOrderID, expected, status, exchangeOrderID)
	if err != nil {
		return false, fmt.Errorf("guarded update bracket leg status: %w", err)
	}
	return tag.RowsAffected() == 1, nil
}

// InsertLeg adds a leg to an existing bracket — used for stop slices derived
// at arm time beyond the single reserved SL leg.
func (r *BracketRepo) InsertLeg(ctx context.Context, leg BracketLegRecord) error {
	if leg.BracketID == uuid.Nil || leg.ClientOrderID == "" {
		return fmt.Errorf("bracket id and client order id are required")
	}
	legID := leg.LegID
	if legID == uuid.Nil {
		legID = uuid.New()
	}
	status := leg.Status
	if status == "" {
		status = LegStatusPlanned
	}
	_, err := r.pool.Exec(ctx, `
		INSERT INTO bracket_legs (
			leg_id, bracket_id, role, tp_index, client_order_id,
			exchange_order_id, price, stop_price, quantity, status
		) VALUES ($1,$2,$3,$4,$5,NULLIF($6,0),$7,$8,$9,$10)
		ON CONFLICT (bracket_id, client_order_id) DO NOTHING`,
		legID, leg.BracketID, leg.Role, leg.TPIndex, leg.ClientOrderID,
		leg.ExchangeOrderID, leg.Price, leg.StopPrice, leg.Quantity, status)
	if err != nil {
		return fmt.Errorf("insert bracket leg: %w", err)
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
		SELECT bracket_id, venue, idempotency_key, request_hash, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets WHERE bracket_id = $1`, bracketID,
	).Scan(
		&rec.BracketID, &rec.Venue, &rec.IdempotencyKey, &rec.RequestHash,
		&rec.Symbol, &rec.Side, &rec.Quantity,
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

// LoadOpenBracketPage returns a bounded, stable page of every non-terminal
// bracket at or before the pass high-water mark.
func (r *BracketRepo) LoadOpenBracketPage(
	ctx context.Context,
	cursor *OpenBracketCursor,
	pageSize int,
) ([]BracketRecord, *OpenBracketCursor, error) {
	if pageSize <= 0 {
		return nil, nil, fmt.Errorf("page size must be greater than zero")
	}

	afterCreatedAt := time.Time{}
	afterBracketID := uuid.Nil
	var highWaterCreatedAt time.Time
	var highWaterBracketID uuid.UUID
	if cursor == nil {
		err := r.pool.QueryRow(ctx, `
			SELECT created_at, bracket_id
			FROM brackets
			WHERE status NOT IN ('CLOSED', 'FAILED')
			ORDER BY created_at DESC, bracket_id DESC
			LIMIT 1`).Scan(&highWaterCreatedAt, &highWaterBracketID)
		if errors.Is(err, pgx.ErrNoRows) {
			return []BracketRecord{}, nil, nil
		}
		if err != nil {
			return nil, nil, fmt.Errorf("load open bracket high-water mark: %w", err)
		}
	} else {
		afterCreatedAt = cursor.AfterCreatedAt
		afterBracketID = cursor.AfterBracketID
		highWaterCreatedAt = cursor.HighWaterCreatedAt
		highWaterBracketID = cursor.HighWaterBracketID
	}

	rows, err := r.pool.Query(ctx, `
		SELECT bracket_id, venue, idempotency_key, request_hash, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets
		WHERE status NOT IN ('CLOSED', 'FAILED')
		  AND (created_at, bracket_id) > ($1, $2)
		  AND (created_at, bracket_id) <= ($3, $4)
		ORDER BY created_at ASC, bracket_id ASC
		LIMIT $5`, afterCreatedAt, afterBracketID, highWaterCreatedAt, highWaterBracketID, pageSize+1)
	if err != nil {
		return nil, nil, fmt.Errorf("load open bracket page: %w", err)
	}
	defer rows.Close()

	records := make([]BracketRecord, 0, pageSize+1)
	for rows.Next() {
		var rec BracketRecord
		if err := rows.Scan(
			&rec.BracketID, &rec.Venue, &rec.IdempotencyKey, &rec.RequestHash,
			&rec.Symbol, &rec.Side, &rec.Quantity,
			&rec.EntryPrice, &rec.StopLossPrice, &rec.EntryClientOrderID,
			&rec.Status, &rec.LegsOnFill, &rec.CreatedAt,
		); err != nil {
			return nil, nil, fmt.Errorf("scan open bracket page: %w", err)
		}
		records = append(records, rec)
	}
	if err := rows.Err(); err != nil {
		return nil, nil, fmt.Errorf("read open bracket page: %w", err)
	}
	rows.Close()

	var next *OpenBracketCursor
	if len(records) > pageSize {
		records = records[:pageSize]
		last := records[len(records)-1]
		next = &OpenBracketCursor{
			AfterCreatedAt:     last.CreatedAt,
			AfterBracketID:     last.BracketID,
			HighWaterCreatedAt: highWaterCreatedAt,
			HighWaterBracketID: highWaterBracketID,
		}
	}
	for i := range records {
		legs, err := r.loadLegs(ctx, records[i].BracketID)
		if err != nil {
			return nil, nil, err
		}
		records[i].Legs = legs
	}
	return records, next, nil
}

func (r *BracketRepo) getByEntryClientOrderID(ctx context.Context, venue, entryClientOrderID string) (*BracketRecord, error) {
	var rec BracketRecord
	err := r.pool.QueryRow(ctx, `
		SELECT bracket_id, venue, idempotency_key, request_hash, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets
		WHERE venue = $1 AND entry_client_order_id = $2`,
		venue, entryClientOrderID,
	).Scan(
		&rec.BracketID, &rec.Venue, &rec.IdempotencyKey, &rec.RequestHash,
		&rec.Symbol, &rec.Side, &rec.Quantity,
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

func (r *BracketRepo) getByIdempotencyKey(ctx context.Context, venue, idempotencyKey string) (*BracketRecord, error) {
	var rec BracketRecord
	err := r.pool.QueryRow(ctx, `
		SELECT bracket_id, venue, idempotency_key, request_hash, symbol, side, quantity, entry_price,
		       stop_loss_price, entry_client_order_id, status, legs_on_fill, created_at
		FROM brackets
		WHERE venue = $1 AND idempotency_key = $2`, venue, idempotencyKey,
	).Scan(
		&rec.BracketID, &rec.Venue, &rec.IdempotencyKey, &rec.RequestHash,
		&rec.Symbol, &rec.Side, &rec.Quantity, &rec.EntryPrice,
		&rec.StopLossPrice, &rec.EntryClientOrderID,
		&rec.Status, &rec.LegsOnFill, &rec.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("load bracket by idempotency key: %w", err)
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
		       COALESCE(stop_price, 0), quantity, COALESCE(executed_quantity, 0), status
		FROM bracket_legs
		WHERE bracket_id = $1
		ORDER BY role, tp_index`,
		bracketID)
	if err != nil {
		var pgErr *pgconn.PgError
		if !errors.As(err, &pgErr) || pgErr.Code != "42703" {
			return nil, fmt.Errorf("load bracket legs: %w", err)
		}
		return r.loadLegacyLegs(ctx, bracketID)
	}
	defer rows.Close()

	var legs []BracketLegRecord
	for rows.Next() {
		var leg BracketLegRecord
		if err := rows.Scan(
			&leg.LegID, &leg.BracketID, &leg.Role, &leg.TPIndex, &leg.ClientOrderID,
			&leg.ExchangeOrderID, &leg.Price, &leg.StopPrice, &leg.Quantity,
			&leg.ExecutedQuantity, &leg.Status,
		); err != nil {
			return nil, fmt.Errorf("scan bracket leg: %w", err)
		}
		legs = append(legs, leg)
	}
	return legs, rows.Err()
}

func (r *BracketRepo) loadLegacyLegs(ctx context.Context, bracketID uuid.UUID) ([]BracketLegRecord, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT leg_id, bracket_id, role, tp_index, client_order_id,
		       COALESCE(exchange_order_id, 0), COALESCE(price, 0),
		       COALESCE(stop_price, 0), quantity, status
		FROM bracket_legs
		WHERE bracket_id = $1
		ORDER BY role, tp_index`, bracketID)
	if err != nil {
		return nil, fmt.Errorf("load legacy bracket legs: %w", err)
	}
	defer rows.Close()

	var legs []BracketLegRecord
	for rows.Next() {
		var leg BracketLegRecord
		if err := rows.Scan(
			&leg.LegID, &leg.BracketID, &leg.Role, &leg.TPIndex, &leg.ClientOrderID,
			&leg.ExchangeOrderID, &leg.Price, &leg.StopPrice, &leg.Quantity, &leg.Status,
		); err != nil {
			return nil, fmt.Errorf("scan legacy bracket leg: %w", err)
		}
		legs = append(legs, leg)
	}
	return legs, rows.Err()
}
