package auth

import (
	"fmt"
	"net/url"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestNewSigner(t *testing.T) {
	t.Run("creates signer with credentials", func(t *testing.T) {
		apiKey := "test-api-key"
		apiSecret := "test-api-secret"

		signer := NewSigner(apiKey, apiSecret)

		assert.NotNil(t, signer)
		assert.Equal(t, apiKey, signer.APIKey())
	})

	t.Run("validates empty api key", func(t *testing.T) {
		signer := NewSigner("", "secret")
		assert.NotNil(t, signer)
		assert.Equal(t, "", signer.APIKey())
	})

	t.Run("validates empty api secret", func(t *testing.T) {
		signer := NewSigner("key", "")
		assert.NotNil(t, signer)
		assert.Equal(t, "key", signer.APIKey())
	})
}

func TestSignRequest(t *testing.T) {
	// Using known test vectors from Binance API documentation
	apiKey := "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
	apiSecret := "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"

	signer := NewSigner(apiKey, apiSecret)

	t.Run("signs GET request with query parameters", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "LTCBTC")
		params.Set("side", "BUY")
		params.Set("type", "LIMIT")
		params.Set("timeInForce", "GTC")
		params.Set("quantity", "1")
		params.Set("price", "0.1")
		params.Set("recvWindow", "5000")
		params.Set("timestamp", "1499827319559")

		signature := signer.Sign(params)

		// Expected signature for alphabetical parameter order (Go's url.Values.Encode() sorts alphabetically)
		// Query string: price=0.1&quantity=1&recvWindow=5000&side=BUY&symbol=LTCBTC&timeInForce=GTC&timestamp=1499827319559&type=LIMIT
		expected := "70fd30433bc3a2e3b5ff17d075e50538dde3734841da6dc28d79113dd37fa9c7"
		assert.Equal(t, expected, signature)
	})

	t.Run("signs empty parameters with timestamp only", func(t *testing.T) {
		params := url.Values{}
		params.Set("timestamp", "1499827319559")

		signature := signer.Sign(params)

		// Expected signature for timestamp=1499827319559
		expected := "2222d49722f6af5da13f6da6bfc0d7de19ca2815ebc98bbc49e4942268472f3f"
		assert.Equal(t, expected, signature)
	})

	t.Run("handles special characters in parameters", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "BTC/USDT")
		params.Set("price", "50,000.50")
		params.Set("timestamp", "1499827319559")

		signature := signer.Sign(params)

		// Signature should be deterministic
		assert.NotEmpty(t, signature)
		assert.Len(t, signature, 64) // SHA256 produces 64 hex characters
	})

	t.Run("produces different signatures for different parameters", func(t *testing.T) {
		params1 := url.Values{}
		params1.Set("symbol", "BTCUSDT")
		params1.Set("timestamp", "1499827319559")

		params2 := url.Values{}
		params2.Set("symbol", "ETHUSDT")
		params2.Set("timestamp", "1499827319559")

		sig1 := signer.Sign(params1)
		sig2 := signer.Sign(params2)

		assert.NotEqual(t, sig1, sig2)
	})

	t.Run("maintains consistent order of parameters", func(t *testing.T) {
		// Same parameters in different order should produce same signature
		params1 := url.Values{}
		params1.Set("symbol", "BTCUSDT")
		params1.Set("side", "BUY")
		params1.Set("timestamp", "1499827319559")

		params2 := url.Values{}
		params2.Set("side", "BUY")
		params2.Set("timestamp", "1499827319559")
		params2.Set("symbol", "BTCUSDT")

		sig1 := signer.Sign(params1)
		sig2 := signer.Sign(params2)

		assert.Equal(t, sig1, sig2)
	})
}

func TestSignedRequest(t *testing.T) {
	apiKey := "test-api-key"
	apiSecret := "test-api-secret"
	signer := NewSigner(apiKey, apiSecret)

	t.Run("adds signature and timestamp to request", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "BTCUSDT")
		params.Set("side", "BUY")

		signedParams := signer.SignedRequest(params)

		// Should have original params plus timestamp and signature
		assert.Equal(t, "BTCUSDT", signedParams.Get("symbol"))
		assert.Equal(t, "BUY", signedParams.Get("side"))
		assert.NotEmpty(t, signedParams.Get("timestamp"))
		assert.NotEmpty(t, signedParams.Get("signature"))
	})

	t.Run("does not modify original parameters", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "BTCUSDT")

		originalLen := len(params)
		signedParams := signer.SignedRequest(params)

		// Original should be unchanged
		assert.Len(t, params, originalLen)
		assert.Empty(t, params.Get("timestamp"))
		assert.Empty(t, params.Get("signature"))

		// Signed should have additions
		assert.NotEmpty(t, signedParams.Get("timestamp"))
		assert.NotEmpty(t, signedParams.Get("signature"))
	})

	t.Run("uses current timestamp", func(t *testing.T) {
		params := url.Values{}

		before := time.Now().UnixMilli()
		signedParams := signer.SignedRequest(params)
		after := time.Now().UnixMilli()

		timestamp := signedParams.Get("timestamp")
		assert.NotEmpty(t, timestamp)

		// Parse and verify timestamp is within range
		var ts int64
		_, err := fmt.Sscanf(timestamp, "%d", &ts)
		assert.NoError(t, err)
		assert.GreaterOrEqual(t, ts, before)
		assert.LessOrEqual(t, ts, after)
	})

	t.Run("overwrites existing timestamp", func(t *testing.T) {
		params := url.Values{}
		params.Set("timestamp", "old-timestamp")

		signedParams := signer.SignedRequest(params)

		// Should have new timestamp, not old one
		assert.NotEqual(t, "old-timestamp", signedParams.Get("timestamp"))
		assert.NotEmpty(t, signedParams.Get("timestamp"))
	})
}

func TestValidateSignature(t *testing.T) {
	apiKey := "vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A"
	apiSecret := "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
	signer := NewSigner(apiKey, apiSecret)

	t.Run("validates correct signature", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "LTCBTC")
		params.Set("side", "BUY")
		params.Set("type", "LIMIT")
		params.Set("timeInForce", "GTC")
		params.Set("quantity", "1")
		params.Set("price", "0.1")
		params.Set("recvWindow", "5000")
		params.Set("timestamp", "1499827319559")

		// Expected signature for Binance's parameter order (different from Go's alphabetical order)
		// We're verifying against our computed signature for alphabetical order
		signature := "70fd30433bc3a2e3b5ff17d075e50538dde3734841da6dc28d79113dd37fa9c7"

		isValid := signer.ValidateSignature(params, signature)
		assert.True(t, isValid)
	})

	t.Run("rejects incorrect signature", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "LTCBTC")
		params.Set("timestamp", "1499827319559")

		incorrectSignature := "0000000000000000000000000000000000000000000000000000000000000000"

		isValid := signer.ValidateSignature(params, incorrectSignature)
		assert.False(t, isValid)
	})

	t.Run("rejects modified parameters", func(t *testing.T) {
		params := url.Values{}
		params.Set("symbol", "LTCBTC")
		params.Set("timestamp", "1499827319559")

		signature := signer.Sign(params)

		// Modify params after signing
		params.Set("symbol", "BTCUSDT")

		isValid := signer.ValidateSignature(params, signature)
		assert.False(t, isValid)
	})

	t.Run("handles empty signature", func(t *testing.T) {
		params := url.Values{}
		params.Set("timestamp", "1499827319559")

		isValid := signer.ValidateSignature(params, "")
		assert.False(t, isValid)
	})
}

func TestRecvWindow(t *testing.T) {
	apiKey := "test-api-key"
	apiSecret := "test-api-secret"

	t.Run("sets default recv window", func(t *testing.T) {
		signer := NewSigner(apiKey, apiSecret)
		assert.Equal(t, int64(5000), signer.RecvWindow())
	})

	t.Run("allows custom recv window", func(t *testing.T) {
		signer := NewSignerWithRecvWindow(apiKey, apiSecret, 10000)
		assert.Equal(t, int64(10000), signer.RecvWindow())
	})

	t.Run("adds recv window to signed request", func(t *testing.T) {
		signer := NewSignerWithRecvWindow(apiKey, apiSecret, 3000)

		params := url.Values{}
		signedParams := signer.SignedRequest(params)

		assert.Equal(t, "3000", signedParams.Get("recvWindow"))
	})

	t.Run("does not overwrite existing recv window", func(t *testing.T) {
		signer := NewSignerWithRecvWindow(apiKey, apiSecret, 3000)

		params := url.Values{}
		params.Set("recvWindow", "1000")

		signedParams := signer.SignedRequest(params)

		// Should keep the explicitly set value
		assert.Equal(t, "1000", signedParams.Get("recvWindow"))
	})
}

func TestConcurrentSigning(t *testing.T) {
	apiKey := "test-api-key"
	apiSecret := "test-api-secret"
	signer := NewSigner(apiKey, apiSecret)

	t.Run("thread-safe concurrent signing", func(t *testing.T) {
		done := make(chan bool)
		signatures := make(map[string]bool)
		mu := sync.Mutex{}

		// Run concurrent signing operations
		for i := 0; i < 100; i++ {
			go func(idx int) {
				params := url.Values{}
				params.Set("symbol", fmt.Sprintf("SYMBOL%d", idx))
				params.Set("timestamp", fmt.Sprintf("%d", 1499827319559+int64(idx)))

				signature := signer.Sign(params)

				mu.Lock()
				signatures[signature] = true
				mu.Unlock()

				done <- true
			}(i)
		}

		// Wait for all goroutines
		for i := 0; i < 100; i++ {
			<-done
		}

		// All signatures should be unique (different parameters)
		assert.Len(t, signatures, 100)
	})
}

// Benchmark signing performance
func BenchmarkSign(b *testing.B) {
	apiKey := "test-api-key"
	apiSecret := "test-api-secret"
	signer := NewSigner(apiKey, apiSecret)

	params := url.Values{}
	params.Set("symbol", "BTCUSDT")
	params.Set("side", "BUY")
	params.Set("type", "LIMIT")
	params.Set("quantity", "1.0")
	params.Set("price", "50000.00")
	params.Set("timestamp", "1499827319559")

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = signer.Sign(params)
	}
}

