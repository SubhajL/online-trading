package rest

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestBinanceError(t *testing.T) {
	t.Run("implements error interface", func(t *testing.T) {
		err := &BinanceError{
			Code:    -1021,
			Message: "Timestamp outside of recv window",
		}

		assert.Implements(t, (*error)(nil), err)
		assert.Equal(t, "Binance API error -1021: Timestamp outside of recv window", err.Error())
	})

	t.Run("indicates retryability", func(t *testing.T) {
		retryableErr := &BinanceError{
			Code:    -1003,
			Message: "Too many requests",
		}

		nonRetryableErr := &BinanceError{
			Code:    -2010,
			Message: "NEW_ORDER_REJECTED",
		}

		assert.True(t, retryableErr.IsRetryable())
		assert.False(t, nonRetryableErr.IsRetryable())
	})

	t.Run("categorizes error types", func(t *testing.T) {
		authErr := &BinanceError{Code: -1022, Message: "Invalid signature"}
		rateErr := &BinanceError{Code: -1003, Message: "Too many requests"}
		orderErr := &BinanceError{Code: -2010, Message: "Account has insufficient balance"}

		assert.True(t, authErr.IsAuthError())
		assert.True(t, rateErr.IsRateLimitError())
		assert.True(t, orderErr.IsOrderError())

		assert.False(t, authErr.IsRateLimitError())
		assert.False(t, rateErr.IsOrderError())
		assert.False(t, orderErr.IsAuthError())
	})
}

func TestParseAPIError(t *testing.T) {
	t.Run("parses valid binance error response", func(t *testing.T) {
		jsonResponse := `{"code":-1021,"msg":"Timestamp outside of recv window."}`
		resp := &http.Response{
			StatusCode: 400,
			Body:       io.NopCloser(strings.NewReader(jsonResponse)),
		}

		err := ParseAPIError(resp)

		assert.Error(t, err)

		var binanceErr *BinanceError
		assert.True(t, errors.As(err, &binanceErr))
		assert.Equal(t, -1021, binanceErr.Code)
		assert.Equal(t, "Timestamp outside of recv window.", binanceErr.Message)
		assert.Equal(t, 400, binanceErr.HTTPStatus)
	})

	t.Run("handles malformed json response", func(t *testing.T) {
		invalidJSON := `{"code":-1021,"msg":`
		resp := &http.Response{
			StatusCode: 400,
			Body:       io.NopCloser(strings.NewReader(invalidJSON)),
		}

		err := ParseAPIError(resp)

		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to parse error response")
	})

	t.Run("handles non-json error response", func(t *testing.T) {
		htmlResponse := `<html><body>Server Error</body></html>`
		resp := &http.Response{
			StatusCode: 500,
			Body:       io.NopCloser(strings.NewReader(htmlResponse)),
		}

		err := ParseAPIError(resp)

		assert.Error(t, err)
		assert.Contains(t, err.Error(), "HTTP 500")
		assert.Contains(t, err.Error(), "Server Error")
	})

	t.Run("handles empty response body", func(t *testing.T) {
		resp := &http.Response{
			StatusCode: 500,
			Body:       io.NopCloser(strings.NewReader("")),
		}

		err := ParseAPIError(resp)

		assert.Error(t, err)
		assert.Contains(t, err.Error(), "HTTP 500")
	})

	t.Run("handles read error", func(t *testing.T) {
		resp := &http.Response{
			StatusCode: 400,
			Body:       &errorReader{},
		}

		err := ParseAPIError(resp)

		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to read error response")
	})

	t.Run("parses different error codes correctly", func(t *testing.T) {
		testCases := []struct {
			code     int
			message  string
			expected bool // retryable
		}{
			{-1003, "Too many requests", true},
			{-1021, "Timestamp outside recv window", true},
			{-1022, "Invalid signature", false},
			{-2010, "Account has insufficient balance", false},
		}

		for _, tc := range testCases {
			jsonResponse := fmt.Sprintf(`{"code":%d,"msg":"%s"}`, tc.code, tc.message)
			resp := &http.Response{
				StatusCode: 400,
				Body:       io.NopCloser(strings.NewReader(jsonResponse)),
			}

			err := ParseAPIError(resp)
			var binanceErr *BinanceError
			assert.True(t, errors.As(err, &binanceErr))
			assert.Equal(t, tc.expected, binanceErr.IsRetryable())
		}
	})
}

func TestIsRetryableError(t *testing.T) {
	t.Run("identifies retryable binance errors", func(t *testing.T) {
		retryableErr := &BinanceError{Code: -1003, Message: "Too many requests"}
		nonRetryableErr := &BinanceError{Code: -2010, Message: "Account insufficient balance"}

		assert.True(t, IsRetryableError(retryableErr))
		assert.False(t, IsRetryableError(nonRetryableErr))
	})

	t.Run("identifies retryable http errors", func(t *testing.T) {
		// Simulate network errors that should be retried
		networkErr := &http.Response{
			StatusCode: 500,
			Body:       io.NopCloser(strings.NewReader("Internal Server Error")),
		}
		timeoutErr := &http.Response{
			StatusCode: 504,
			Body:       io.NopCloser(strings.NewReader("Gateway Timeout")),
		}
		serverErr := &http.Response{
			StatusCode: 502,
			Body:       io.NopCloser(strings.NewReader("Bad Gateway")),
		}

		// Convert to actual errors
		err500 := ParseAPIError(networkErr)
		err504 := ParseAPIError(timeoutErr)
		err502 := ParseAPIError(serverErr)

		assert.True(t, IsRetryableError(err500))
		assert.True(t, IsRetryableError(err504))
		assert.True(t, IsRetryableError(err502))
	})

	t.Run("identifies non-retryable client errors", func(t *testing.T) {
		clientErr := &http.Response{
			StatusCode: 400,
			Body:       io.NopCloser(strings.NewReader("Bad Request")),
		}
		unauthorizedErr := &http.Response{
			StatusCode: 401,
			Body:       io.NopCloser(strings.NewReader("Unauthorized")),
		}
		forbiddenErr := &http.Response{
			StatusCode: 403,
			Body:       io.NopCloser(strings.NewReader("Forbidden")),
		}

		err400 := ParseAPIError(clientErr)
		err401 := ParseAPIError(unauthorizedErr)
		err403 := ParseAPIError(forbiddenErr)

		assert.False(t, IsRetryableError(err400))
		assert.False(t, IsRetryableError(err401))
		assert.False(t, IsRetryableError(err403))
	})

	t.Run("handles context errors", func(t *testing.T) {
		timeoutErr := context.DeadlineExceeded
		cancelErr := context.Canceled

		assert.False(t, IsRetryableError(timeoutErr))
		assert.False(t, IsRetryableError(cancelErr))
	})

	t.Run("handles generic errors", func(t *testing.T) {
		genericErr := errors.New("some random error")
		assert.False(t, IsRetryableError(genericErr))
	})
}

func TestErrorWithContext(t *testing.T) {
	t.Run("wraps error with operation context", func(t *testing.T) {
		originalErr := errors.New("connection failed")
		wrappedErr := ErrorWithContext(originalErr, "GetOrderBook")

		assert.Error(t, wrappedErr)
		assert.Contains(t, wrappedErr.Error(), "GetOrderBook")
		assert.Contains(t, wrappedErr.Error(), "connection failed")
	})

	t.Run("preserves binance error type", func(t *testing.T) {
		originalErr := &BinanceError{
			Code:    -1021,
			Message: "Timestamp outside recv window",
		}

		wrappedErr := ErrorWithContext(originalErr, "PlaceOrder")

		assert.Error(t, wrappedErr)
		assert.Contains(t, wrappedErr.Error(), "PlaceOrder")

		// Should still be able to unwrap to BinanceError
		var binanceErr *BinanceError
		assert.True(t, errors.As(wrappedErr, &binanceErr))
		assert.Equal(t, -1021, binanceErr.Code)
	})

	t.Run("handles nil error", func(t *testing.T) {
		wrappedErr := ErrorWithContext(nil, "SomeOperation")
		assert.NoError(t, wrappedErr)
	})
}

func TestHTTPStatusErrors(t *testing.T) {
	t.Run("creates appropriate error for status codes", func(t *testing.T) {
		testCases := []struct {
			status    int
			retryable bool
		}{
			{200, false}, // Success shouldn't create error
			{400, false}, // Bad request
			{401, false}, // Unauthorized
			{403, false}, // Forbidden
			{429, true},  // Too many requests
			{500, true},  // Internal server error
			{502, true},  // Bad gateway
			{503, true},  // Service unavailable
			{504, true},  // Gateway timeout
		}

		for _, tc := range testCases {
			if tc.status == 200 {
				continue // Skip success case
			}

			resp := &http.Response{
				StatusCode: tc.status,
				Body:       io.NopCloser(strings.NewReader("Error message")),
			}

			err := ParseAPIError(resp)
			assert.Error(t, err)
			assert.Equal(t, tc.retryable, IsRetryableError(err), "Status %d should have retryable=%v", tc.status, tc.retryable)
		}
	})
}

// Helper type for testing read errors
type errorReader struct{}

func (e *errorReader) Read(p []byte) (n int, err error) {
	return 0, errors.New("read error")
}

func (e *errorReader) Close() error {
	return nil
}
