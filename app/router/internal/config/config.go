package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds all configuration for the router service
type Config struct {
	Server   ServerConfig   `json:"server"`
	Binance  BinanceConfig  `json:"binance"`
	Redis    RedisConfig    `json:"redis"`
	Metrics  MetricsConfig  `json:"metrics"`
	Logging  LoggingConfig  `json:"logging"`
	Security SecurityConfig `json:"security"`
}

// ServerConfig holds HTTP server configuration
type ServerConfig struct {
	Port            int           `json:"port"`
	Host            string        `json:"host"`
	ReadTimeout     time.Duration `json:"read_timeout"`
	WriteTimeout    time.Duration `json:"write_timeout"`
	IdleTimeout     time.Duration `json:"idle_timeout"`
	ShutdownTimeout time.Duration `json:"shutdown_timeout"`
}

// BinanceConfig holds Binance API configuration
type BinanceConfig struct {
	// Spot API credentials
	SpotAPIKey    string `json:"spot_api_key"`
	SpotSecretKey string `json:"spot_secret_key"`

	// Futures API credentials
	FuturesAPIKey    string `json:"futures_api_key"`
	FuturesSecretKey string `json:"futures_secret_key"`

	// Legacy fields for backward compatibility
	APIKey          string        `json:"api_key"`
	SecretKey       string        `json:"secret_key"`
	BaseURL         string        `json:"base_url"`
	WSBaseURL       string        `json:"ws_base_url"`
	FuturesBaseURL  string        `json:"futures_base_url"`
	FuturesWSURL    string        `json:"futures_ws_url"`
	Testnet         bool          `json:"testnet"`
	Timeout         time.Duration `json:"timeout"`
	MaxRetries      int           `json:"max_retries"`
	RetryDelay      time.Duration `json:"retry_delay"`
	RateLimitDelay  time.Duration `json:"rate_limit_delay"`
	RecvWindow      int64         `json:"recv_window"`

	// Exchange info cache
	ExchangeInfoCacheTTL time.Duration `json:"exchange_info_cache_ttl"`
}

// RedisConfig holds Redis configuration
type RedisConfig struct {
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Password string `json:"password"`
	DB       int    `json:"db"`
	PoolSize int    `json:"pool_size"`
}

// MetricsConfig holds metrics configuration
type MetricsConfig struct {
	Enabled bool   `json:"enabled"`
	Path    string `json:"path"`
	Port    int    `json:"port"`
}

// LoggingConfig holds logging configuration
type LoggingConfig struct {
	Level      string `json:"level"`
	Format     string `json:"format"` // json or text
	Output     string `json:"output"` // stdout, stderr, or file path
	MaxSize    int    `json:"max_size"`    // MB
	MaxBackups int    `json:"max_backups"`
	MaxAge     int    `json:"max_age"` // days
}

// SecurityConfig holds security configuration
type SecurityConfig struct {
	APIKeyHeader     string        `json:"api_key_header"`
	RequiredAPIKey   string        `json:"required_api_key"`
	MaxRequestSize   int64         `json:"max_request_size"`
	RateLimit       int           `json:"rate_limit"`        // requests per minute
	RateLimitWindow time.Duration `json:"rate_limit_window"`
	AllowedOrigins  []string      `json:"allowed_origins"`
}

// Load loads configuration from environment variables
func Load() (*Config, error) {
	config := &Config{
		Server: ServerConfig{
			Port:            getEnvAsInt("SERVER_PORT", 8080),
			Host:            getEnv("SERVER_HOST", "0.0.0.0"),
			ReadTimeout:     getEnvAsDuration("SERVER_READ_TIMEOUT", "30s"),
			WriteTimeout:    getEnvAsDuration("SERVER_WRITE_TIMEOUT", "30s"),
			IdleTimeout:     getEnvAsDuration("SERVER_IDLE_TIMEOUT", "60s"),
			ShutdownTimeout: getEnvAsDuration("SERVER_SHUTDOWN_TIMEOUT", "10s"),
		},
		Binance: BinanceConfig{
			// Spot API credentials (fallback to legacy keys)
			SpotAPIKey:    getEnv("BINANCE_SPOT_API_KEY", getEnv("BINANCE_API_KEY", "")),
			SpotSecretKey: getEnv("BINANCE_SPOT_SECRET_KEY", getEnv("BINANCE_SECRET_KEY", "")),

			// Futures API credentials
			FuturesAPIKey:    getEnv("BINANCE_FUTURES_API_KEY", ""),
			FuturesSecretKey: getEnv("BINANCE_FUTURES_SECRET_KEY", ""),

			// Legacy fields
			APIKey:          getEnv("BINANCE_API_KEY", ""),
			SecretKey:       getEnv("BINANCE_SECRET_KEY", ""),
			BaseURL:         getEnv("BINANCE_BASE_URL", "https://api.binance.com"),
			WSBaseURL:       getEnv("BINANCE_WS_BASE_URL", "wss://stream.binance.com:9443"),
			FuturesBaseURL:  getEnv("BINANCE_FUTURES_BASE_URL", "https://fapi.binance.com"),
			FuturesWSURL:    getEnv("BINANCE_FUTURES_WS_URL", "wss://fstream.binance.com"),
			Testnet:         getEnvAsBool("BINANCE_TESTNET", false),
			Timeout:         getEnvAsDuration("BINANCE_TIMEOUT", "30s"),
			MaxRetries:      getEnvAsInt("BINANCE_MAX_RETRIES", 3),
			RetryDelay:      getEnvAsDuration("BINANCE_RETRY_DELAY", "1s"),
			RateLimitDelay:  getEnvAsDuration("BINANCE_RATE_LIMIT_DELAY", "100ms"),
			RecvWindow:      getEnvAsInt64("BINANCE_RECV_WINDOW", 5000),

			// Cache settings
			ExchangeInfoCacheTTL: getEnvAsDuration("EXCHANGE_INFO_CACHE_TTL", "5m"),
		},
		Redis: RedisConfig{
			Host:     getEnv("REDIS_HOST", "localhost"),
			Port:     getEnvAsInt("REDIS_PORT", 6379),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getEnvAsInt("REDIS_DB", 0),
			PoolSize: getEnvAsInt("REDIS_POOL_SIZE", 10),
		},
		Metrics: MetricsConfig{
			Enabled: getEnvAsBool("METRICS_ENABLED", true),
			Path:    getEnv("METRICS_PATH", "/metrics"),
			Port:    getEnvAsInt("METRICS_PORT", 9090),
		},
		Logging: LoggingConfig{
			Level:      getEnv("LOG_LEVEL", "info"),
			Format:     getEnv("LOG_FORMAT", "json"),
			Output:     getEnv("LOG_OUTPUT", "stdout"),
			MaxSize:    getEnvAsInt("LOG_MAX_SIZE", 100),
			MaxBackups: getEnvAsInt("LOG_MAX_BACKUPS", 5),
			MaxAge:     getEnvAsInt("LOG_MAX_AGE", 30),
		},
		Security: SecurityConfig{
			APIKeyHeader:     getEnv("SECURITY_API_KEY_HEADER", "X-API-Key"),
			RequiredAPIKey:   getEnv("SECURITY_REQUIRED_API_KEY", ""),
			MaxRequestSize:   getEnvAsInt64("SECURITY_MAX_REQUEST_SIZE", 1048576), // 1MB
			RateLimit:       getEnvAsInt("SECURITY_RATE_LIMIT", 1000),
			RateLimitWindow: getEnvAsDuration("SECURITY_RATE_LIMIT_WINDOW", "1m"),
			AllowedOrigins:  getEnvAsSlice("SECURITY_ALLOWED_ORIGINS", []string{"*"}),
		},
	}

	// Validate required configuration
	if err := config.Validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return config, nil
}

// Validate validates the configuration
func (c *Config) Validate() error {
	// Check Spot API credentials
	if c.Binance.SpotAPIKey == "" {
		return fmt.Errorf("BINANCE_SPOT_API_KEY is required")
	}
	if c.Binance.SpotSecretKey == "" {
		return fmt.Errorf("BINANCE_SPOT_SECRET_KEY is required")
	}

	// Check Futures API credentials
	if c.Binance.FuturesAPIKey == "" {
		return fmt.Errorf("BINANCE_FUTURES_API_KEY is required")
	}
	if c.Binance.FuturesSecretKey == "" {
		return fmt.Errorf("BINANCE_FUTURES_SECRET_KEY is required")
	}

	if c.Server.Port <= 0 || c.Server.Port > 65535 {
		return fmt.Errorf("invalid server port: %d", c.Server.Port)
	}
	if c.Redis.Port <= 0 || c.Redis.Port > 65535 {
		return fmt.Errorf("invalid redis port: %d", c.Redis.Port)
	}
	return nil
}

// GetBinanceTestnetURLs returns testnet URLs if testnet is enabled
func (c *Config) GetBinanceTestnetURLs() {
	if c.Binance.Testnet {
		c.Binance.BaseURL = "https://testnet.binance.vision"
		c.Binance.WSBaseURL = "wss://testnet.binance.vision"
		c.Binance.FuturesBaseURL = "https://testnet.binancefuture.com"
		c.Binance.FuturesWSURL = "wss://stream.binancefuture.com"
	}
}

// Helper functions for environment variable parsing

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if intValue, err := strconv.Atoi(value); err == nil {
			return intValue
		}
	}
	return defaultValue
}

func getEnvAsInt64(key string, defaultValue int64) int64 {
	if value := os.Getenv(key); value != "" {
		if int64Value, err := strconv.ParseInt(value, 10, 64); err == nil {
			return int64Value
		}
	}
	return defaultValue
}

func getEnvAsBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		if boolValue, err := strconv.ParseBool(value); err == nil {
			return boolValue
		}
	}
	return defaultValue
}

func getEnvAsDuration(key string, defaultValue string) time.Duration {
	if value := os.Getenv(key); value != "" {
		if duration, err := time.ParseDuration(value); err == nil {
			return duration
		}
	}
	duration, _ := time.ParseDuration(defaultValue)
	return duration
}

func getEnvAsSlice(key string, defaultValue []string) []string {
	if value := os.Getenv(key); value != "" {
		return strings.Split(value, ",")
	}
	return defaultValue
}