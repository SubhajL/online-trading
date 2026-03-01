package config

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestConfig_ValidateOptionalKeys(t *testing.T) {
	t.Run("validates spot-only configuration", func(t *testing.T) {
		// Set up spot-only environment
		t.Setenv("BINANCE_SPOT_API_KEY", "test-spot-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-spot-secret")
		t.Setenv("TRADING_MODE", "spot")

		config, err := Load()
		require.NoError(t, err)
		assert.NotNil(t, config)
		assert.Equal(t, "test-spot-key", config.Binance.SpotAPIKey)
		assert.Equal(t, "test-spot-secret", config.Binance.SpotSecretKey)
	})

	t.Run("validates futures-only configuration", func(t *testing.T) {
		// Set up futures-only environment
		t.Setenv("BINANCE_FUTURES_API_KEY", "test-futures-key")
		t.Setenv("BINANCE_FUTURES_SECRET_KEY", "test-futures-secret")
		t.Setenv("TRADING_MODE", "futures")

		config, err := Load()
		require.NoError(t, err)
		assert.NotNil(t, config)
		assert.Equal(t, "test-futures-key", config.Binance.FuturesAPIKey)
		assert.Equal(t, "test-futures-secret", config.Binance.FuturesSecretKey)
	})

	t.Run("validates both required when both trading modes enabled", func(t *testing.T) {
		// Set up both trading modes
		t.Setenv("BINANCE_SPOT_API_KEY", "test-spot-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-spot-secret")
		t.Setenv("BINANCE_FUTURES_API_KEY", "test-futures-key")
		t.Setenv("BINANCE_FUTURES_SECRET_KEY", "test-futures-secret")
		t.Setenv("TRADING_MODE", "spot,futures")

		config, err := Load()
		require.NoError(t, err)
		assert.NotNil(t, config)
		assert.Equal(t, "test-spot-key", config.Binance.SpotAPIKey)
		assert.Equal(t, "test-futures-key", config.Binance.FuturesAPIKey)
	})

	t.Run("validates error when spot keys missing for spot mode", func(t *testing.T) {
		// Set up spot mode without keys
		t.Setenv("TRADING_MODE", "spot")

		_, err := Load()
		require.Error(t, err)
		assert.Contains(t, err.Error(), "BINANCE_SPOT_API_KEY or BINANCE_API_KEY is required for spot trading")
	})

	t.Run("validates error when futures keys missing for futures mode", func(t *testing.T) {
		// Set up futures mode without keys
		t.Setenv("TRADING_MODE", "futures")

		_, err := Load()
		require.Error(t, err)
		assert.Contains(t, err.Error(), "BINANCE_FUTURES_API_KEY is required for futures trading")
	})
}

func TestBinanceConfig_TradingModes(t *testing.T) {
	t.Run("IsSpotEnabled returns true when spot mode is set", func(t *testing.T) {
		config := &BinanceConfig{TradingMode: "spot"}
		assert.True(t, config.IsSpotEnabled())
		assert.False(t, config.IsFuturesEnabled())
	})

	t.Run("IsFuturesEnabled returns true when futures mode is set", func(t *testing.T) {
		config := &BinanceConfig{TradingMode: "futures"}
		assert.False(t, config.IsSpotEnabled())
		assert.True(t, config.IsFuturesEnabled())
	})

	t.Run("both modes enabled when comma-separated", func(t *testing.T) {
		config := &BinanceConfig{TradingMode: "spot,futures"}
		assert.True(t, config.IsSpotEnabled())
		assert.True(t, config.IsFuturesEnabled())
	})

	t.Run("defaults to both modes when empty", func(t *testing.T) {
		config := &BinanceConfig{TradingMode: ""}
		assert.True(t, config.IsSpotEnabled())
		assert.True(t, config.IsFuturesEnabled())
	})
}

func TestBinanceConfig_ExecutionEnv(t *testing.T) {
	t.Run("defaults to testnet for safety", func(t *testing.T) {
		t.Setenv("ROUTER_EXECUTION_ENV", "")
		t.Setenv("BINANCE_SPOT_API_KEY", "test-spot-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-spot-secret")
		t.Setenv("TRADING_MODE", "spot")

		cfg, err := Load()
		require.NoError(t, err)
		assert.True(t, cfg.Binance.Testnet)
	})

	t.Run("mainnet execution env disables testnet URLs", func(t *testing.T) {
		t.Setenv("ROUTER_EXECUTION_ENV", "mainnet")
		t.Setenv("BINANCE_SPOT_API_KEY", "test-spot-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-spot-secret")
		t.Setenv("TRADING_MODE", "spot")

		cfg, err := Load()
		require.NoError(t, err)
		assert.False(t, cfg.Binance.Testnet)
	})

	t.Run("invalid execution env returns validation error", func(t *testing.T) {
		t.Setenv("ROUTER_EXECUTION_ENV", "banana")
		t.Setenv("BINANCE_SPOT_API_KEY", "test-spot-key")
		t.Setenv("BINANCE_SPOT_SECRET_KEY", "test-spot-secret")
		t.Setenv("TRADING_MODE", "spot")

		_, err := Load()
		require.Error(t, err)
		assert.Contains(t, err.Error(), "ROUTER_EXECUTION_ENV")
	})
}
