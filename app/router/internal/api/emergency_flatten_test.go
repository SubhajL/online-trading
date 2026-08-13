package api

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"router/internal/orders"
)

type fakeEmergencyFlattener struct {
	response *orders.EmergencyFlattenResponse
	err      error
}

func (fake fakeEmergencyFlattener) EmergencyFlatten(
	context.Context,
	*orders.EmergencyFlattenRequest,
) (*orders.EmergencyFlattenResponse, error) {
	return fake.response, fake.err
}

func TestEmergencyFlattenHandlerReturnsExchangeVerdict(t *testing.T) {
	handler := NewEmergencyFlattenHandler(fakeEmergencyFlattener{
		response: &orders.EmergencyFlattenResponse{FullyFlattened: true, Passes: 1},
	})
	request := httptest.NewRequest(http.MethodPost, "/emergency_flatten", strings.NewReader(
		`{"scope":"ALL","idempotency_key":"emergency-1"}`,
	))
	response := httptest.NewRecorder()

	handler(response, request)

	assert.Equal(t, http.StatusOK, response.Code)
	assert.Contains(t, response.Body.String(), `"fully_flattened":true`)
}

func TestEmergencyFlattenHandlerRequiresHaltedExecution(t *testing.T) {
	handler := NewEmergencyFlattenHandler(fakeEmergencyFlattener{err: orders.ErrExecutionNotHalted})
	request := httptest.NewRequest(http.MethodPost, "/emergency_flatten", strings.NewReader(
		`{"scope":"ALL","idempotency_key":"emergency-2"}`,
	))
	response := httptest.NewRecorder()

	handler(response, request)

	assert.Equal(t, http.StatusLocked, response.Code)
	assert.Contains(t, response.Body.String(), "requires halted execution")
}
