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
		"../../../../db/migrations/037_order_update_stop_price.sql",
		"../../../../db/migrations/040_order_update_average_fill_price.sql",
		"../../../../db/migrations/042_partial_entry_execution.sql",
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
		AverageFillPrice: decimal.RequireFromString("101.25"),
		UpdateTime:       time.Now().UTC(),
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
		_, _ = pool.Exec(context.Background(), `DELETE FROM orders WHERE venue='SPOT' AND client_order_id=$1`, clientOrderID)
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
		INSERT INTO orders (
			client_order_id, venue, symbol, side, type, quantity, price,
			status, filled_quantity, average_fill_price, exchange_order_id, created_at
		) VALUES ($1,'SPOT','BTCUSDT','BUY','LIMIT',3,100,
			'PARTIALLY_FILLED',1.25,102.50,'42',NOW())
	`, clientOrderID)
	require.NoError(t, err)

	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs SET status='CANCELED'
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	var status, executedQty, averageFillPrice string
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT payload->>'status', payload->>'executed_qty', payload->>'average_fill_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1
		ORDER BY sequence DESC
		LIMIT 1
	`, aggregateID).Scan(&status, &executedQty, &averageFillPrice))
	assert.Equal(t, "CANCELED", status)
	assert.Equal(t, "1.25", executedQty)
	assert.Equal(t, "102.50000000", averageFillPrice,
		"canonical order average must win over the prior outbox average")

	var sequences []int64
	rows, err := pool.Query(ctx, `
		SELECT sequence FROM router_order_update_outbox
		WHERE aggregate_id=$1 ORDER BY sequence
	`, aggregateID)
	require.NoError(t, err)
	for rows.Next() {
		var sequence int64
		require.NoError(t, rows.Scan(&sequence))
		sequences = append(sequences, sequence)
	}
	rows.Close()
	require.NoError(t, rows.Err())
	assert.Equal(t, []int64{1, 2}, sequences)

	_, err = pool.Exec(ctx, `
		UPDATE router_order_update_outbox
		SET created_at = TIMESTAMPTZ '1900-01-01' + sequence * INTERVAL '1 second'
		WHERE aggregate_id=$1
	`, aggregateID)
	require.NoError(t, err)
	first, err := store.Claim(ctx)
	require.NoError(t, err)
	require.NotNil(t, first)
	assert.Equal(t, aggregateID, first.Envelope.AggregateID)
	assert.Equal(t, int64(1), first.Envelope.Sequence)

	var secondClaimable bool
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT NOT EXISTS (
			SELECT 1 FROM router_order_update_outbox earlier
			WHERE earlier.aggregate_id = current.aggregate_id
			  AND earlier.sequence < current.sequence
			  AND earlier.status <> 'DELIVERED'
		)
		FROM router_order_update_outbox current
		WHERE current.aggregate_id=$1 AND current.sequence=2
	`, aggregateID).Scan(&secondClaimable))
	assert.False(t, secondClaimable, "sequence 2 must remain blocked behind delivering sequence 1")

	require.NoError(t, store.MarkDelivered(ctx, first.Envelope.EventID))
	second, err := store.Claim(ctx)
	require.NoError(t, err)
	require.NotNil(t, second)
	assert.Equal(t, aggregateID, second.Envelope.AggregateID)
	assert.Equal(t, int64(2), second.Envelope.Sequence)
	require.NoError(t, store.MarkDelivered(ctx, second.Envelope.EventID))

	_, err = pool.Exec(ctx, `DELETE FROM orders WHERE venue='SPOT' AND client_order_id=$1`, clientOrderID)
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs SET status='EXPIRED'
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT payload->>'average_fill_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1 AND sequence=3
	`, aggregateID).Scan(&averageFillPrice))
	assert.Equal(t, "102.50000000", averageFillPrice,
		"the newest prior average must survive when no canonical average remains")
}

func TestBracketLegTriggerUsesNullPriceForMarketEntry(t *testing.T) {
	_, pool, ctx := newOutboxIntegrationStore(t)
	bracketID := uuid.New()
	clientOrderID := "market-entry-" + uuid.NewString()
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
		) VALUES ($1,'SPOT','BTCUSDT','BUY',2,0,49000,$2,'ENTRY_PLACED',$3,repeat('0',64))
	`, bracketID, clientOrderID, "test-"+uuid.NewString())
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		INSERT INTO bracket_legs (
			bracket_id, role, client_order_id, exchange_order_id, price, quantity, status
		) VALUES ($1,'ENTRY',$2,42,0,2,'PLACING')
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs SET status='PLACED'
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	var orderType string
	var price, stopPrice *string
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT payload->>'order_type', payload->>'price', payload->>'stop_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1
		ORDER BY sequence DESC
		LIMIT 1
	`, aggregateID).Scan(&orderType, &price, &stopPrice))
	assert.Equal(t, "MARKET", orderType)
	assert.Nil(t, price)
	assert.Nil(t, stopPrice)
}

func TestBracketLegTriggerPreservesSpotStopLimitTypeAndPrices(t *testing.T) {
	_, pool, ctx := newOutboxIntegrationStore(t)
	bracketID := uuid.New()
	clientOrderID := "spot-stop-limit-" + uuid.NewString()
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
		) VALUES ($1,'SPOT','BTCUSDT','BUY',2,50000,49500,$2,'ENTRY_PLACED',$3,repeat('0',64))
	`, bracketID, "entry-"+uuid.NewString(), "test-"+uuid.NewString())
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		INSERT INTO bracket_legs (
			bracket_id, role, client_order_id, exchange_order_id, price, stop_price, quantity, status
		) VALUES ($1,'SL',$2,42,49000,49500,2,'PLACING')
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs SET status='PLACED'
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	var orderType, price, stopPrice string
	require.NoError(t, pool.QueryRow(ctx, `
		SELECT payload->>'order_type', payload->>'price', payload->>'stop_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1
		ORDER BY sequence DESC
		LIMIT 1
	`, aggregateID).Scan(&orderType, &price, &stopPrice))
	assert.Equal(t, "STOP_LOSS_LIMIT", orderType)
	assert.Equal(t, "49000.00000000", price)
	assert.Equal(t, "49500.00000000", stopPrice)
}

func TestBracketEntryProgressEmitsOrderedPartialThenTerminalQuantity(t *testing.T) {
	_, pool, ctx := newOutboxIntegrationStore(t)
	bracketID := uuid.New()
	clientOrderID := "entry-progress-" + uuid.NewString()
	aggregateID := "USD_M:" + clientOrderID
	t.Cleanup(func() {
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_outbox WHERE aggregate_id=$1`, aggregateID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM router_order_update_sequences WHERE aggregate_id=$1`, aggregateID)
		_, _ = pool.Exec(context.Background(), `DELETE FROM brackets WHERE bracket_id=$1`, bracketID)
	})

	_, err := pool.Exec(ctx, `
		INSERT INTO brackets (
			bracket_id, venue, symbol, side, quantity, entry_price, stop_loss_price,
			entry_client_order_id, status, idempotency_key, request_hash
		) VALUES ($1,'USD_M','BTCUSDT','BUY',2,50000,49000,$2,'ENTRY_PLACED',$3,repeat('0',64))
	`, bracketID, clientOrderID, "test-"+uuid.NewString())
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		INSERT INTO bracket_legs (
			bracket_id, role, client_order_id, exchange_order_id, price, quantity, status
		) VALUES ($1,'ENTRY',$2,42,50000,2,'PLACED')
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs
		SET executed_quantity=0.5, average_fill_price=50010
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `
		UPDATE bracket_legs
		SET status='CANCELED', executed_quantity=0.75, average_fill_price=50020
		WHERE bracket_id=$1 AND client_order_id=$2
	`, bracketID, clientOrderID)
	require.NoError(t, err)

	rows, err := pool.Query(ctx, `
		SELECT sequence, payload->>'status', payload->>'executed_qty', payload->>'average_fill_price'
		FROM router_order_update_outbox
		WHERE aggregate_id=$1
		ORDER BY sequence
	`, aggregateID)
	require.NoError(t, err)
	defer rows.Close()
	type updateRow struct {
		sequence int64
		status   string
		executed string
		average  string
	}
	var updates []updateRow
	for rows.Next() {
		var update updateRow
		require.NoError(t, rows.Scan(&update.sequence, &update.status, &update.executed, &update.average))
		updates = append(updates, update)
	}
	require.NoError(t, rows.Err())
	assert.Equal(t, []updateRow{
		{sequence: 1, status: "PARTIALLY_FILLED", executed: "0.50000000", average: "50010.00000000"},
		{sequence: 2, status: "CANCELED", executed: "0.75000000", average: "50020.00000000"},
	}, updates)
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
