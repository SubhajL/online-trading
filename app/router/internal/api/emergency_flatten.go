package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"router/internal/orders"
)

type EmergencyFlattener interface {
	EmergencyFlatten(context.Context, *orders.EmergencyFlattenRequest) (*orders.EmergencyFlattenResponse, error)
}

func NewEmergencyFlattenHandler(flattener EmergencyFlattener) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
			return
		}
		if flattener == nil {
			writeError(w, http.StatusServiceUnavailable, "Emergency flatten is unavailable")
			return
		}
		var request orders.EmergencyFlattenRequest
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			writeError(w, http.StatusBadRequest, "Invalid request body")
			return
		}
		response, err := flattener.EmergencyFlatten(r.Context(), &request)
		if err != nil {
			switch {
			case errors.Is(err, orders.ErrExecutionNotHalted):
				writeError(w, http.StatusLocked, err.Error())
			case errors.Is(err, orders.ErrExecutionDurabilityUnavailable):
				writeError(w, http.StatusServiceUnavailable, err.Error())
			default:
				writeError(w, http.StatusBadRequest, err.Error())
			}
			return
		}
		writeJSON(w, http.StatusOK, response)
	}
}
