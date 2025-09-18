package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

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
	}

	// Load from environment
	if portStr := os.Getenv("PORT"); portStr != "" {
		port, err := strconv.Atoi(portStr)
		if err != nil {
			return nil, fmt.Errorf("invalid PORT value: %v", err)
		}
		config.Port = port
	}

	config.APIKey = os.Getenv("API_KEY")
	if config.APIKey == "" {
		return nil, fmt.Errorf("API_KEY environment variable is required")
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
	if config.Port <= 0 || config.Port > 65535 {
		return fmt.Errorf("invalid port number: %d", config.Port)
	}

	if config.APIKey == "" {
		return fmt.Errorf("API key is required")
	}

	if config.RateLimit < 0 {
		return fmt.Errorf("rate limit must be non-negative")
	}

	if config.MaxConnections < 0 {
		return fmt.Errorf("max connections must be non-negative")
	}

	// Validate log level
	validLogLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}

	if !validLogLevels[config.LogLevel] {
		return fmt.Errorf("invalid log level: %s", config.LogLevel)
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