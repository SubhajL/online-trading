package rest

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestNewRateLimiter(t *testing.T) {
	t.Run("creates rate limiter with valid parameters", func(t *testing.T) {
		limiter := NewRateLimiter(10, 5)
		assert.NotNil(t, limiter)
		assert.Equal(t, 10.0, limiter.Rate())
		assert.Equal(t, 5, limiter.Burst())
	})

	t.Run("handles zero rate", func(t *testing.T) {
		limiter := NewRateLimiter(0, 1)
		assert.NotNil(t, limiter)
		assert.Equal(t, 0.0, limiter.Rate())
	})

	t.Run("handles zero burst", func(t *testing.T) {
		limiter := NewRateLimiter(10, 0)
		assert.NotNil(t, limiter)
		assert.Equal(t, 0, limiter.Burst())
	})

	t.Run("handles high rate values", func(t *testing.T) {
		limiter := NewRateLimiter(1000, 100)
		assert.NotNil(t, limiter)
		assert.Equal(t, 1000.0, limiter.Rate())
		assert.Equal(t, 100, limiter.Burst())
	})
}

func TestRateLimiter_AllowsBurstRequests(t *testing.T) {
	t.Run("allows burst requests immediately", func(t *testing.T) {
		// Create limiter with 10 req/sec, burst of 5
		limiter := NewRateLimiter(10, 5)

		// All burst requests should succeed immediately
		for i := 0; i < 5; i++ {
			allowed := limiter.TryAcquire()
			assert.True(t, allowed, "Burst request %d should be allowed", i+1)
		}
	})

	t.Run("blocks after burst is exhausted", func(t *testing.T) {
		limiter := NewRateLimiter(10, 3)

		// Use up the burst
		for i := 0; i < 3; i++ {
			assert.True(t, limiter.TryAcquire())
		}

		// Next request should be blocked
		allowed := limiter.TryAcquire()
		assert.False(t, allowed, "Request after burst should be blocked")
	})

	t.Run("burst works with zero rate", func(t *testing.T) {
		limiter := NewRateLimiter(0, 2)

		// Should allow burst requests even with zero rate
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.False(t, limiter.TryAcquire())
	})
}

func TestRateLimiter_ThrottlesExcessiveRequests(t *testing.T) {
	t.Run("blocks when exceeding rate limit", func(t *testing.T) {
		// Very low rate: 1 request per second, burst of 1
		limiter := NewRateLimiter(1, 1)

		// First request should succeed
		assert.True(t, limiter.TryAcquire())

		// Immediate second request should fail
		assert.False(t, limiter.TryAcquire())
	})

	t.Run("wait blocks until token available", func(t *testing.T) {
		// 5 req/sec, burst of 1
		limiter := NewRateLimiter(5, 1)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())

		// Wait should block but eventually succeed
		ctx := context.Background()
		start := time.Now()

		err := limiter.Wait(ctx)
		elapsed := time.Since(start)

		assert.NoError(t, err)
		// Should wait approximately 200ms (1/5 second)
		assert.Greater(t, elapsed, 100*time.Millisecond)
		assert.Less(t, elapsed, 400*time.Millisecond)
	})

	t.Run("wait with short timeout fails", func(t *testing.T) {
		limiter := NewRateLimiter(1, 1)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())

		// Context with very short timeout
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
		defer cancel()

		err := limiter.Wait(ctx)
		assert.Error(t, err)
		assert.Equal(t, context.DeadlineExceeded, err)
	})
}

func TestRateLimiter_RefillsTokensOverTime(t *testing.T) {
	t.Run("tokens refill at configured rate", func(t *testing.T) {
		// 10 req/sec, burst of 2
		limiter := NewRateLimiter(10, 2)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.False(t, limiter.TryAcquire())

		// Wait for tokens to refill (100ms should add 1 token at 10/sec)
		time.Sleep(120 * time.Millisecond)

		// Should be able to make at least one more request
		assert.True(t, limiter.TryAcquire())
	})

	t.Run("tokens accumulate up to burst limit", func(t *testing.T) {
		// 20 req/sec, burst of 3
		limiter := NewRateLimiter(20, 3)

		// Use one token
		assert.True(t, limiter.TryAcquire())

		// Wait long enough for multiple tokens to refill
		time.Sleep(200 * time.Millisecond)

		// Should be able to use full burst again
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.False(t, limiter.TryAcquire())
	})

	t.Run("refill respects fractional tokens", func(t *testing.T) {
		// 2.5 req/sec, burst of 1
		limiter := NewRateLimiter(2.5, 1)

		// Use the burst
		assert.True(t, limiter.TryAcquire())

		// Wait for partial refill (200ms = 0.5 tokens)
		time.Sleep(200 * time.Millisecond)
		assert.False(t, limiter.TryAcquire())

		// Wait for full token (400ms total = 1 token)
		time.Sleep(200 * time.Millisecond)
		assert.True(t, limiter.TryAcquire())
	})
}

func TestRateLimiter_RespectsContextCancellation(t *testing.T) {
	t.Run("wait returns on context cancellation", func(t *testing.T) {
		limiter := NewRateLimiter(1, 1)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())

		ctx, cancel := context.WithCancel(context.Background())

		// Start waiting in a goroutine
		errCh := make(chan error, 1)
		go func() {
			errCh <- limiter.Wait(ctx)
		}()

		// Cancel the context after a short delay
		time.Sleep(50 * time.Millisecond)
		cancel()

		// Wait should return with cancellation error
		select {
		case err := <-errCh:
			assert.Error(t, err)
			assert.Equal(t, context.Canceled, err)
		case <-time.After(100 * time.Millisecond):
			t.Fatal("Wait did not return after context cancellation")
		}
	})

	t.Run("wait with already cancelled context", func(t *testing.T) {
		limiter := NewRateLimiter(10, 1)

		ctx, cancel := context.WithCancel(context.Background())
		cancel() // Cancel immediately

		err := limiter.Wait(ctx)
		assert.Error(t, err)
		assert.Equal(t, context.Canceled, err)
	})

	t.Run("wait with deadline exceeded", func(t *testing.T) {
		limiter := NewRateLimiter(1, 1)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())

		// Context with deadline in the past
		ctx, cancel := context.WithDeadline(context.Background(), time.Now().Add(-time.Second))
		defer cancel()

		err := limiter.Wait(ctx)
		assert.Error(t, err)
		assert.Equal(t, context.DeadlineExceeded, err)
	})
}

func TestRateLimiter_ConcurrentAccess(t *testing.T) {
	t.Run("thread-safe under concurrent load", func(t *testing.T) {
		limiter := NewRateLimiter(100, 10)

		const numGoroutines = 50
		const requestsPerGoroutine = 10

		var wg sync.WaitGroup
		var mu sync.Mutex
		successCount := 0
		failureCount := 0

		// Launch concurrent goroutines
		for i := 0; i < numGoroutines; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()

				for j := 0; j < requestsPerGoroutine; j++ {
					if limiter.TryAcquire() {
						mu.Lock()
						successCount++
						mu.Unlock()
					} else {
						mu.Lock()
						failureCount++
						mu.Unlock()
					}
				}
			}()
		}

		wg.Wait()

		totalRequests := numGoroutines * requestsPerGoroutine
		assert.Equal(t, totalRequests, successCount+failureCount)

		// Some requests should succeed (at least the burst)
		assert.Greater(t, successCount, 0)

		// Most requests should fail due to rate limiting
		assert.Greater(t, failureCount, 0)
	})

	t.Run("concurrent wait operations", func(t *testing.T) {
		limiter := NewRateLimiter(5, 2)

		const numWaiters = 10
		var wg sync.WaitGroup
		var mu sync.Mutex
		successCount := 0

		// Use up the burst
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())

		// Launch concurrent wait operations
		for i := 0; i < numWaiters; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()

				ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
				defer cancel()

				if limiter.Wait(ctx) == nil {
					mu.Lock()
					successCount++
					mu.Unlock()
				}
			}()
		}

		wg.Wait()

		// Some waiters should succeed
		assert.Greater(t, successCount, 0)
		assert.LessOrEqual(t, successCount, numWaiters)
	})

	t.Run("no data races in mixed operations", func(t *testing.T) {
		limiter := NewRateLimiter(50, 5)

		const duration = 100 * time.Millisecond
		var wg sync.WaitGroup

		// TryAcquire goroutines
		for i := 0; i < 10; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()

				start := time.Now()
				for time.Since(start) < duration {
					limiter.TryAcquire()
					time.Sleep(time.Millisecond)
				}
			}()
		}

		// Wait goroutines
		for i := 0; i < 5; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()

				start := time.Now()
				for time.Since(start) < duration {
					ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
					limiter.Wait(ctx)
					cancel()
				}
			}()
		}

		wg.Wait()
		// Test passes if no race conditions detected
	})
}

func TestRateLimiter_EdgeCases(t *testing.T) {
	t.Run("extremely high rate", func(t *testing.T) {
		limiter := NewRateLimiter(1000000, 1000)

		// Should handle high rates without panic
		for i := 0; i < 100; i++ {
			assert.True(t, limiter.TryAcquire())
		}
	})

	t.Run("fractional rate", func(t *testing.T) {
		limiter := NewRateLimiter(0.5, 1) // 0.5 req/sec = 1 request per 2 seconds

		// First request should succeed
		assert.True(t, limiter.TryAcquire())

		// Second should fail immediately
		assert.False(t, limiter.TryAcquire())
	})

	t.Run("large burst with low rate", func(t *testing.T) {
		limiter := NewRateLimiter(1, 100)

		// Should allow large initial burst
		for i := 0; i < 100; i++ {
			assert.True(t, limiter.TryAcquire())
		}

		// Then block
		assert.False(t, limiter.TryAcquire())
	})
}

func TestRateLimiter_Reset(t *testing.T) {
	t.Run("reset restores full burst capacity", func(t *testing.T) {
		limiter := NewRateLimiter(10, 3)

		// Use up the burst
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.False(t, limiter.TryAcquire())

		// Reset should restore capacity
		limiter.Reset()

		// Should be able to use full burst again
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.True(t, limiter.TryAcquire())
		assert.False(t, limiter.TryAcquire())
	})
}

// Benchmark rate limiter performance
func BenchmarkRateLimiter_TryAcquire(b *testing.B) {
	limiter := NewRateLimiter(1000000, 1000) // High limits to avoid blocking

	b.ResetTimer()
	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			limiter.TryAcquire()
		}
	})
}

func BenchmarkRateLimiter_Wait(b *testing.B) {
	limiter := NewRateLimiter(1000000, 1000) // High limits to avoid blocking
	ctx := context.Background()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		limiter.Wait(ctx)
	}
}
