package storage

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

const ExecutionControlAdvisoryKey int64 = 4996822828266939461

const (
	ExecutionStateRunning = "RUNNING"
	ExecutionStateHalted  = "HALTED"
)

type ExecutionControlRecord struct {
	Scope          string    `json:"scope"`
	State          string    `json:"state"`
	Generation     int64     `json:"generation"`
	Reason         string    `json:"reason"`
	RequestedBy    string    `json:"requested_by"`
	IdempotencyKey string    `json:"idempotency_key"`
	RequestedAt    time.Time `json:"requested_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

type ExecutionControlRequest struct {
	Reason         string `json:"reason"`
	RequestedBy    string `json:"requested_by"`
	IdempotencyKey string `json:"idempotency_key"`
	ConfirmSafe    bool   `json:"confirm_safe,omitempty"`
}

type PostgresExecutionControl struct {
	pool *pgxpool.Pool
}

type ResumeSafetyError struct{ Cause error }

func (e *ResumeSafetyError) Error() string {
	return fmt.Sprintf("execution is not safe to resume: %v", e.Cause)
}
func (e *ResumeSafetyError) Unwrap() error { return e.Cause }

func NewPostgresExecutionControl(pool *pgxpool.Pool) *PostgresExecutionControl {
	return &PostgresExecutionControl{pool: pool}
}

func (c *PostgresExecutionControl) AcquirePlacement(
	ctx context.Context,
) (string, func() error, error) {
	return c.acquireControlLock(ctx, false)
}

func (c *PostgresExecutionControl) AcquireEmergency(
	ctx context.Context,
) (string, func() error, error) {
	return c.acquireControlLock(ctx, true)
}

func (c *PostgresExecutionControl) acquireControlLock(
	ctx context.Context,
	exclusive bool,
) (string, func() error, error) {
	conn, err := c.pool.Acquire(ctx)
	if err != nil {
		return "", nil, fmt.Errorf("acquire execution-control connection: %w", err)
	}
	lockQuery := `SELECT pg_advisory_lock_shared($1)`
	unlockQuery := `SELECT pg_advisory_unlock_shared($1)`
	lockKind := "shared"
	if exclusive {
		lockQuery = `SELECT pg_advisory_lock($1)`
		unlockQuery = `SELECT pg_advisory_unlock($1)`
		lockKind = "exclusive"
	}
	if _, err := conn.Exec(ctx, lockQuery, ExecutionControlAdvisoryKey); err != nil {
		conn.Release()
		return "", nil, fmt.Errorf("acquire %s execution-control lock: %w", lockKind, err)
	}
	var state string
	if err := conn.QueryRow(ctx, `SELECT state FROM execution_control WHERE scope = 'GLOBAL'`).Scan(&state); err != nil {
		releaseErr := releaseExecutionControlLock(ctx, conn, unlockQuery, lockKind)
		return "", nil, errors.Join(fmt.Errorf("read execution control: %w", err), releaseErr)
	}
	var once sync.Once
	var releaseErr error
	release := func() error {
		once.Do(func() {
			releaseErr = releaseExecutionControlLock(ctx, conn, unlockQuery, lockKind)
		})
		return releaseErr
	}
	return state, release, nil
}

func releaseExecutionControlLock(
	ctx context.Context,
	conn *pgxpool.Conn,
	unlockQuery string,
	lockKind string,
) error {
	releaseCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()
	var unlocked bool
	err := conn.QueryRow(releaseCtx, unlockQuery, ExecutionControlAdvisoryKey).Scan(&unlocked)
	if err == nil && !unlocked {
		err = fmt.Errorf("%s execution-control lock was not held", lockKind)
	}
	if err != nil {
		raw := conn.Hijack()
		return errors.Join(err, raw.Close(context.Background()))
	}
	conn.Release()
	return nil
}

func (c *PostgresExecutionControl) Get(ctx context.Context) (*ExecutionControlRecord, error) {
	var record ExecutionControlRecord
	err := c.pool.QueryRow(ctx, `
		SELECT scope, state, generation, reason, requested_by,
		       idempotency_key, requested_at, updated_at
		FROM execution_control WHERE scope = 'GLOBAL'
	`).Scan(
		&record.Scope,
		&record.State,
		&record.Generation,
		&record.Reason,
		&record.RequestedBy,
		&record.IdempotencyKey,
		&record.RequestedAt,
		&record.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("get execution control: %w", err)
	}
	return &record, nil
}

func (c *PostgresExecutionControl) Halt(
	ctx context.Context,
	request ExecutionControlRequest,
) (*ExecutionControlRecord, error) {
	return c.setState(ctx, request, ExecutionStateHalted, nil)
}

func (c *PostgresExecutionControl) Resume(
	ctx context.Context,
	request ExecutionControlRequest,
) (*ExecutionControlRecord, error) {
	return c.setState(ctx, request, ExecutionStateRunning, nil)
}

func (c *PostgresExecutionControl) ResumeSafely(
	ctx context.Context,
	request ExecutionControlRequest,
	safetyCheck func(context.Context) error,
) (*ExecutionControlRecord, error) {
	if safetyCheck == nil {
		return nil, &ResumeSafetyError{Cause: fmt.Errorf("resume safety check is unavailable")}
	}
	return c.setState(ctx, request, ExecutionStateRunning, safetyCheck)
}

func (c *PostgresExecutionControl) setState(
	ctx context.Context,
	request ExecutionControlRequest,
	targetState string,
	safetyCheck func(context.Context) error,
) (*ExecutionControlRecord, error) {
	if request.IdempotencyKey == "" || request.Reason == "" || request.RequestedBy == "" {
		return nil, fmt.Errorf("idempotency_key, reason, and requested_by are required")
	}
	conn, err := c.pool.Acquire(ctx)
	if err != nil {
		return nil, fmt.Errorf("acquire execution-control connection: %w", err)
	}
	defer conn.Release()
	tx, err := conn.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin execution-control transition: %w", err)
	}
	defer func() { _ = tx.Rollback(context.WithoutCancel(ctx)) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, ExecutionControlAdvisoryKey); err != nil {
		return nil, fmt.Errorf("acquire exclusive execution-control lock: %w", err)
	}
	if safetyCheck != nil {
		if err := safetyCheck(ctx); err != nil {
			return nil, &ResumeSafetyError{Cause: err}
		}
	}

	if replay, replayErr := loadControlRequest(ctx, tx, request.IdempotencyKey); replayErr == nil {
		if replay.State != targetState {
			return nil, fmt.Errorf("idempotency key already used for %s", replay.State)
		}
		if replay.Reason != request.Reason || replay.RequestedBy != request.RequestedBy {
			return nil, fmt.Errorf("idempotency key payload mismatch")
		}
		var currentState, currentKey string
		var currentGeneration int64
		if err := tx.QueryRow(ctx, `
			SELECT state, generation, idempotency_key
			FROM execution_control WHERE scope = 'GLOBAL'
			FOR UPDATE
		`).Scan(&currentState, &currentGeneration, &currentKey); err != nil {
			return nil, fmt.Errorf("read current execution control: %w", err)
		}
		if currentState != replay.State || currentGeneration != replay.Generation || currentKey != replay.IdempotencyKey {
			return nil, fmt.Errorf("stale idempotency replay: current state is %s generation %d", currentState, currentGeneration)
		}
		return replay, nil
	} else if replayErr != pgx.ErrNoRows {
		return nil, fmt.Errorf("read execution-control request: %w", replayErr)
	}

	var record ExecutionControlRecord
	err = tx.QueryRow(ctx, `
		UPDATE execution_control
		SET state = $1,
		    generation = generation + 1,
		    reason = $2,
		    requested_by = $3,
		    idempotency_key = $4,
		    requested_at = CURRENT_TIMESTAMP,
		    updated_at = CURRENT_TIMESTAMP
		WHERE scope = 'GLOBAL'
		RETURNING scope, state, generation, reason, requested_by,
		          idempotency_key, requested_at, updated_at
	`, targetState, request.Reason, request.RequestedBy, request.IdempotencyKey).Scan(
		&record.Scope,
		&record.State,
		&record.Generation,
		&record.Reason,
		&record.RequestedBy,
		&record.IdempotencyKey,
		&record.RequestedAt,
		&record.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("update execution control: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO execution_control_requests (
			idempotency_key, scope, target_state, generation, reason, requested_by, requested_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7)
	`, record.IdempotencyKey, record.Scope, record.State, record.Generation,
		record.Reason, record.RequestedBy, record.RequestedAt); err != nil {
		return nil, fmt.Errorf("record execution-control request: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit execution-control transition: %w", err)
	}
	return &record, nil
}

func loadControlRequest(
	ctx context.Context,
	tx pgx.Tx,
	idempotencyKey string,
) (*ExecutionControlRecord, error) {
	var record ExecutionControlRecord
	err := tx.QueryRow(ctx, `
		SELECT scope, target_state, generation, reason, requested_by,
		       idempotency_key, requested_at, requested_at
		FROM execution_control_requests
		WHERE idempotency_key = $1
	`, idempotencyKey).Scan(
		&record.Scope,
		&record.State,
		&record.Generation,
		&record.Reason,
		&record.RequestedBy,
		&record.IdempotencyKey,
		&record.RequestedAt,
		&record.UpdatedAt,
	)
	return &record, err
}
