package main

import (
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestLoadConfig(t *testing.T) {
	t.Run("loads config from environment variables", func(t *testing.T) {
		// Set environment variables
		os.Setenv("PORT", "8080")
		os.Setenv("API_KEY", "test-key-123")
		os.Setenv("RATE_LIMIT", "100")
		os.Setenv("MAX_CONNECTIONS", "10")
		os.Setenv("LOG_LEVEL", "debug")
		os.Setenv("CORS_ORIGINS", "http://localhost:3000,https://example.com")
		defer func() {
			os.Unsetenv("PORT")
			os.Unsetenv("API_KEY")
			os.Unsetenv("RATE_LIMIT")
			os.Unsetenv("MAX_CONNECTIONS")
			os.Unsetenv("LOG_LEVEL")
			os.Unsetenv("CORS_ORIGINS")
		}()

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 8080, config.Port)
		assert.Equal(t, "test-key-123", config.APIKey)
		assert.Equal(t, 100, config.RateLimit)
		assert.Equal(t, "debug", config.LogLevel)
		assert.Contains(t, config.CORSOrigins, "http://localhost:3000")
		assert.Contains(t, config.CORSOrigins, "https://example.com")
	})

	t.Run("uses default values when env vars not set", func(t *testing.T) {
		// Clear any existing env vars
		os.Unsetenv("PORT")
		os.Unsetenv("RATE_LIMIT")
		os.Unsetenv("LOG_LEVEL")

		// API_KEY is required
		os.Setenv("API_KEY", "required-key")
		defer os.Unsetenv("API_KEY")

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 8080, config.Port) // Default port
		assert.Equal(t, 100, config.RateLimit) // Default rate limit
		assert.Equal(t, "info", config.LogLevel) // Default log level
		assert.Equal(t, 30*time.Second, config.ReadTimeout)
		assert.Equal(t, 30*time.Second, config.WriteTimeout)
	})

	t.Run("returns error when API key is missing", func(t *testing.T) {
		os.Unsetenv("API_KEY")

		_, err := LoadConfig()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "API_KEY")
	})

	t.Run("validates port range", func(t *testing.T) {
		os.Setenv("API_KEY", "test-key")
		defer os.Unsetenv("API_KEY")

		// Test invalid port
		os.Setenv("PORT", "70000")
		defer os.Unsetenv("PORT")

		_, err := LoadConfig()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "port")
	})

	t.Run("parses timeout values", func(t *testing.T) {
		os.Setenv("API_KEY", "test-key")
		os.Setenv("READ_TIMEOUT", "60")
		os.Setenv("WRITE_TIMEOUT", "120")
		os.Setenv("IDLE_TIMEOUT", "300")
		defer func() {
			os.Unsetenv("API_KEY")
			os.Unsetenv("READ_TIMEOUT")
			os.Unsetenv("WRITE_TIMEOUT")
			os.Unsetenv("IDLE_TIMEOUT")
		}()

		config, err := LoadConfig()
		require.NoError(t, err)

		assert.Equal(t, 60*time.Second, config.ReadTimeout)
		assert.Equal(t, 120*time.Second, config.WriteTimeout)
		assert.Equal(t, 300*time.Second, config.IdleTimeout)
	})
}

func TestValidateConfig(t *testing.T) {
	t.Run("validates required fields", func(t *testing.T) {
		config := &Config{
			Port: 8080,
			// Missing API key
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "API key")
	})

	t.Run("validates port range", func(t *testing.T) {
		config := &Config{
			Port:   -1,
			APIKey: "test",
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
			APIKey:    "test",
			RateLimit: -1,
		}

		err := ValidateConfig(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "rate limit")
	})

	t.Run("accepts valid config", func(t *testing.T) {
		config := &Config{
			Port:      8080,
			APIKey:    "test-key",
			RateLimit: 100,
		}

		err := ValidateConfig(config)
		assert.NoError(t, err)
	})
}