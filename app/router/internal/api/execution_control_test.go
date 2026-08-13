package api

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/storage"
)

type fakeExecutionControlStore struct {
	record       *storage.ExecutionControlRecord
	haltRequests []storage.ExecutionControlRequest
	resumeCalls  int
}

func (s *fakeExecutionControlStore) Get(_ context.Context) (*storage.ExecutionControlRecord, error) {
	return s.record, nil
}

func (s *fakeExecutionControlStore) Halt(
	_ context.Context,
	request storage.ExecutionControlRequest,
) (*storage.ExecutionControlRecord, error) {
	s.haltRequests = append(s.haltRequests, request)
	return s.record, nil
}

func (s *fakeExecutionControlStore) ResumeSafely(
	ctx context.Context,
	_ storage.ExecutionControlRequest,
	safetyCheck func(context.Context) error,
) (*storage.ExecutionControlRecord, error) {
	if err := safetyCheck(ctx); err != nil {
		return nil, &storage.ResumeSafetyError{Cause: err}
	}
	s.resumeCalls++
	return s.record, nil
}

func TestExecutionControlHaltReturnsDurableAcknowledgment(t *testing.T) {
	store := &fakeExecutionControlStore{record: &storage.ExecutionControlRecord{
		Scope: "GLOBAL", State: storage.ExecutionStateHalted, Generation: 2,
	}}
	handler := NewExecutionControlHandler(store, nil)
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/execution-control/halt",
		bytes.NewBufferString(`{"reason":"operator stop","requested_by":"ops","idempotency_key":"halt-1"}`),
	)
	recorder := httptest.NewRecorder()

	handler(recorder, req)

	require.Equal(t, http.StatusOK, recorder.Code)
	assert.Contains(t, recorder.Body.String(), `"state":"HALTED"`)
	require.Len(t, store.haltRequests, 1)
	assert.Equal(t, "halt-1", store.haltRequests[0].IdempotencyKey)
}

func TestExecutionControlResumeRequiresPassingSafetyCheck(t *testing.T) {
	store := &fakeExecutionControlStore{record: &storage.ExecutionControlRecord{
		Scope: "GLOBAL", State: storage.ExecutionStateRunning, Generation: 3,
	}}
	handler := NewExecutionControlHandler(store, func(_ context.Context) error {
		return errors.New("reconciliation has unrepaired legs")
	})
	req := httptest.NewRequest(
		http.MethodPost,
		"/internal/execution-control/resume",
		bytes.NewBufferString(`{"reason":"resume","requested_by":"ops","idempotency_key":"resume-1","confirm_safe":true}`),
	)
	recorder := httptest.NewRecorder()

	handler(recorder, req)

	require.Equal(t, http.StatusConflict, recorder.Code)
	assert.Zero(t, store.resumeCalls)
}
