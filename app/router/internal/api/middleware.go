package api

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"router/internal/models"
)

// RequestIDMiddleware generates or propagates request IDs for tracing
func RequestIDMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		requestID := c.GetHeader("X-Request-ID")
		if requestID == "" {
			// Generate UUID v4
			requestID = generateUUID()
		}

		c.Set("request_id", requestID)
		c.Header("X-Request-ID", requestID)
		c.Next()
	}
}

// LoggerMiddleware logs HTTP requests with configurable output
func LoggerMiddleware(output io.Writer) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		raw := c.Request.URL.RawQuery

		c.Next()

		latency := time.Since(start)
		clientIP := c.ClientIP()
		method := c.Request.Method
		statusCode := c.Writer.Status()

		if raw != "" {
			path = path + "?" + raw
		}

		logLine := fmt.Sprintf("%s | %3d | %13v | %15s | %-7s %#v | latency=%v\n",
			time.Now().Format("2006/01/02 - 15:04:05"),
			statusCode,
			latency,
			clientIP,
			method,
			path,
			latency,
		)

		output.Write([]byte(logLine))
	}
}

// AuthMiddleware validates API key authentication
func AuthMiddleware(apiKey string) gin.HandlerFunc {
	// Skip auth for these paths
	skipPaths := map[string]bool{
		"/health":  true,
		"/ready":   true,
		"/metrics": true,
		"/healthz": true,
		"/readyz":  true,
	}

	return func(c *gin.Context) {
		// Skip authentication for health check endpoints
		if skipPaths[c.Request.URL.Path] {
			c.Next()
			return
		}

		providedKey := c.GetHeader("X-API-Key")
		if providedKey == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, models.NewErrorResponse(
				"UNAUTHORIZED",
				"Missing API key",
				c.GetString("request_id"),
			))
			return
		}

		if providedKey != apiKey {
			c.AbortWithStatusJSON(http.StatusUnauthorized, models.NewErrorResponse(
				"UNAUTHORIZED",
				"Invalid API key",
				c.GetString("request_id"),
			))
			return
		}

		c.Next()
	}
}

// RateLimiter tracks request rates per client
type rateLimiter struct {
	clients         map[string]*clientRateInfo
	mu              sync.RWMutex
	rate            int
	window          time.Duration
	cleanupInterval time.Duration
	stopCleanup     chan bool
}

type clientRateInfo struct {
	tokens    int
	lastReset time.Time
}

// RateLimitMiddleware implements token bucket rate limiting per client IP
func RateLimitMiddleware(requestsPerWindow int, window time.Duration) gin.HandlerFunc {
	limiter := &rateLimiter{
		clients:         make(map[string]*clientRateInfo),
		rate:            requestsPerWindow,
		window:          window,
		cleanupInterval: window * 10,
		stopCleanup:     make(chan bool),
	}

	// Start cleanup goroutine
	go func() {
		ticker := time.NewTicker(limiter.cleanupInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				limiter.cleanup()
			case <-limiter.stopCleanup:
				return
			}
		}
	}()

	return func(c *gin.Context) {
		clientIP := getClientIP(c)

		limiter.mu.Lock()
		client, exists := limiter.clients[clientIP]
		if !exists || time.Since(client.lastReset) >= window {
			limiter.clients[clientIP] = &clientRateInfo{
				tokens:    requestsPerWindow - 1,
				lastReset: time.Now(),
			}
			limiter.mu.Unlock()

			c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", requestsPerWindow))
			c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", requestsPerWindow-1))
			c.Header("X-RateLimit-Reset", fmt.Sprintf("%d", time.Now().Add(window).Unix()))
			c.Next()
			return
		}

		if client.tokens <= 0 {
			limiter.mu.Unlock()

			c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", requestsPerWindow))
			c.Header("X-RateLimit-Remaining", "0")
			c.Header("X-RateLimit-Reset", fmt.Sprintf("%d", client.lastReset.Add(window).Unix()))

			c.JSON(http.StatusTooManyRequests, models.NewErrorResponse(
				"RATE_LIMITED",
				"Too many requests",
				c.GetString("request_id"),
			))
			c.Abort()
			return
		}

		client.tokens--
		remaining := client.tokens
		resetTime := client.lastReset.Add(window)
		limiter.mu.Unlock()

		c.Header("X-RateLimit-Limit", fmt.Sprintf("%d", requestsPerWindow))
		c.Header("X-RateLimit-Remaining", fmt.Sprintf("%d", remaining))
		c.Header("X-RateLimit-Reset", fmt.Sprintf("%d", resetTime.Unix()))
		c.Next()
	}
}

func (rl *rateLimiter) cleanup() {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	for ip, client := range rl.clients {
		if now.Sub(client.lastReset) > rl.window*2 {
			delete(rl.clients, ip)
		}
	}
}

// ErrorMiddleware handles panic recovery and error responses
func ErrorMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if err := recover(); err != nil {
				// Log the error (in production, this would go to a logger)
				fmt.Printf("Panic recovered: %v\n", err)

				c.JSON(http.StatusInternalServerError, models.NewErrorResponse(
					"INTERNAL_ERROR",
					"An internal server error occurred",
					c.GetString("request_id"),
				))
				c.Abort()
			}
		}()
		c.Next()
	}
}

// CORSConfig defines CORS middleware configuration
type CORSConfig struct {
	AllowOrigins     []string
	AllowMethods     []string
	AllowHeaders     []string
	ExposeHeaders    []string
	AllowCredentials bool
	MaxAge           int
}

// CORSMiddleware handles Cross-Origin Resource Sharing
func CORSMiddleware(config CORSConfig) gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")

		// Check if origin is allowed
		originAllowed := false
		allowedOrigin := ""
		for _, allowed := range config.AllowOrigins {
			if allowed == "*" || allowed == origin {
				originAllowed = true
				allowedOrigin = allowed
				break
			}
		}

		// Handle preflight request
		if c.Request.Method == "OPTIONS" {
			if originAllowed {
				c.Header("Access-Control-Allow-Origin", allowedOrigin)
				c.Header("Access-Control-Allow-Methods", strings.Join(config.AllowMethods, ", "))
				c.Header("Access-Control-Allow-Headers", strings.Join(config.AllowHeaders, ", "))
				if config.AllowCredentials {
					c.Header("Access-Control-Allow-Credentials", "true")
				}
				if config.MaxAge > 0 {
					c.Header("Access-Control-Max-Age", fmt.Sprintf("%d", config.MaxAge))
				}
			}
			c.Status(http.StatusNoContent)
			c.Abort()
			return
		}

		// Handle actual request
		if origin != "" && !originAllowed {
			c.JSON(http.StatusForbidden, models.NewErrorResponse(
				"CORS_ERROR",
				"Origin not allowed",
				c.GetString("request_id"),
			))
			c.Abort()
			return
		}

		if originAllowed {
			c.Header("Access-Control-Allow-Origin", allowedOrigin)
			if config.AllowCredentials {
				c.Header("Access-Control-Allow-Credentials", "true")
			}
			if len(config.ExposeHeaders) > 0 {
				c.Header("Access-Control-Expose-Headers", strings.Join(config.ExposeHeaders, ", "))
			}
		}

		c.Next()
	}
}

// TimeoutMiddleware sets a timeout for request processing
func TimeoutMiddleware(timeout time.Duration) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Create a context with timeout
		ctx, cancel := context.WithTimeout(c.Request.Context(), timeout)
		defer cancel()

		// Create channels to communicate between goroutines
		finished := make(chan struct{})
		panicChan := make(chan interface{}, 1)

		// Store original writer and replace with buffer
		w := c.Writer
		buffer := &responseBuffer{
			header: make(http.Header),
			body:   &bytes.Buffer{},
			code:   http.StatusOK,
			mu:     &sync.Mutex{},
		}
		c.Writer = buffer

		// Update request with timeout context
		c.Request = c.Request.WithContext(ctx)

		go func() {
			defer func() {
				if r := recover(); r != nil {
					panicChan <- r
				}
				close(finished)
			}()
			c.Next()
		}()

		select {
		case <-finished:
			// Handler completed successfully, write the buffered response
			c.Writer = w
			buffer.WriteTo(w)
		case p := <-panicChan:
			// Handler panicked, restore writer and propagate panic
			c.Writer = w
			panic(p)
		case <-ctx.Done():
			// Timeout occurred

			// Write timeout response to original writer
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusRequestTimeout)
			json.NewEncoder(w).Encode(models.NewErrorResponse(
				"REQUEST_TIMEOUT",
				"Request timeout exceeded",
				c.GetString("request_id"),
			))

			// Wait for handler goroutine to finish
			// This prevents the handler from continuing to execute after timeout
			<-finished

			// Restore the original writer and set a high abort index
			// to prevent any further middleware from running
			c.Writer = w
			c.AbortWithStatus(http.StatusRequestTimeout)
		}
	}
}

// responseBuffer captures the response for delayed writing
type responseBuffer struct {
	header http.Header
	body   *bytes.Buffer
	code   int
	mu     *sync.Mutex
}

func (r *responseBuffer) Header() http.Header {
	return r.header
}

func (r *responseBuffer) Write(b []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.body.Write(b)
}

func (r *responseBuffer) WriteHeader(code int) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.code = code
}

func (r *responseBuffer) WriteTo(w gin.ResponseWriter) {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Copy headers
	for k, v := range r.header {
		w.Header()[k] = v
	}
	// Write status code
	w.WriteHeader(r.code)
	// Write body
	w.Write(r.body.Bytes())
}

// Implement other required methods for gin.ResponseWriter
func (r *responseBuffer) WriteString(s string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.body.WriteString(s)
}

func (r *responseBuffer) Written() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.body.Len() > 0
}

func (r *responseBuffer) WriteHeaderNow() {}

func (r *responseBuffer) Status() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.code
}

func (r *responseBuffer) Size() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.body.Len()
}

func (r *responseBuffer) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	return nil, nil, fmt.Errorf("hijack not supported")
}

func (r *responseBuffer) CloseNotify() <-chan bool {
	return nil
}

func (r *responseBuffer) Flush() {}

func (r *responseBuffer) Pusher() http.Pusher {
	return nil
}

// ValidationMiddleware performs basic request validation
func ValidationMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Check Content-Type for requests with body
		if c.Request.Method == "POST" || c.Request.Method == "PUT" || c.Request.Method == "PATCH" {
			contentType := c.GetHeader("Content-Type")
			if contentType == "" || !strings.Contains(contentType, "application/json") {
				c.JSON(http.StatusBadRequest, models.NewErrorResponse(
					"INVALID_CONTENT_TYPE",
					"Content-Type must be application/json",
					c.GetString("request_id"),
				))
				c.Abort()
				return
			}
		}

		c.Next()
	}
}

// Helper functions

func generateUUID() string {
	// Simple UUID v4 generation
	b := make([]byte, 16)
	for i := range b {
		b[i] = byte(time.Now().UnixNano() + int64(i))
	}

	// Set version (4) and variant bits
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80

	return fmt.Sprintf("%x-%x-%x-%x-%x",
		b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

func getClientIP(c *gin.Context) string {
	// Extract IP from RemoteAddr, removing port
	host, _, err := net.SplitHostPort(c.Request.RemoteAddr)
	if err != nil {
		// RemoteAddr might not have port
		return c.Request.RemoteAddr
	}
	return host
}
