package health

import (
	"context"
	"os"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
)

// IsCI returns true if running in CI environment
func IsCI() bool {
	return os.Getenv("CI") == "true" || os.Getenv("GITHUB_ACTIONS") == "true"
}

// GetTestBinanceClient returns appropriate Binance client for testing
func GetTestBinanceClient() BinanceClient {
	if IsCI() {
		// Return mock for CI
		return &mockBinanceClient{
			pingFunc: func(ctx context.Context) error {
				// Simulate successful ping
				return nil
			},
			getExchangeInfoFunc: func(ctx context.Context) (interface{}, error) {
				// Return minimal exchange info
				return map[string]interface{}{
					"timezone": "UTC",
					"serverTime": time.Now().UnixMilli(),
					"symbols": []interface{}{},
				}, nil
			},
		}
	}

	// For local/production, would return real Binance client
	// This would be imported from your actual Binance package
	// return binance.NewClient(...)

	// For now, return a simple implementation
	return &simpleBinanceClient{}
}

// GetTestRedisClient returns appropriate Redis client for testing
func GetTestRedisClient() RedisClient {
	if IsCI() {
		// In CI, connect to GitHub Actions Redis service
		rdb := redis.NewClient(&redis.Options{
			Addr: "localhost:6379",
			DB:   0,
		})
		return &redisClientWrapper{client: rdb}
	}

	// For local, connect to local Redis
	rdb := redis.NewClient(&redis.Options{
		Addr: "localhost:6379",
		DB:   0,
	})
	return &redisClientWrapper{client: rdb}
}

// MockBinanceClient is exported for testing
type MockBinanceClient struct {
	PingFunc            func(ctx context.Context) error
	GetExchangeInfoFunc func(ctx context.Context) (interface{}, error)
}

func (m *MockBinanceClient) Ping(ctx context.Context) error {
	if m.PingFunc != nil {
		return m.PingFunc(ctx)
	}
	return nil
}

func (m *MockBinanceClient) GetExchangeInfo(ctx context.Context) (interface{}, error) {
	if m.GetExchangeInfoFunc != nil {
		return m.GetExchangeInfoFunc(ctx)
	}
	return nil, nil
}

// MockRedisClient is exported for testing
type MockRedisClient struct {
	PingFunc func(ctx context.Context) error
	InfoFunc func(ctx context.Context, section string) (string, error)
}

func (m *MockRedisClient) Ping(ctx context.Context) error {
	if m.PingFunc != nil {
		return m.PingFunc(ctx)
	}
	return nil
}

func (m *MockRedisClient) Info(ctx context.Context, section string) (string, error) {
	if m.InfoFunc != nil {
		return m.InfoFunc(ctx, section)
	}
	return "", nil
}

// Mock implementation for CI only
type mockBinanceClient struct {
	pingFunc            func(ctx context.Context) error
	getExchangeInfoFunc func(ctx context.Context) (interface{}, error)
}

func (m *mockBinanceClient) Ping(ctx context.Context) error {
	if m.pingFunc != nil {
		return m.pingFunc(ctx)
	}
	return nil
}

func (m *mockBinanceClient) GetExchangeInfo(ctx context.Context) (interface{}, error) {
	if m.getExchangeInfoFunc != nil {
		return m.getExchangeInfoFunc(ctx)
	}
	return nil, nil
}

// Simple Binance client for local testing (would be replaced with real client)
type simpleBinanceClient struct{}

func (s *simpleBinanceClient) Ping(ctx context.Context) error {
	// In real implementation, this would ping actual Binance testnet
	// For now, simulate success
	return nil
}

func (s *simpleBinanceClient) GetExchangeInfo(ctx context.Context) (interface{}, error) {
	// In real implementation, this would call actual Binance API
	return map[string]interface{}{
		"timezone": "UTC",
		"serverTime": time.Now().UnixMilli(),
	}, nil
}

// Redis wrapper to implement our interface
type redisClientWrapper struct {
	client *redis.Client
}

func (r *redisClientWrapper) Ping(ctx context.Context) error {
	return r.client.Ping(ctx).Err()
}

func (r *redisClientWrapper) Info(ctx context.Context, section string) (string, error) {
	return r.client.Info(ctx, section).Result()
}

// rateLimitError represents a rate limit error
type rateLimitError struct {
	message string
}

func (e *rateLimitError) Error() string {
	return e.message
}

// NewRateLimitError creates a new rate limit error
func NewRateLimitError(message string) error {
	return &rateLimitError{message: message}
}

// IsRateLimitError checks if an error is a rate limit error
func IsRateLimitError(err error) bool {
	if err == nil {
		return false
	}
	return strings.Contains(err.Error(), "rate limit")
}