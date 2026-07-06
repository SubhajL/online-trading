package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/orders"
)

type stubReconciler struct {
	summary *orders.ReconcileSummary
	status  orders.ReconcileStatus
	err     error
	calls   int
}

func (s *stubReconciler) Reconcile(_ context.Context) (*orders.ReconcileSummary, error) {
	s.calls++
	return s.summary, s.err
}

func (s *stubReconciler) Status() orders.ReconcileStatus {
	return s.status
}

func TestReconcileHandler_RejectsUnsupportedMethod(t *testing.T) {
	handler := NewReconcileHandler(&stubReconciler{}, zerolog.Nop())

	rec := httptest.NewRecorder()
	handler(rec, httptest.NewRequest(http.MethodDelete, "/internal/reconcile", nil))

	assert.Equal(t, http.StatusMethodNotAllowed, rec.Code)
}

func TestReconcileHandler_GetReturnsStatusWithoutRunning(t *testing.T) {
	stub := &stubReconciler{status: orders.ReconcileStatus{
		HasRun:  true,
		Summary: &orders.ReconcileSummary{BracketsSwept: 5, UnrepairedLegs: 1},
	}}
	handler := NewReconcileHandler(stub, zerolog.Nop())

	rec := httptest.NewRecorder()
	handler(rec, httptest.NewRequest(http.MethodGet, "/internal/reconcile", nil))

	require.Equal(t, http.StatusOK, rec.Code)
	var got orders.ReconcileStatus
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &got))
	assert.Equal(t, [2]any{true, 1}, [2]any{got.HasRun, got.Summary.UnrepairedLegs})
	assert.Equal(t, 0, stub.calls, "GET must be read-only — it must not trigger a pass")
}

func TestReconcileHandler_ReturnsSummary(t *testing.T) {
	stub := &stubReconciler{summary: &orders.ReconcileSummary{BracketsSwept: 3, BracketsClosed: 1}}
	handler := NewReconcileHandler(stub, zerolog.Nop())

	rec := httptest.NewRecorder()
	handler(rec, httptest.NewRequest(http.MethodPost, "/internal/reconcile", nil))

	require.Equal(t, http.StatusOK, rec.Code)
	var got orders.ReconcileSummary
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &got))
	assert.Equal(t, *stub.summary, got)
	assert.Equal(t, 1, stub.calls)
}

func TestReconcileHandler_InFlightConflicts(t *testing.T) {
	handler := NewReconcileHandler(&stubReconciler{err: orders.ErrReconcileInFlight}, zerolog.Nop())

	rec := httptest.NewRecorder()
	handler(rec, httptest.NewRequest(http.MethodPost, "/internal/reconcile", nil))

	assert.Equal(t, http.StatusConflict, rec.Code)
}

func TestReadyzHandler_GatedOnReconciliation(t *testing.T) {
	h := NewHandlers(nil, zerolog.Nop(), nil, nil)

	readyz := func() int {
		rec := httptest.NewRecorder()
		h.ReadyzHandler(rec, httptest.NewRequest(http.MethodGet, "/readyz", nil))
		return rec.Code
	}

	assert.Equal(t, http.StatusOK, readyz(), "deployments without a reconciler must stay ready by default")

	h.SetReady(false)
	assert.Equal(t, http.StatusServiceUnavailable, readyz(), "not ready while startup reconciliation runs")

	h.SetReady(true)
	assert.Equal(t, http.StatusOK, readyz())
}
