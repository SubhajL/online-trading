package orders

import (
	"context"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newOutboxIntegrationStore(t *testing.T) (*PostgresOutboxStore, *pgxpool.Pool, context.Context) {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	t.Cleanup(cancel)
	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)
	_, err = pool.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
	require.NoError(t, err)
	for _, file := range []string{
		"../../../../db/migrations/030_brackets.sql",
		"../../../../db/migrations/031_bracket_leg_placing.sql",
		"../../../../db/migrations/034_execution_safety.sql",
		"../../../../db/migrations/035_order_update_delivery.sql",
	} {
		migration, readErr := os.ReadFile(file)
		require.NoError(t, readErr)
		_, err = pool.Exec(ctx, string(migration))
		require.NoError(t, err)
	}
	return NewPostgresOutboxStore(pool), pool, ctx
}

func TestExecutionSafetyTablesGrantRuntimeRoleAccess(t *testing.T) {
	_, pool, ctx := newOutboxIntegrationStore(t)
	for _, table := range []string{
		"execution_intents",
		"execution_control",
		"execution_control_requests",
		"router_order_update_sequences",
		"router_order_update_outbox",
		"engine_order_update_inbox",
	} {
		var allowed bool
		require.NoError(t, pool.QueryRow(
			ctx,
			`SELECT has_table_privilege('trading_user', $1, 'SELECT,INSERT,UPDATE,DELETE')`,
			table,
		).Scan(&allowed))
		assert.True(t, allowed, table)
	}
}

func testPartialUpdate(clientOrderID string, executed string) *OrderUpdate {
	return &OrderUpdate{
		EventType: "order_update.v1", Venue: "SPOT", Symbol: "BTCUSDT",
		OrderID: 42, ClientOrderID: clientOrderID, Status: "PARTIALLY_FILLED",
		Side: "BUY", OrderType: "LIMIT", Price: decimal.NewFromInt(100),
		Quantity: decimal.NewFromInt(3), ExecutedQty: decimal.RequireFromString(executed),
		UpdateTime: time.Now().UTC(),
	}
}

func TestOutboxPreservesDistinctPartialFillProgress(t *testing.T) {
	store, pool, ctx := newOutboxIntegrationStore(t)
	clientOrderID := "partial-" + uuid.NewString()
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_outbox WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_sequences WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
	})

	require.NoError(t, store.Enqueue(ctx, testPartialUpdate(clientOrderID, "1")))
	require.NoError(t, store.Enqueue(ctx, testPartialUpdate(clientOrderID, "2")))

	var count int
	require.NoError(t, pool.QueryRow(ctx, `SELECT count(*) FROM router_order_update_outbox WHERE aggregate_id=$1`, "SPOT:"+clientOrderID).Scan(&count))
	assert.Equal(t, 2, count)
}

func TestBracketLegTerminalTriggerPreservesPartialExecutedQuantity(t *testing.T) {
	store, pool, ctx := newOutboxIntegrationStore(t)
	bracketID := uuid.New()
	clientOrderID := "trigger-partial-" + uuid.NewString()
	aggregateID := "SPOT:" + clientOrderID
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_outbox WHERE aggregate_id=$1`, aggregateID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_sequences WHERE aggregate_id=$1`, aggregateID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM brackets WHERE bracket_id=$1`, bracketID)
	})
	_, err := pool.Exec(ctx, `
		INSERT INTO brackets (
			bracket_id, venue, symbol, side, quantity, entry_price, stop_loss_price,
			entry_client_order_id, status, idempotency_key, request_hash
		) VALUES ($1,'SPOT','BTCUSDT','BUY',3,100,90,$2,'LEGS_PLACED',$3,repeat('0',64))
	`, bracketID, "entry-"+uuid.NewString(), "test-"+uuid.NewString())
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		INSERT INTO bracket_legs (
			bracket_id, role, tp_index, client_order_id, exchange_order_id, price, quantity, status
		) VALUES ($1,'TP',1,$2,42,110,3,'PLACED')
	`, bracketID, clientOrderID)
	require.NoError(t, err)
	require.NoError(t, store.Enqueue(ctx, testPartialUpdate(clientOrderID, "1.25")))

	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs SET status='CANCELED'
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	var status, executedQty string
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT payload->>'status', payload->>'executed_qty'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1
		ORDER BY sequence DESC
		LIMIT 1
	`, aggregateID).Scan(&status, &executedQty))
	assert.Equal(t, "CANCELED", status)
	assert.Equal(t, "1.25", executedQty)
}

func TestOutboxConcurrentIdenticalEnqueueCreatesOneEvent(t *testing.T) {
	store, pool, ctx := newOutboxIntegrationStore(t)
	clientOrderID := "concurrent-" + uuid.NewString()
	update := testPartialUpdate(clientOrderID, "1")
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_outbox WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_sequences WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
	})

	var wg sync.WaitGroup
	errors := make(chan error, 2)
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			errors <- store.Enqueue(ctx, update)
		}()
	}
	wg.Wait()
	close(errors)
	for err := range errors {
		require.NoError(t, err)
	}

	var count int
	require.NoError(t, pool.QueryRow(ctx, `SELECT count(*) FROM router_order_update_outbox WHERE aggregate_id=$1`, "SPOT:"+clientOrderID).Scan(&count))
	assert.Equal(t, 1, count)
}

func TestDeadOutboxEventAtomicallyHaltsExecution(t *testing.T) {
	store, pool, ctx := newOutboxIntegrationStore(t)
	clientOrderID := "dead-" + uuid.NewString()
	require.NoError(t, store.Enqueue(ctx, testPartialUpdate(clientOrderID, "1")))
	message, err := store.Claim(ctx)
	require.NoError(t, err)
	require.NotNil(t, message)
	_, err = pool.Exec(ctx, `
		UPDATE execution_control
		SET state='RUNNING', reason='test setup', requested_by='test',
		    idempotency_key=$1, generation=generation+1
		WHERE scope='GLOBAL'
	`, "running-"+uuid.NewString())
	require.NoError(t, err)
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_outbox WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_sequences WHERE aggregate_id=$1`, "SPOT:"+clientOrderID)
	})

	err = store.MarkFailed(ctx, message.Envelope.EventID, message.Attempts, "permanent delivery failure", time.Now(), true)

	require.NoError(t, err)
	var state, reason string
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT state, reason FROM execution_control WHERE scope='GLOBAL'
	`).Scan(&state, &reason))
	assert.Equal(t, "HALTED", state)
	assert.Contains(t, reason, "order update delivery")
}
