package rest

import (
	"context"
	"sync"
	"time"
)

// RateLimiter implements a token bucket rate limiter
type RateLimiter struct {
	rate  float64 // tokens per second
	burst int     // maximum number of tokens in bucket

	mu     sync.Mutex
	tokens float64   // current number of tokens
	last   time.Time // last time tokens were added
}

// NewRateLimiter creates a new token bucket rate limiter
func NewRateLimiter(requestsPerSecond float64, burst int) *RateLimiter {
	return &RateLimiter{
		rate:   requestsPerSecond,
		burst:  burst,
		tokens: float64(burst), // start with full bucket
		last:   time.Now(),
	}
}

// Rate returns the configured rate (tokens per second)
func (rl *RateLimiter) Rate() float64 {
	return rl.rate
}

// Burst returns the configured burst capacity
func (rl *RateLimiter) Burst() int {
	return rl.burst
}

// TryAcquire attempts to acquire a token without blocking
func (rl *RateLimiter) TryAcquire() bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	rl.refillTokens()

	if rl.tokens >= 1.0 {
		rl.tokens -= 1.0
		return true
	}

	return false
}

// Wait blocks until a token is available or context is cancelled
func (rl *RateLimiter) Wait(ctx context.Context) error {
	// Check if context is already cancelled
	if err := ctx.Err(); err != nil {
		return err
	}

	// Try to acquire immediately first
	if rl.TryAcquire() {
		return nil
	}

	// If rate is zero and no tokens available, we'll never get one
	if rl.rate == 0 {
		return context.DeadlineExceeded
	}

	// Calculate wait time for next token
	rl.mu.Lock()
	waitTime := time.Duration((1.0 / rl.rate) * float64(time.Second))
	rl.mu.Unlock()

	// Wait for either the timeout or context cancellation
	select {
	case <-time.After(waitTime):
		// Try to acquire after waiting
		if rl.TryAcquire() {
			return nil
		}
		// If still no token, keep trying with shorter waits
		return rl.Wait(ctx)
	case <-ctx.Done():
		return ctx.Err()
	}
}

// Reset restores the bucket to full capacity
func (rl *RateLimiter) Reset() {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	rl.tokens = float64(rl.burst)
	rl.last = time.Now()
}

// refillTokens adds tokens to the bucket based on elapsed time
// Must be called with mutex held
func (rl *RateLimiter) refillTokens() {
	now := time.Now()
	elapsed := now.Sub(rl.last).Seconds()

	// Add tokens based on elapsed time and rate
	tokensToAdd := elapsed * rl.rate
	rl.tokens += tokensToAdd

	// Cap at burst limit
	if rl.tokens > float64(rl.burst) {
		rl.tokens = float64(rl.burst)
	}

	rl.last = now
}
