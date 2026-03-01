package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// BinanceConfig holds Binance exchange configuration
type BinanceConfig struct {
	APIKey    string
	SecretKey string
	BaseURL   string
}

// Config holds application configuration
type Config struct {
	Port           int
	APIKey         string
	RateLimit      int
	MaxConnections int
	LogLevel       string
	CORSOrigins    []string
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	IdleTimeout    time.Duration
	Version        string
	Testnet        bool
	Spot           BinanceConfig
	Futures        BinanceConfig
}

// Binance API URLs
const (
	BinanceSpotProdURL       = "https://api.binance.com"
	BinanceSpotTestnetURL    = "https://testnet.binance.vision"
	BinanceFuturesProdURL    = "https://fapi.binance.com"
	BinanceFuturesTestnetURL = "https://testnet.binancefuture.com"
)

// BinanceBaseURL returns the appropriate Binance base URL
func BinanceBaseURL(testnet bool, venue string) string {
	if venue == "futures" || venue == "USD_M" {
		if testnet {
			return BinanceFuturesTestnetURL
		}
		return BinanceFuturesProdURL
	}
	if testnet {
		return BinanceSpotTestnetURL
	}
	return BinanceSpotProdURL
}

// LoadConfig loads configuration from environment variables
func LoadConfig() (*Config, error) {
	config := &Config{
		// Default values
		Port:           8080,
		RateLimit:      100,
		MaxConnections: 50,
		LogLevel:       "info",
		ReadTimeout:    30 * time.Second,
		WriteTimeout:   30 * time.Second,
		IdleTimeout:    60 * time.Second,
		Version:        getVersion(),
		Testnet:        true, // Default to testnet for safety
	}

	// Load from environment
	if portStr := os.Getenv("PORT"); portStr != "" {
		port, err := strconv.Atoi(portStr)
		if err != nil {
			return nil, fmt.Errorf("invalid PORT value: %v", err)
		}
		config.Port = port
	}

	// Testnet mode
	if testnetStr := os.Getenv("TESTNET"); testnetStr != "" {
		config.Testnet = testnetStr == "true" || testnetStr == "1"
	}

	// Legacy API_KEY support (falls back to BINANCE_SPOT_API_KEY)
	config.APIKey = os.Getenv("API_KEY")

	// Binance Spot configuration
	config.Spot.APIKey = os.Getenv("BINANCE_SPOT_API_KEY")
	if config.Spot.APIKey == "" {
		config.Spot.APIKey = config.APIKey // Fallback to legacy API_KEY
	}
	config.Spot.SecretKey = os.Getenv("BINANCE_SPOT_SECRET_KEY")
	if config.Spot.SecretKey == "" {
		config.Spot.SecretKey = os.Getenv("API_SECRET") // Fallback
	}
	config.Spot.BaseURL = os.Getenv("BINANCE_SPOT_BASE_URL")
	if config.Spot.BaseURL == "" {
		config.Spot.BaseURL = BinanceBaseURL(config.Testnet, "spot")
	}

	// Binance Futures configuration
	config.Futures.APIKey = os.Getenv("BINANCE_FUTURES_API_KEY")
	if config.Futures.APIKey == "" {
		config.Futures.APIKey = config.Spot.APIKey // Fallback to spot keys
	}
	config.Futures.SecretKey = os.Getenv("BINANCE_FUTURES_SECRET_KEY")
	if config.Futures.SecretKey == "" {
		config.Futures.SecretKey = config.Spot.SecretKey // Fallback to spot keys
	}
	config.Futures.BaseURL = os.Getenv("BINANCE_FUTURES_BASE_URL")
	if config.Futures.BaseURL == "" {
		config.Futures.BaseURL = BinanceBaseURL(config.Testnet, "futures")
	}

	// Require at least spot API key
	if config.Spot.APIKey == "" {
		return nil, fmt.Errorf("BINANCE_SPOT_API_KEY environment variable is required")
	}

	if rateStr := os.Getenv("RATE_LIMIT"); rateStr != "" {
		rate, err := strconv.Atoi(rateStr)
		if err != nil {
			return nil, fmt.Errorf("invalid RATE_LIMIT value: %v", err)
		}
		config.RateLimit = rate
	}

	if maxConnStr := os.Getenv("MAX_CONNECTIONS"); maxConnStr != "" {
		maxConn, err := strconv.Atoi(maxConnStr)
		if err != nil {
			return nil, fmt.Errorf("invalid MAX_CONNECTIONS value: %v", err)
		}
		config.MaxConnections = maxConn
	}

	if logLevel := os.Getenv("LOG_LEVEL"); logLevel != "" {
		config.LogLevel = logLevel
	}

	if origins := os.Getenv("CORS_ORIGINS"); origins != "" {
		config.CORSOrigins = strings.Split(origins, ",")
		// Trim whitespace from each origin
		for i, origin := range config.CORSOrigins {
			config.CORSOrigins[i] = strings.TrimSpace(origin)
		}
	}

	// Parse timeout values
	if readTimeout := os.Getenv("READ_TIMEOUT"); readTimeout != "" {
		seconds, err := strconv.Atoi(readTimeout)
		if err != nil {
			return nil, fmt.Errorf("invalid READ_TIMEOUT value: %v", err)
		}
		config.ReadTimeout = time.Duration(seconds) * time.Second
	}

	if writeTimeout := os.Getenv("WRITE_TIMEOUT"); writeTimeout != "" {
		seconds, err := strconv.Atoi(writeTimeout)
		if err != nil {
			return nil, fmt.Errorf("invalid WRITE_TIMEOUT value: %v", err)
		}
		config.WriteTimeout = time.Duration(seconds) * time.Second
	}

	if idleTimeout := os.Getenv("IDLE_TIMEOUT"); idleTimeout != "" {
		seconds, err := strconv.Atoi(idleTimeout)
		if err != nil {
			return nil, fmt.Errorf("invalid IDLE_TIMEOUT value: %v", err)
		}
		config.IdleTimeout = time.Duration(seconds) * time.Second
	}

	// Validate configuration
	if err := ValidateConfig(config); err != nil {
		return nil, err
	}

	return config, nil
}

// ValidateConfig validates the configuration
func ValidateConfig(config *Config) error {
	var errors []string

	if config.Port <= 0 || config.Port > 65535 {
		errors = append(errors, fmt.Sprintf("invalid port number: %d", config.Port))
	}

	// Validate Binance Spot configuration
	if config.Spot.APIKey == "" {
		errors = append(errors, "BINANCE_SPOT_API_KEY is required")
	}
	if config.Spot.SecretKey == "" {
		errors = append(errors, "BINANCE_SPOT_SECRET_KEY is required")
	}

	if config.RateLimit < 0 {
		errors = append(errors, "rate limit must be non-negative")
	}

	if config.MaxConnections < 0 {
		errors = append(errors, "max connections must be non-negative")
	}

	// Validate log level
	validLogLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}

	if !validLogLevels[config.LogLevel] {
		errors = append(errors, fmt.Sprintf("invalid log level: %s", config.LogLevel))
	}

	if len(errors) > 0 {
		return fmt.Errorf("configuration validation failed: %s", strings.Join(errors, "; "))
	}

	return nil
}

// getVersion returns the application version
func getVersion() string {
	// Could be set via build flags: -ldflags "-X main.Version=1.0.0"
	if version := os.Getenv("VERSION"); version != "" {
		return version
	}
	return "1.0.0"
}
