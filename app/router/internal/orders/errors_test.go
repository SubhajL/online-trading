package orders

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestBracketOrderError(t *testing.T) {
	tests := []struct {
		name           string
		bracketID      string
		symbol         string
		errors         []OrderError
		expectedString string
		hasErrors      bool
		hasCritical    bool
	}{
		{
			name:           "no errors",
			bracketID:      "12345678-1234-1234-1234-123456789012",
			symbol:         "BTCUSDT",
			errors:         []OrderError{},
			expectedString: "bracket order error with no details",
			hasErrors:      false,
			hasCritical:    false,
		},
		{
			name:      "single error",
			bracketID: "12345678-1234-1234-1234-123456789012",
			symbol:    "BTCUSDT",
			errors: []OrderError{
				{OrderType: "TP1", Error: errors.New("insufficient balance")},
			},
			expectedString: "bracket order 12345678 failed:; TP1: insufficient balance",
			hasErrors:      true,
			hasCritical:    false,
		},
		{
			name:      "multiple errors",
			bracketID: "12345678-1234-1234-1234-123456789012",
			symbol:    "BTCUSDT",
			errors: []OrderError{
				{OrderType: "TP1", Error: errors.New("insufficient balance")},
				{OrderType: "TP2", Error: errors.New("invalid price")},
				{OrderType: "SL", Error: errors.New("quantity too small")},
			},
			expectedString: "bracket order 12345678 failed:; TP1: insufficient balance; TP2: invalid price; SL: quantity too small",
			hasErrors:      true,
			hasCritical:    false,
		},
		{
			name:      "critical error",
			bracketID: "12345678-1234-1234-1234-123456789012",
			symbol:    "BTCUSDT",
			errors: []OrderError{
				{OrderType: "MAIN", Error: errors.New("insufficient margin")},
			},
			expectedString: "bracket order 12345678 failed:; MAIN: insufficient margin",
			hasErrors:      true,
			hasCritical:    true,
		},
		{
			name:      "mixed errors with critical",
			bracketID: "12345678-1234-1234-1234-123456789012",
			symbol:    "BTCUSDT",
			errors: []OrderError{
				{OrderType: "MAIN", Error: errors.New("insufficient margin")},
				{OrderType: "TP1", Error: errors.New("invalid price")},
			},
			expectedString: "bracket order 12345678 failed:; MAIN: insufficient margin; TP1: invalid price",
			hasErrors:      true,
			hasCritical:    true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := NewBracketOrderError(tt.bracketID, tt.symbol)
			for _, e := range tt.errors {
				err.Add(e.OrderType, e.Error)
			}

			assert.Equal(t, tt.expectedString, err.Error())
			assert.Equal(t, tt.hasErrors, err.HasErrors())
			assert.Equal(t, tt.hasCritical, err.HasCriticalError())
		})
	}
}

func TestBracketOrderError_Add(t *testing.T) {
	err := NewBracketOrderError("12345678", "BTCUSDT")

	// Add nil error should not add anything
	err.Add("TP1", nil)
	assert.Equal(t, 0, len(err.Errors))

	// Add valid error
	err.Add("TP1", errors.New("test error"))
	assert.Equal(t, 1, len(err.Errors))
	assert.Equal(t, "TP1", err.Errors[0].OrderType)
	assert.Equal(t, "test error", err.Errors[0].Error.Error())

	// Add another error
	err.Add("SL", errors.New("another error"))
	assert.Equal(t, 2, len(err.Errors))
}