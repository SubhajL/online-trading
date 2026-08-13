package orders

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"

	"router/internal/storage"
)

type OrderUpdateEnvelope struct {
	EventID      uuid.UUID       `json:"event_id"`
	AggregateID  string          `json:"aggregate_id"`
	Sequence     int64           `json:"sequence"`
	EventVersion int             `json:"event_version"`
	EventType    string          `json:"event_type"`
	OccurredAt   time.Time       `json:"occurred_at"`
	Payload      json.RawMessage `json:"payload"`
}

type OutboxMessage struct {
	Envelope OrderUpdateEnvelope
	Attempts int
}

type OutboxStore interface {
	Enqueue(context.Context, *OrderUpdate) error
	Claim(context.Context) (*OutboxMessage, error)
	MarkDelivered(context.Context, uuid.UUID) error
	MarkFailed(context.Context, uuid.UUID, int, string, time.Time, bool) error
}

type PostgresOutboxStore struct {
	pool *pgxpool.Pool
}

func NewPostgresOutboxStore(pool *pgxpool.Pool) *PostgresOutboxStore {
	return &PostgresOutboxStore{pool: pool}
}

func (store *PostgresOutboxStore) Health(ctx context.Context) (pending int, dead int, oldest time.Duration, err error) {
	var oldestSeconds float64
	err = store.pool.QueryRow(ctx, `
		SELECT
			COUNT(*) FILTER (WHERE status IN ('PENDING', 'DELIVERING')),
			COUNT(*) FILTER (WHERE status = 'DEAD'),
			COALESCE(EXTRACT(EPOCH FROM (
				CURRENT_TIMESTAMP - MIN(created_at) FILTER (WHERE status IN ('PENDING', 'DELIVERING'))
			)), 0)
		FROM router_order_update_outbox
	`).Scan(&pending, &dead, &oldestSeconds)
	return pending, dead, time.Duration(oldestSeconds * float64(time.Second)), err
}

func (store *PostgresOutboxStore) Enqueue(ctx context.Context, update *OrderUpdate) error {
	if store == nil || store.pool == nil {
		return fmt.Errorf("outbox store is unavailable")
	}
	if update == nil || update.ClientOrderID == "" {
		return fmt.Errorf("order update and client_order_id are required")
	}
	aggregateID := strings.ToUpper(update.Venue) + ":" + update.ClientOrderID
	payload, err := json.Marshal(update)
	if err != nil {
		return fmt.Errorf("marshal order update: %w", err)
	}
	digest := sha256.Sum256(payload)
	semanticUpdate := *update
	semanticUpdate.UpdateTime = time.Time{}
	semanticPayload, err := json.Marshal(&semanticUpdate)
	if err != nil {
		return fmt.Errorf("marshal semantic order update: %w", err)
	}
	eventKeyDigest := sha256.Sum256(semanticPayload)
	eventKeyHash := hex.EncodeToString(eventKeyDigest[:])
	eventID := uuid.New()
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin outbox enqueue: %w", err)
	}
	defer func() { _ = tx.Rollback(context.WithoutCancel(ctx)) }()
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, aggregateID); err != nil {
		return fmt.Errorf("lock outbox aggregate: %w", err)
	}
	var alreadyQueued bool
	err = tx.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM router_order_update_outbox
			WHERE aggregate_id = $1
			  AND event_key_hash = $2
			ORDER BY sequence DESC LIMIT 1
		)
	`, aggregateID, eventKeyHash).Scan(&alreadyQueued)
	if err != nil {
		return fmt.Errorf("check existing outbox event: %w", err)
	}
	if alreadyQueued {
		return nil
	}
	var sequence int64
	err = tx.QueryRow(ctx, `
		INSERT INTO router_order_update_sequences (aggregate_id, next_sequence)
		VALUES ($1, 2)
		ON CONFLICT (aggregate_id) DO UPDATE
		SET next_sequence = router_order_update_sequences.next_sequence + 1,
		    updated_at = CURRENT_TIMESTAMP
		RETURNING next_sequence - 1
	`, aggregateID).Scan(&sequence)
	if err != nil {
		return fmt.Errorf("allocate outbox sequence: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO router_order_update_outbox (
			event_id, aggregate_id, sequence, event_version, event_type,
			payload, payload_hash, event_key_hash, status, next_attempt_at
		) VALUES ($1,$2,$3,1,'order_update.v1',$4::jsonb,$5,$6,'PENDING',CURRENT_TIMESTAMP)
	`, eventID, aggregateID, sequence, payload, hex.EncodeToString(digest[:]), eventKeyHash)
	if err != nil {
		return fmt.Errorf("insert outbox event: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit outbox event: %w", err)
	}
	return nil
}

func (store *PostgresOutboxStore) Claim(ctx context.Context) (*OutboxMessage, error) {
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return nil, fmt.Errorf("begin outbox claim: %w", err)
	}
	defer func() { _ = tx.Rollback(context.WithoutCancel(ctx)) }()
	var message OutboxMessage
	var payload []byte
	err = tx.QueryRow(ctx, `
		WITH candidate AS (
			SELECT event_id
			FROM router_order_update_outbox current
			WHERE (
				(current.status = 'PENDING' AND current.next_attempt_at <= CURRENT_TIMESTAMP)
				OR (current.status = 'DELIVERING' AND current.next_attempt_at <= CURRENT_TIMESTAMP - INTERVAL '60 seconds')
			)
			AND NOT EXISTS (
				SELECT 1 FROM router_order_update_outbox earlier
				WHERE earlier.aggregate_id = current.aggregate_id
				  AND earlier.sequence < current.sequence
				  AND earlier.status <> 'DELIVERED'
			)
			ORDER BY current.created_at, current.sequence
			FOR UPDATE SKIP LOCKED
			LIMIT 1
		)
		UPDATE router_order_update_outbox outbox
		SET status = 'DELIVERING', attempts = attempts + 1,
		    next_attempt_at = CURRENT_TIMESTAMP, last_error = NULL
		FROM candidate
		WHERE outbox.event_id = candidate.event_id
		RETURNING outbox.event_id, outbox.aggregate_id, outbox.sequence,
		          outbox.event_version, outbox.event_type, outbox.created_at,
		          outbox.payload::text, outbox.attempts
	`).Scan(
		&message.Envelope.EventID,
		&message.Envelope.AggregateID,
		&message.Envelope.Sequence,
		&message.Envelope.EventVersion,
		&message.Envelope.EventType,
		&message.Envelope.OccurredAt,
		&payload,
		&message.Attempts,
	)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("claim outbox event: %w", err)
	}
	message.Envelope.Payload = payload
	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit outbox claim: %w", err)
	}
	return &message, nil
}

func (store *PostgresOutboxStore) MarkDelivered(ctx context.Context, eventID uuid.UUID) error {
	result, err := store.pool.Exec(ctx, `
		UPDATE router_order_update_outbox
		SET status = 'DELIVERED', delivered_at = CURRENT_TIMESTAMP, last_error = NULL
		WHERE event_id = $1 AND status = 'DELIVERING'
	`, eventID)
	if err != nil {
		return err
	}
	if result.RowsAffected() != 1 {
		return fmt.Errorf("outbox event %s was not delivering", eventID)
	}
	return nil
}

func (store *PostgresOutboxStore) MarkFailed(
	ctx context.Context,
	eventID uuid.UUID,
	attempts int,
	errorMessage string,
	nextAttempt time.Time,
	dead bool,
) error {
	status := "PENDING"
	if dead {
		status = "DEAD"
	}
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin outbox failure transition: %w", err)
	}
	defer func() { _ = tx.Rollback(context.WithoutCancel(ctx)) }()
	if dead {
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock($1)`, storage.ExecutionControlAdvisoryKey); err != nil {
			return fmt.Errorf("lock execution control for dead outbox event: %w", err)
		}
	}
	result, err := tx.Exec(ctx, `
		UPDATE router_order_update_outbox
		SET status = $2, last_error = $3, next_attempt_at = $4
		WHERE event_id = $1 AND status = 'DELIVERING'
	`, eventID, status, errorMessage, nextAttempt)
	if err != nil {
		return fmt.Errorf("persist outbox failure: %w", err)
	}
	if result.RowsAffected() != 1 {
		return fmt.Errorf("outbox event %s was not delivering", eventID)
	}
	if dead {
		idempotencyKey := "outbox-dead:" + eventID.String()
		var generation int64
		err = tx.QueryRow(ctx, `
			UPDATE execution_control
			SET state='HALTED', generation=generation+1,
			    reason='order update delivery reached dead-letter state',
			    requested_by='router-outbox', idempotency_key=$1,
			    requested_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
			WHERE scope='GLOBAL' AND state <> 'HALTED'
			RETURNING generation
		`, idempotencyKey).Scan(&generation)
		if err != nil && err != pgx.ErrNoRows {
			return fmt.Errorf("halt execution for dead outbox event: %w", err)
		}
		if err == nil {
			if _, err := tx.Exec(ctx, `
				INSERT INTO execution_control_requests (
					idempotency_key, scope, target_state, generation,
					reason, requested_by, requested_at
				) VALUES ($1,'GLOBAL','HALTED',$2,
					'order update delivery reached dead-letter state','router-outbox',CURRENT_TIMESTAMP)
			`, idempotencyKey, generation); err != nil {
				return fmt.Errorf("record outbox-triggered halt: %w", err)
			}
		}
	}
	_ = attempts
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit outbox failure transition: %w", err)
	}
	return nil
}

type OutboxEventEmitter struct {
	store OutboxStore
}

func NewOutboxEventEmitter(store OutboxStore) *OutboxEventEmitter {
	return &OutboxEventEmitter{store: store}
}

func (emitter *OutboxEventEmitter) EmitOrderUpdate(ctx context.Context, update *OrderUpdate) error {
	return emitter.store.Enqueue(ctx, update)
}

type OutboxDispatcher struct {
	store       OutboxStore
	url         string
	token       string
	client      *http.Client
	logger      zerolog.Logger
	maxAttempts int
}

func NewOutboxDispatcher(
	store OutboxStore,
	url string,
	token string,
	logger zerolog.Logger,
) *OutboxDispatcher {
	return &OutboxDispatcher{
		store: store, url: url, token: token,
		client: &http.Client{Timeout: 5 * time.Second}, logger: logger,
		maxAttempts: 20,
	}
}

func (dispatcher *OutboxDispatcher) Run(ctx context.Context) {
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	for {
		if _, err := dispatcher.DispatchOnce(ctx); err != nil && ctx.Err() == nil {
			dispatcher.logger.Error().Err(err).Msg("order update outbox dispatch failed")
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (dispatcher *OutboxDispatcher) DispatchOnce(ctx context.Context) (bool, error) {
	message, err := dispatcher.store.Claim(ctx)
	if err != nil || message == nil {
		return false, err
	}
	body, err := json.Marshal(message.Envelope)
	if err == nil {
		var request *http.Request
		request, err = http.NewRequestWithContext(ctx, http.MethodPost, dispatcher.url, bytes.NewReader(body))
		if err == nil {
			request.Header.Set("Content-Type", "application/json")
			if dispatcher.token != "" {
				request.Header.Set("Authorization", "Bearer "+dispatcher.token)
			}
			var response *http.Response
			response, err = dispatcher.client.Do(request)
			if err == nil {
				_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
				_ = response.Body.Close()
				if response.StatusCode < 200 || response.StatusCode >= 300 {
					err = fmt.Errorf("order update receiver returned HTTP %d", response.StatusCode)
				}
			}
		}
	}
	if err == nil {
		return true, dispatcher.store.MarkDelivered(ctx, message.Envelope.EventID)
	}
	dead := message.Attempts >= dispatcher.maxAttempts
	jitter := time.Duration(message.Envelope.EventID[15]) * time.Millisecond
	backoff := time.Duration(1<<min(message.Attempts, 8))*time.Second + jitter
	markErr := dispatcher.store.MarkFailed(
		context.WithoutCancel(ctx),
		message.Envelope.EventID,
		message.Attempts,
		err.Error(),
		time.Now().Add(backoff),
		dead,
	)
	if markErr != nil {
		return true, fmt.Errorf("delivery failed (%v) and failure state could not persist: %w", err, markErr)
	}
	return true, err
}
