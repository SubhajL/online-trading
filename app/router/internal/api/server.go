package api

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/rs/zerolog"
	"router/internal/handlers"
	"router/internal/metrics"
)

// ServerConfig contains server configuration
type ServerConfig struct {
	Port           int
	ReadTimeout    time.Duration
	WriteTimeout   time.Duration
	IdleTimeout    time.Duration
	MaxHeaderBytes int
	APIKey         string
	Version        string
	RateLimit      int           // Requests per second
	RateWindow     time.Duration // Rate limit window
	CORSOrigins    []string
	LogLevel       string
}

// Server represents the API server
type Server struct {
	config     ServerConfig
	router     *gin.Engine
	httpServer *http.Server
	logger     zerolog.Logger
	startTime  time.Time

	// Handler dependencies (will be injected)
	streamManager       handlers.StreamManager
	subscriptionManager handlers.SubscriptionManager
	configManager       handlers.ConfigManager
	readinessChecker    handlers.ReadinessChecker
	metricsCollector    handlers.MetricsCollector

	// Internal metrics collector interface for middleware
	internalMetricsCollector metrics.MetricsCollectorInterface
}

// NewServer creates a new API server
func NewServer(config ServerConfig) (*Server, error) {
	// Validate configuration
	if err := validateConfig(&config); err != nil {
		return nil, err
	}

	// Set defaults
	setConfigDefaults(&config)

	// Configure logger
	logger := setupLogger(config.LogLevel)

	// Setup Gin
	if config.LogLevel == "debug" {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	// Create router with recovery middleware
	router := gin.New()
	router.Use(gin.Recovery())

	// Create server
	server := &Server{
		config:    config,
		router:    router,
		logger:    logger,
		startTime: time.Now(),
	}

	// Setup middleware
	server.setupMiddleware()

	// Setup basic routes (health check only)
	server.setupBasicRoutes()

	// Create HTTP server
	server.httpServer = &http.Server{
		Addr:           fmt.Sprintf(":%d", config.Port),
		Handler:        router,
		ReadTimeout:    config.ReadTimeout,
		WriteTimeout:   config.WriteTimeout,
		IdleTimeout:    config.IdleTimeout,
		MaxHeaderBytes: config.MaxHeaderBytes,
	}

	return server, nil
}

// MetricsCollectorWithInternal defines interface for metrics collector that provides internal access
type MetricsCollectorWithInternal interface {
	handlers.MetricsCollector
	GetCollector() *metrics.Collector
}

// SetDependencies sets the handler dependencies
func (s *Server) SetDependencies(
	streamManager handlers.StreamManager,
	subscriptionManager handlers.SubscriptionManager,
	configManager handlers.ConfigManager,
	readinessChecker handlers.ReadinessChecker,
	metricsCollector handlers.MetricsCollector,
) {
	s.streamManager = streamManager
	s.subscriptionManager = subscriptionManager
	s.configManager = configManager
	s.readinessChecker = readinessChecker
	s.metricsCollector = metricsCollector

	// Try to get internal collector for middleware
	if collectorWithInternal, ok := metricsCollector.(MetricsCollectorWithInternal); ok {
		s.internalMetricsCollector = collectorWithInternal.GetCollector()

		// Add metrics middleware to router
		s.router.Use(metrics.MetricsMiddleware(s.internalMetricsCollector))
	}

	// Re-setup routes with actual handlers
	s.setupRoutes()
}

// Start starts the API server
func (s *Server) Start() error {
	s.logger.Info().
		Int("port", s.config.Port).
		Str("version", s.config.Version).
		Msg("Starting API server")

	return s.httpServer.ListenAndServe()
}

// Shutdown gracefully shuts down the server
func (s *Server) Shutdown(ctx context.Context) error {
	s.logger.Info().Msg("Shutting down API server")
	return s.httpServer.Shutdown(ctx)
}

// setupMiddleware configures server middleware
func (s *Server) setupMiddleware() {
	// Request ID middleware (always first)
	s.router.Use(RequestIDMiddleware())

	// Logger middleware
	s.router.Use(LoggerMiddleware(os.Stdout))

	// Error recovery middleware
	s.router.Use(ErrorMiddleware())

	// CORS middleware (if configured)
	if len(s.config.CORSOrigins) > 0 {
		corsConfig := CORSConfig{
			AllowOrigins:     s.config.CORSOrigins,
			AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
			AllowHeaders:     []string{"Origin", "Content-Type", "X-API-Key", "X-Request-ID"},
			ExposeHeaders:    []string{"X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"},
			AllowCredentials: true,
			MaxAge:           86400,
		}
		s.router.Use(CORSMiddleware(corsConfig))
	}

	// Rate limiting middleware
	if s.config.RateLimit > 0 {
		s.router.Use(RateLimitMiddleware(s.config.RateLimit, s.config.RateWindow))
	}

	// Authentication middleware (applied to specific routes)
	// Will be applied in setupRoutes()
}

// setupBasicRoutes configures basic routes (health check)
func (s *Server) setupBasicRoutes() {
	// Health check endpoints (no auth required)
	healthHandlers := handlers.NewHealthHandlers(s.config.Version, s.startTime)
	s.router.GET("/health", healthHandlers.HealthCheck())
}

// setupRoutes configures API routes
func (s *Server) setupRoutes() {
	// Health handlers for additional endpoints
	healthHandlers := handlers.NewHealthHandlers(s.config.Version, s.startTime)

	// Conditional routes that require dependencies
	if s.readinessChecker != nil {
		s.router.GET("/ready", healthHandlers.Readiness(s.readinessChecker))
	}

	if s.metricsCollector != nil {
		s.router.GET("/metrics", healthHandlers.Metrics(s.metricsCollector))
	}

	// API routes (with authentication)
	api := s.router.Group("/api")
	api.Use(AuthMiddleware(s.config.APIKey))

	// Stream management routes
	if s.streamManager != nil {
		streamHandlers := handlers.NewStreamHandlers(s.streamManager)
		streams := api.Group("/streams")
		{
			streams.POST("", streamHandlers.CreateStream())
			streams.GET("", streamHandlers.ListStreams())
			streams.GET("/:id", streamHandlers.GetStream())
			streams.DELETE("/:id", streamHandlers.CloseStream())
			streams.POST("/:id/reconnect", streamHandlers.ReconnectStream())
		}
	}

	// Subscription routes
	if s.subscriptionManager != nil {
		subHandlers := handlers.NewSubscriptionHandlers(s.subscriptionManager)
		api.POST("/streams/:id/subscribe", subHandlers.SubscribeToMarketData())
		api.POST("/streams/:id/user-data", subHandlers.SubscribeToUserData())
		api.POST("/streams/:id/unsubscribe", subHandlers.Unsubscribe())
		api.GET("/streams/:id/subscriptions", subHandlers.ListSubscriptions())
	}

	// Admin routes
	if s.configManager != nil {
		adminHandlers := handlers.NewAdminHandlers(s.configManager)
		admin := api.Group("/admin")
		admin.Use(ValidationMiddleware()) // Extra validation for admin endpoints
		{
			admin.GET("/config", adminHandlers.GetConfig())
			admin.PUT("/config", adminHandlers.UpdateConfig())
			admin.GET("/stats", adminHandlers.GetStreamStats())
			admin.POST("/stats/reset", adminHandlers.ResetStats())
			admin.POST("/streams/close-all", adminHandlers.CloseAllStreams())
		}
	}
}

// Helper functions

func validateConfig(config *ServerConfig) error {
	if config.Port <= 0 || config.Port > 65535 {
		return fmt.Errorf("invalid port number: %d", config.Port)
	}

	if config.APIKey == "" {
		return fmt.Errorf("API key required")
	}

	if config.Version == "" {
		config.Version = "unknown"
	}

	return nil
}

func setConfigDefaults(config *ServerConfig) {
	if config.ReadTimeout == 0 {
		config.ReadTimeout = 30 * time.Second
	}

	if config.WriteTimeout == 0 {
		config.WriteTimeout = 30 * time.Second
	}

	if config.IdleTimeout == 0 {
		config.IdleTimeout = 60 * time.Second
	}

	if config.MaxHeaderBytes == 0 {
		config.MaxHeaderBytes = 1 << 20 // 1 MB
	}

	if config.RateWindow == 0 {
		config.RateWindow = time.Second
	}

	if config.LogLevel == "" {
		config.LogLevel = "info"
	}
}

func setupLogger(level string) zerolog.Logger {
	zerolog.TimeFieldFormat = time.RFC3339

	// Set log level
	switch level {
	case "debug":
		zerolog.SetGlobalLevel(zerolog.DebugLevel)
	case "info":
		zerolog.SetGlobalLevel(zerolog.InfoLevel)
	case "warn":
		zerolog.SetGlobalLevel(zerolog.WarnLevel)
	case "error":
		zerolog.SetGlobalLevel(zerolog.ErrorLevel)
	default:
		zerolog.SetGlobalLevel(zerolog.InfoLevel)
	}

	return zerolog.New(os.Stdout).With().Timestamp().Logger()
}
