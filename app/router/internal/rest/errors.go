package rest

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// BinanceError represents an error response from Binance API
type BinanceError struct {
	Code       int    `json:"code"`
	Message    string `json:"msg"`
	HTTPStatus int    `json:"-"`
}

// Error implements the error interface
func (e *BinanceError) Error() string {
	return fmt.Sprintf("Binance API error %d: %s", e.Code, e.Message)
}

// IsRetryable determines if this error should trigger a retry
func (e *BinanceError) IsRetryable() bool {
	retryableCodes := map[int]bool{
		-1003: true, // Too many requests
		-1021: true, // Timestamp outside recv window
	}
	return retryableCodes[e.Code]
}

// IsAuthError checks if this is an authentication error
func (e *BinanceError) IsAuthError() bool {
	authCodes := map[int]bool{
		-1022: true, // Invalid signature
		-2014: true, // API key format invalid
		-2015: true, // Invalid API key, IP, or permissions
	}
	return authCodes[e.Code]
}

// IsRateLimitError checks if this is a rate limiting error
func (e *BinanceError) IsRateLimitError() bool {
	return e.Code == -1003
}

// IsOrderError checks if this is an order-related error
func (e *BinanceError) IsOrderError() bool {
	orderCodes := map[int]bool{
		-2010: true, // Account has insufficient balance
		-2011: true, // Unknown order sent
		-2013: true, // Order does not exist
	}
	return orderCodes[e.Code]
}

// ParseAPIError extracts and parses Binance API error from HTTP response
func ParseAPIError(resp *http.Response) error {
	if resp == nil {
		return fmt.Errorf("nil response")
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read error response: %w", err)
	}

	// Try to parse as Binance JSON error
	var binanceErr BinanceError
	jsonErr := json.Unmarshal(body, &binanceErr)

	// Check if it's a valid Binance error response
	if jsonErr == nil && binanceErr.Code != 0 {
		binanceErr.HTTPStatus = resp.StatusCode
		return &binanceErr
	}

	// If JSON parsing failed and response looks like JSON, report parsing error
	bodyStr := strings.TrimSpace(string(body))
	if jsonErr != nil && (strings.HasPrefix(bodyStr, "{") || strings.HasPrefix(bodyStr, "[")) {
		return fmt.Errorf("failed to parse error response: %w", jsonErr)
	}

	// Fallback for non-JSON responses
	if bodyStr == "" {
		bodyStr = "empty response"
	}

	return fmt.Errorf("HTTP %d: %s", resp.StatusCode, bodyStr)
}

// IsRetryableError determines if an error should trigger a retry
func IsRetryableError(err error) bool {
	if err == nil {
		return false
	}

	// Check for context errors (not retryable)
	if err == context.DeadlineExceeded || err == context.Canceled {
		return false
	}

	// Check for BinanceError
	var binanceErr *BinanceError
	if errors.As(err, &binanceErr) {
		return binanceErr.IsRetryable()
	}

	// Check for HTTP status in error message (for non-BinanceError cases)
	errMsg := err.Error()
	retryableStatuses := []string{
		"HTTP 429", // Too Many Requests
		"HTTP 500", // Internal Server Error
		"HTTP 502", // Bad Gateway
		"HTTP 503", // Service Unavailable
		"HTTP 504", // Gateway Timeout
	}

	for _, status := range retryableStatuses {
		if strings.Contains(errMsg, status) {
			return true
		}
	}

	return false
}

// ErrorWithContext wraps errors with operation context for better debugging
func ErrorWithContext(err error, operation string) error {
	if err == nil {
		return nil
	}

	return fmt.Errorf("%s: %w", operation, err)
}
