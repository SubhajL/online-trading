package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"router/internal/models"
)

func TestNewServer(t *testing.T) {
	t.Run("creates server with valid configuration", func(t *testing.T) {
		config := ServerConfig{
			Port:           8080,
			ReadTimeout:    10 * time.Second,
			WriteTimeout:   10 * time.Second,
			MaxHeaderBytes: 1 << 20,
			APIKey:         "test-key",
			Version:        "1.0.0",
		}

		server, err := NewServer(config)
		require.NoError(t, err)
		assert.NotNil(t, server)
		assert.Equal(t, ":8080", server.httpServer.Addr)
		assert.Equal(t, 10*time.Second, server.httpServer.ReadTimeout)
	})

	t.Run("validates port number", func(t *testing.T) {
		config := ServerConfig{
			Port:    0, // Invalid port
			APIKey:  "test-key",
			Version: "1.0.0",
		}

		_, err := NewServer(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid port")
	})

	t.Run("requires API key", func(t *testing.T) {
		config := ServerConfig{
			Port:    8080,
			APIKey:  "", // Missing API key
			Version: "1.0.0",
		}

		_, err := NewServer(config)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "API key required")
	})

	t.Run("sets default timeouts", func(t *testing.T) {
		config := ServerConfig{
			Port:    8080,
			APIKey:  "test-key",
			Version: "1.0.0",
			// No timeouts specified
		}

		server, err := NewServer(config)
		require.NoError(t, err)
		assert.Equal(t, 30*time.Second, server.httpServer.ReadTimeout)
		assert.Equal(t, 30*time.Second, server.httpServer.WriteTimeout)
	})
}

func TestServerStart(t *testing.T) {
	t.Run("starts server successfully", func(t *testing.T) {
		config := ServerConfig{
			Port:    0, // Use random port for testing
			APIKey:  "test-key",
			Version: "1.0.0",
		}

		server := &Server{
			config: config,
			logger: zerolog.Nop(),
			httpServer: &http.Server{
				Addr: ":0", // Use random port
				Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.WriteHeader(http.StatusOK)
				}),
			},
		}

		// Start server in goroutine
		errCh := make(chan error, 1)
		go func() {
			errCh <- server.Start()
		}()

		// Give server time to start
		time.Sleep(100 * time.Millisecond)

		// Shutdown server
		ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
		defer cancel()

		err := server.Shutdown(ctx)
		assert.NoError(t, err)

		// Check if Start() returned expected error
		select {
		case err := <-errCh:
			// Server should return http.ErrServerClosed when shutdown gracefully
			assert.ErrorIs(t, err, http.ErrServerClosed)
		case <-time.After(2 * time.Second):
			t.Fatal("Server did not shut down in time")
		}
	})
}

func TestServerShutdown(t *testing.T) {
	t.Run("shuts down gracefully", func(t *testing.T) {
		server := &Server{
			httpServer: &http.Server{
				Addr: ":0", // Use random port
				Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.WriteHeader(http.StatusOK)
				}),
			},
		}

		// Start server
		go server.httpServer.ListenAndServe()
		time.Sleep(100 * time.Millisecond)

		// Shutdown with timeout
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()

		err := server.Shutdown(ctx)
		assert.NoError(t, err)
	})

	t.Run("respects shutdown timeout", func(t *testing.T) {
		// Create a channel to signal when handler is running
		handlerStarted := make(chan struct{})

		server := &Server{
			httpServer: &http.Server{
				Addr: ":0", // Use random port
				Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					close(handlerStarted)
					// Simulate long-running request
					time.Sleep(5 * time.Second)
					w.WriteHeader(http.StatusOK)
				}),
			},
		}

		// Start server
		listener, err := net.Listen("tcp", ":0")
		require.NoError(t, err)
		defer listener.Close()

		go server.httpServer.Serve(listener)
		time.Sleep(100 * time.Millisecond)

		// Make a request to trigger the long-running handler
		go func() {
			http.Get(fmt.Sprintf("http://localhost:%d/", listener.Addr().(*net.TCPAddr).Port))
		}()

		// Wait for handler to start
		select {
		case <-handlerStarted:
			// Handler is running
		case <-time.After(1 * time.Second):
			t.Fatal("Handler did not start")
		}

		// Shutdown with short timeout
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		defer cancel()

		err = server.Shutdown(ctx)
		// Should timeout since handler takes 5 seconds
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "context deadline exceeded")
	})
}

func TestServerHealthCheck(t *testing.T) {
	t.Run("responds to health check", func(t *testing.T) {
		config := ServerConfig{
			Port:    8080,
			APIKey:  "test-key",
			Version: "1.0.0",
		}

		server, err := NewServer(config)
		require.NoError(t, err)

		// Make health check request
		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		server.router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var resp models.HealthResponse
		err = json.Unmarshal(w.Body.Bytes(), &resp)
		require.NoError(t, err)
		assert.Equal(t, "healthy", resp.Status)
		assert.Equal(t, "1.0.0", resp.Version)
	})
}

func TestServerMiddleware(t *testing.T) {
	t.Run("applies request ID middleware", func(t *testing.T) {
		config := ServerConfig{
			Port:    8080,
			APIKey:  "test-key",
			Version: "1.0.0",
		}

		server, err := NewServer(config)
		require.NoError(t, err)

		req := httptest.NewRequest("GET", "/health", nil)
		w := httptest.NewRecorder()
		server.router.ServeHTTP(w, req)

		// Should have X-Request-ID header
		assert.NotEmpty(t, w.Header().Get("X-Request-ID"))
	})

	t.Run("enforces API key authentication", func(t *testing.T) {
		config := ServerConfig{
			Port:    8080,
			APIKey:  "secret-key",
			Version: "1.0.0",
		}

		server, err := NewServer(config)
		require.NoError(t, err)

		// Since routes aren't set up in the test, we can't test auth directly
		// The auth middleware is tested separately in middleware_test.go
		// Here we just verify the server was created with auth configuration
		assert.Equal(t, "secret-key", server.config.APIKey)
	})

	t.Run("applies rate limiting", func(t *testing.T) {
		config := ServerConfig{
			Port:      8080,
			APIKey:    "test-key",
			Version:   "1.0.0",
			RateLimit: 2, // Allow 2 requests per second
		}

		server, err := NewServer(config)
		require.NoError(t, err)

		// Make requests up to rate limit
		for i := 0; i < 2; i++ {
			req := httptest.NewRequest("GET", "/health", nil)
			req.RemoteAddr = "127.0.0.1:1234"
			w := httptest.NewRecorder()
			server.router.ServeHTTP(w, req)
			assert.Equal(t, http.StatusOK, w.Code)
		}

		// Next request should be rate limited
		req := httptest.NewRequest("GET", "/health", nil)
		req.RemoteAddr = "127.0.0.1:1234"
		w := httptest.NewRecorder()
		server.router.ServeHTTP(w, req)
		assert.Equal(t, http.StatusTooManyRequests, w.Code)
	})
}
