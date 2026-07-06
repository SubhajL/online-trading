package api

import (
	"context"
	"errors"
	"net/http"

	"github.com/rs/zerolog"

	"router/internal/orders"
)

// ReconcileRunner runs one reconciliation pass over open brackets.
type ReconcileRunner interface {
	Reconcile(ctx context.Context) (*orders.ReconcileSummary, error)
}

// NewReconcileHandler serves POST /internal/reconcile: it runs a pass
// synchronously and returns its summary. Auth comes from the router's
// shared token middleware.
func NewReconcileHandler(runner ReconcileRunner, logger zerolog.Logger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
			return
		}

		summary, err := runner.Reconcile(r.Context())
		if err != nil {
			if errors.Is(err, orders.ErrReconcileInFlight) {
				writeError(w, http.StatusConflict, "reconcile already in flight")
				return
			}
			logger.Error().Err(err).Msg("On-demand reconcile failed")
			writeError(w, http.StatusInternalServerError, "reconcile failed")
			return
		}
		writeJSON(w, http.StatusOK, summary)
	}
}
