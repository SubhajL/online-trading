package orders

import (
	"fmt"
	"strings"
)

// BracketOrderError represents an error during bracket order placement
type BracketOrderError struct {
	BracketID string
	Symbol    string
	Errors    []OrderError
}

// OrderError represents a single order error within a bracket
type OrderError struct {
	OrderType string // "MAIN", "TP1", "TP2", "SL", etc.
	Error     error
}

// Error implements the error interface
func (e *BracketOrderError) Error() string {
	if len(e.Errors) == 0 {
		return "bracket order error with no details"
	}

	var parts []string
	parts = append(parts, fmt.Sprintf("bracket order %s failed:", e.BracketID[:8]))

	for _, err := range e.Errors {
		parts = append(parts, fmt.Sprintf("%s: %v", err.OrderType, err.Error))
	}

	return strings.Join(parts, "; ")
}

// Add adds a new error to the bracket order error
func (e *BracketOrderError) Add(orderType string, err error) {
	if err != nil {
		e.Errors = append(e.Errors, OrderError{
			OrderType: orderType,
			Error:     err,
		})
	}
}

// HasErrors returns true if there are any errors
func (e *BracketOrderError) HasErrors() bool {
	return len(e.Errors) > 0
}

// HasCriticalError returns true if the main order failed
func (e *BracketOrderError) HasCriticalError() bool {
	for _, err := range e.Errors {
		if err.OrderType == "MAIN" {
			return true
		}
	}
	return false
}

// NewBracketOrderError creates a new bracket order error
func NewBracketOrderError(bracketID, symbol string) *BracketOrderError {
	return &BracketOrderError{
		BracketID: bracketID,
		Symbol:    symbol,
		Errors:    make([]OrderError, 0),
	}
}
