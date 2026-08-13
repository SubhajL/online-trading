package storage

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newExecutionControlTestStore(t *testing.T) (*PostgresExecutionControl, context.Context) {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	t.Cleanup(cancel)
	pool, err := NewPostgresPool(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)
	_, err = pool.Exec(ctx, `CREATE EXTENSION IF NOT EXISTS pgcrypto`)
	require.NoError(t, err)
	for _, file := range []string{
		"../../../../db/migrations/030_brackets.sql",
		"../../../../db/migrations/031_bracket_leg_placing.sql",
		"../../../../db/migrations/034_execution_safety.sql",
	} {
		migration, readErr := os.ReadFile(file)
		require.NoError(t, readErr)
		_, err = pool.Exec(ctx, string(migration))
		require.NoError(t, err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cleanupCancel()
		_, _ = pool.Exec(cleanupCtx, `DELETE FROM execution_control_requests`)
		_, _ = pool.Exec(cleanupCtx, `
			UPDATE execution_control
			SET state='HALTED', reason='test cleanup', requested_by='test',
			    idempotency_key='test-cleanup', updated_at=CURRENT_TIMESTAMP
			WHERE scope='GLOBAL'`)
	})
	return NewPostgresExecutionControl(pool), ctx
}

func TestHaltSurvivesRouterRestart(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	key := "halt-" + uuid.NewString()

	record, err := store.Halt(ctx, ExecutionControlRequest{
		Reason: "restart proof", RequestedBy: "test", IdempotencyKey: key,
	})
	require.NoError(t, err)
	require.Equal(t, ExecutionStateHalted, record.State)

	restarted := NewPostgresExecutionControl(store.pool)
	current, err := restarted.Get(ctx)
	require.NoError(t, err)
	assert.Equal(t, ExecutionStateHalted, current.State)
	assert.Equal(t, key, current.IdempotencyKey)

	state, release, err := restarted.AcquirePlacement(ctx)
	require.NoError(t, err)
	assert.Equal(t, ExecutionStateHalted, state)
	require.NoError(t, release())
}

func TestExecutionControlIdempotentHaltDoesNotAdvanceGeneration(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	request := ExecutionControlRequest{
		Reason: "operator stop", RequestedBy: "test", IdempotencyKey: "halt-" + uuid.NewString(),
	}

	first, err := store.Halt(ctx, request)
	require.NoError(t, err)
	replay, err := store.Halt(ctx, request)
	require.NoError(t, err)

	assert.Equal(t, first.Generation, replay.Generation)
}

func TestExecutionControlRejectsIdempotencyKeyPayloadMismatch(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	key := "halt-" + uuid.NewString()
	_, err := store.Halt(ctx, ExecutionControlRequest{
		Reason: "operator stop", RequestedBy: "operator-a", IdempotencyKey: key,
	})
	require.NoError(t, err)

	_, err = store.Halt(ctx, ExecutionControlRequest{
		Reason: "different reason", RequestedBy: "operator-b", IdempotencyKey: key,
	})

	require.ErrorContains(t, err, "idempotency key payload mismatch")
}

func TestExecutionControlRejectsStaleHaltReplayAfterResume(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	haltRequest := ExecutionControlRequest{
		Reason: "operator stop", RequestedBy: "operator-a", IdempotencyKey: "halt-" + uuid.NewString(),
	}
	_, err := store.Halt(ctx, haltRequest)
	require.NoError(t, err)
	_, err = store.Resume(ctx, ExecutionControlRequest{
		Reason: "safe resume", RequestedBy: "operator-a", IdempotencyKey: "resume-" + uuid.NewString(),
	})
	require.NoError(t, err)

	_, err = store.Halt(ctx, haltRequest)

	require.ErrorContains(t, err, "stale idempotency replay")
	current, getErr := store.Get(ctx)
	require.NoError(t, getErr)
	assert.Equal(t, ExecutionStateRunning, current.State)
}

func TestExecutionControlResumeSafetyFailureLeavesSystemHalted(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	_, err := store.Halt(ctx, ExecutionControlRequest{
		Reason: "precondition", RequestedBy: "test", IdempotencyKey: "halt-" + uuid.NewString(),
	})
	require.NoError(t, err)

	_, err = store.ResumeSafely(ctx, ExecutionControlRequest{
		Reason: "unsafe resume", RequestedBy: "test", IdempotencyKey: "resume-" + uuid.NewString(),
	}, func(context.Context) error {
		return errors.New("outbox became dead")
	})

	var safetyErr *ResumeSafetyError
	require.ErrorAs(t, err, &safetyErr)
	current, getErr := store.Get(ctx)
	require.NoError(t, getErr)
	assert.Equal(t, ExecutionStateHalted, current.State)
}

func TestEmergencyFencesAreExclusive(t *testing.T) {
	store, ctx := newExecutionControlTestStore(t)
	state, releaseFirst, err := store.AcquireEmergency(ctx)
	require.NoError(t, err)
	require.Equal(t, ExecutionStateHalted, state)

	acquiredSecond := make(chan func() error, 1)
	errSecond := make(chan error, 1)
	go func() {
		_, release, acquireErr := store.AcquireEmergency(ctx)
		if acquireErr != nil {
			errSecond <- acquireErr
			return
		}
		acquiredSecond <- release
	}()

	select {
	case <-acquiredSecond:
		t.Fatal("a second emergency operation acquired the global fence concurrently")
	case acquireErr := <-errSecond:
		t.Fatalf("second emergency fence failed before release: %v", acquireErr)
	case <-time.After(100 * time.Millisecond):
	}

	require.NoError(t, releaseFirst())
	select {
	case releaseSecond := <-acquiredSecond:
		require.NoError(t, releaseSecond())
	case acquireErr := <-errSecond:
		t.Fatalf("second emergency fence failed: %v", acquireErr)
	case <-time.After(2 * time.Second):
		t.Fatal("second emergency fence did not acquire after release")
	}
}
