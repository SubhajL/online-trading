package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"router/internal/storage"
)

type ExecutionControlStore interface {
	Get(ctx context.Context) (*storage.ExecutionControlRecord, error)
	Halt(ctx context.Context, request storage.ExecutionControlRequest) (*storage.ExecutionControlRecord, error)
	ResumeSafely(
		ctx context.Context,
		request storage.ExecutionControlRequest,
		safetyCheck func(context.Context) error,
	) (*storage.ExecutionControlRecord, error)
}

type ResumeSafetyCheck func(ctx context.Context) error

func NewExecutionControlHandler(
	store ExecutionControlStore,
	resumeSafetyCheck ResumeSafetyCheck,
) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if store == nil {
			writeError(w, http.StatusServiceUnavailable, "Execution control is unavailable")
			return
		}
		switch {
		case r.Method == http.MethodGet && r.URL.Path == "/internal/execution-control":
			record, err := store.Get(r.Context())
			if err != nil {
				writeError(w, http.StatusServiceUnavailable, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, record)
		case r.Method == http.MethodPost && r.URL.Path == "/internal/execution-control/halt":
			request, ok := decodeExecutionControlRequest(w, r)
			if !ok {
				return
			}
			record, err := store.Halt(r.Context(), request)
			if err != nil {
				writeError(w, http.StatusServiceUnavailable, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, record)
		case r.Method == http.MethodPost && r.URL.Path == "/internal/execution-control/resume":
			request, ok := decodeExecutionControlRequest(w, r)
			if !ok {
				return
			}
			if !request.ConfirmSafe {
				writeError(w, http.StatusConflict, "confirm_safe is required to resume execution")
				return
			}
			if resumeSafetyCheck == nil {
				writeError(w, http.StatusServiceUnavailable, "Resume safety check is unavailable")
				return
			}
			record, err := store.ResumeSafely(r.Context(), request, resumeSafetyCheck)
			if err != nil {
				var safetyErr *storage.ResumeSafetyError
				if errors.As(err, &safetyErr) {
					writeError(w, http.StatusConflict, fmt.Sprintf("Execution is not safe to resume: %v", safetyErr.Cause))
					return
				}
				writeError(w, http.StatusServiceUnavailable, err.Error())
				return
			}
			writeJSON(w, http.StatusOK, record)
		default:
			writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		}
	}
}

func decodeExecutionControlRequest(
	w http.ResponseWriter,
	r *http.Request,
) (storage.ExecutionControlRequest, bool) {
	var request storage.ExecutionControlRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "Invalid request body")
		return storage.ExecutionControlRequest{}, false
	}
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.Reason = strings.TrimSpace(request.Reason)
	request.RequestedBy = strings.TrimSpace(request.RequestedBy)
	if request.IdempotencyKey == "" || request.Reason == "" || request.RequestedBy == "" {
		writeError(w, http.StatusBadRequest, "idempotency_key, reason, and requested_by are required")
		return storage.ExecutionControlRequest{}, false
	}
	return request, true
}
