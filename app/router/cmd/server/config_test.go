package main

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func clearEnv(t *testing.T) {
	t.Helper()
	keys := []string{
		"PORT",
		"API_KEY",
		"API_SECRET",
		"TESTNET",
		"BINANCE_SPOT_API_KEY",
		"BINANCE_SPOT_SECRET_KEY",
		"BINANCE_SPOT_BASE_URL",
		"BINANCE_FUTURES_API_KEY",
		"BINANCE_FUTURES_SECRET_KEY",
		"BINANCE_FUTURES_BASE_URL",
		"RATE_LIMIT",
		"MAX_CONNECTIONS",
		"LOG_LEVEL",
		"CORS_ORIGINS",
		"READ_TIMEOUT",
		"WRITE_TIMEOUT",
		"IDLE_TIMEOUT",
	}
	for _, k := range keys {
		t.Setenv(k, "")
	}
}

func TestBinanceBaseURL(t *testing.T) {
	t.Run("returns testnet URL when testnet=true for spot", func(t *testing.T) {
		url := BinanceBaseURL(true, "spot")
		assert.Equal(t, BinanceSpotTestnetURL, url)
	})

	t.Run("returns prod URL when testnet=false for spot", func(t *testing.T) {
		url := BinanceBaseURL(false, "spot")
		assert.Equal(t, BinanceSpotProdURL, url)
	})

	t.Run("returns testnet URL when testnet=true for futures", func(t *testing.T) {
		url := BinanceBaseURL(true, "futures")
		assert.Equal(t, BinanceFuturesTestnetURL, url)
	})

	t.Run("returns prod URL when testnet=false for futures", func(t *testing.T) {
		url := BinanceBaseURL(false, "futures")
		assert.Equal(t, BinanceFuturesProdURL, url)
	})

	t.Run("handles USD_M as futures", func(t *testing.T) {
		url := BinanceBaseURL(true, "USD_M")
		assert.Equal(t, BinanceFuturesTestnetURL, url)
	})
}

func TestLoadConfig(t *testing.T) {
	t.Run("loads config from environment variables", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("PORT", "8080")
		t.Setenv("BINANCE_SPOT_API_KEY", "spot-key-123")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "spot-secret-123")
		t.Setenv("BINANCE_FUTURES_API_KEY", "futures-key-123")
		t.Setenv("BINANCE_FUTURES_SECRET_KEY", "futures-secret-123")
		t.Setenv("TESTNET", "true")
		t.Setenv("RATE_LIMIT", "100")
		t.Setenv("MAX_CONNECTIONS", "10")
		t.Setenv("LOG_LEVEL", "debug")
		t.Setenv("CORS_ORIGINS", "http://localhost:3000,https://example.com")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 8080, config.Port)
		assert.Equal(t, "spot-key-123", config.Spot.APIKey)
		assert.Equal(t, "spot-secret-123", config.Spot.SecretKey)
		assert.Equal(t, BinanceSpotTestnetURL, config.Spot.BaseURL)
		assert.Equal(t, "futures-key-123", config.Futures.APIKey)
		assert.Equal(t, "futures-secret-123", config.Futures.SecretKey)
		assert.Equal(t, BinanceFuturesTestnetURL, config.Futures.BaseURL)
		assert.True(t, config.Testnet)
		assert.Equal(t, 100, config.RateLimit)
		assert.Equal(t, "debug", config.LogLevel)
		assert.Contains(t, config.CORSOrigins, "http://localhost:3000")
		assert.Contains(t, config.CORSOrigins, "https://example.com")
	})

	t.Run("uses default values when env vars not set", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("BINANCE_SPOT_API_KEY", "required-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "required-secret")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 8080, config.Port)
		assert.Equal(t, 100, config.RateLimit)
		assert.Equal(t, "info", config.LogLevel)
		assert.Equal(t, 30*time.Second, config.ReadTimeout)
		assert.Equal(t, 30*time.Second, config.WriteTimeout)
		assert.True(t, config.Testnet) // Default to testnet
	})

	t.Run("returns error when spot API key is missing", func(t *testing.T) {
		clearEnv(t)

		_, err := LoadConfig()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "BINANCE_SPOT_API_KEY")
	})

	t.Run("falls back to legacy API_KEY", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("API_KEY", "legacy-key")
		t.Setenv("API_SECRET", "legacy-secret")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, "legacy-key", config.Spot.APIKey)
		assert.Equal(t, "legacy-secret", config.Spot.SecretKey)
	})

	t.Run("futures falls back to spot keys", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("BINANCE_SPOT_API_KEY", "spot-only-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "spot-only-secret")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, "spot-only-key", config.Futures.APIKey)
		assert.Equal(t, "spot-only-secret", config.Futures.SecretKey)
	})

	t.Run("validates port range", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("BINANCE_SPOT_API_KEY", "test-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-secret")
		t.Setenv("PORT", "70000")

		_, err := LoadConfig()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "port")
	})

	t.Run("parses timeout values", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("BINANCE_SPOT_API_KEY", "test-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-secret")
		t.Setenv("READ_TIMEOUT", "60")
		t.Setenv("WRITE_TIMEOUT", "120")
		t.Setenv("IDLE_TIMEOUT", "300")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 60*time.Second, config.ReadTimeout)
		assert.Equal(t, 120*time.Second, config.WriteTimeout)
		assert.Equal(t, 300*time.Second, config.IdleTimeout)
	})

	t.Run("sets testnet=false when explicitly disabled", func(t *testing.T) {
		clearEnv(t)

		t.Setenv("BINANCE_SPOT_API_KEY", "test-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-secret")
		t.Setenv("TESTNET", "false")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.False(t, config.Testnet)
		assert.Equal(t, BinanceSpotProdURL, config.Spot.BaseURL)
		assert.Equal(t, BinanceFuturesProdURL, config.Futures.BaseURL)
	})
}

func TestValidateConfig(t *testing.T) {
	t.Run("validates spot API key is required", func(t *testing.T) {
		config := &Config{
			Port:     8080,
			LogLevel: "info",
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "BINANCE_SPOT_API_KEY")
	})

	t.Run("validates spot secret key is required", func(t *testing.T) {
		config := &Config{
			Port:     8080,
			LogLevel: "info",
			Spot: BinanceConfig{
				APIKey: "key",
			},
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "BINANCE_SPOT_SECRET_KEY")
	})

	t.Run("validates port range", func(t *testing.T) {
		config := &Config{
			Port:     -1,
			LogLevel: "info",
			Spot: BinanceConfig{
				APIKey:    "key",
				SecretKey: "secret",
			},
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "port")

		config.Port = 70000
		err = ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "port")
	})

	t.Run("validates rate limit", func(t *testing.T) {
		config := &Config{
			Port:      8080,
			RateLimit: -1,
			LogLevel:  "info",
			Spot: BinanceConfig{
				APIKey:    "key",
				SecretKey: "secret",
			},
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "rate limit")
	})

	t.Run("validates log level", func(t *testing.T) {
		config := &Config{
			Port:     8080,
			LogLevel: "invalid",
			Spot: BinanceConfig{
				APIKey:    "key",
				SecretKey: "secret",
			},
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "log level")
	})

	t.Run("accepts valid config", func(t *testing.T) {
		config := &Config{
			Port:      8080,
			RateLimit: 100,
			LogLevel:  "info",
			Spot: BinanceConfig{
				APIKey:    "spot-key",
				SecretKey: "spot-secret",
			},
		}

		err := ValidateConfig(config)
		assert.NoError(t, err)
	})

	t.Run("collects all validation errors", func(t *testing.T) {
		config := &Config{
			Port:      -1,
			RateLimit: -1,
			LogLevel:  "invalid",
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "port")
		assert.Contains(t, err.Error(), "rate limit")
		assert.Contains(t, err.Error(), "log level")
		assert.Contains(t, err.Error(), "BINANCE_SPOT_API_KEY")
	})
}
