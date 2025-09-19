package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/url"
	"time"
)

// Signer handles HMAC-SHA256 signing for Binance API requests
type Signer struct {
	apiKey     string
	apiSecret  string
	recvWindow int64
}

// NewSigner creates a new signer with default recv window
func NewSigner(apiKey, apiSecret string) *Signer {
	return &Signer{
		apiKey:     apiKey,
		apiSecret:  apiSecret,
		recvWindow: 5000,
	}
}

// NewSignerWithRecvWindow creates a new signer with custom recv window
func NewSignerWithRecvWindow(apiKey, apiSecret string, recvWindow int64) *Signer {
	return &Signer{
		apiKey:     apiKey,
		apiSecret:  apiSecret,
		recvWindow: recvWindow,
	}
}

// APIKey returns the API key
func (s *Signer) APIKey() string {
	return s.apiKey
}

// RecvWindow returns the recv window value
func (s *Signer) RecvWindow() int64 {
	return s.recvWindow
}

// Sign generates HMAC-SHA256 signature for the given parameters
func (s *Signer) Sign(params url.Values) string {
	// Create the query string
	queryString := params.Encode()

	// Create HMAC with SHA256
	h := hmac.New(sha256.New, []byte(s.apiSecret))
	h.Write([]byte(queryString))

	// Return hex encoded signature
	return hex.EncodeToString(h.Sum(nil))
}

// SignedRequest adds timestamp and signature to parameters
func (s *Signer) SignedRequest(params url.Values) url.Values {
	// Create a copy of the parameters
	signedParams := make(url.Values)
	for key, values := range params {
		for _, value := range values {
			signedParams.Add(key, value)
		}
	}

	// Always set fresh timestamp
	signedParams.Set("timestamp", fmt.Sprintf("%d", time.Now().UnixMilli()))

	// Add recv window if not present
	if signedParams.Get("recvWindow") == "" {
		signedParams.Set("recvWindow", fmt.Sprintf("%d", s.recvWindow))
	}

	// Generate signature
	signature := s.Sign(signedParams)
	signedParams.Set("signature", signature)

	return signedParams
}

// ValidateSignature verifies if a signature is valid for given parameters
func (s *Signer) ValidateSignature(params url.Values, signature string) bool {
	expectedSignature := s.Sign(params)
	return hmac.Equal([]byte(expectedSignature), []byte(signature))
}
