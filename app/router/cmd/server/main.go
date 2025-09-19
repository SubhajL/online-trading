package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"router/internal/api"
	"router/internal/websocket"
)

func main() {
	// Setup logger
	zerolog.TimeFieldFormat = time.RFC3339
	log.Logger = log.Output(zerolog.ConsoleWriter{Out: os.Stderr})

	// Load configuration
	config, err := LoadConfig()
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to load configuration")
	}

	// Log configuration
	log.Info().
		Int("port", config.Port).
		Str("version", config.Version).
		Str("log_level", config.LogLevel).
		Int("rate_limit", config.RateLimit).
		Msg("Starting router service")

	// Create server configuration
	serverConfig := api.ServerConfig{
		Port:           config.Port,
		ReadTimeout:    config.ReadTimeout,
		WriteTimeout:   config.WriteTimeout,
		IdleTimeout:    config.IdleTimeout,
		MaxHeaderBytes: 1 << 20, // 1 MB
		APIKey:         config.APIKey,
		Version:        config.Version,
		RateLimit:      config.RateLimit,
		RateWindow:     time.Second,
		CORSOrigins:    config.CORSOrigins,
		LogLevel:       config.LogLevel,
	}

	// Create API server
	server, err := api.NewServer(serverConfig)
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to create server")
	}

	// Initialize WebSocket client (from Phase 3)
	wsClient, err := initializeWebSocketClient(config)
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to initialize WebSocket client")
	}

	// Create manager implementations that bridge WebSocket to HTTP
	streamManager := NewStreamManagerImpl(wsClient)
	subscriptionManager := NewSubscriptionManagerImpl(wsClient)
	configManager := NewConfigManagerImpl(config)
	readinessChecker := NewReadinessCheckerImpl(wsClient)
	metricsCollector := NewMetricsCollectorImpl(wsClient)

	// Set dependencies
	server.SetDependencies(
		streamManager,
		subscriptionManager,
		configManager,
		readinessChecker,
		metricsCollector,
	)

	// Start server in goroutine
	serverErrors := make(chan error, 1)
	go func() {
		log.Info().Int("port", config.Port).Msg("API server listening")
		serverErrors <- server.Start()
	}()

	// Setup signal handling
	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, os.Interrupt, syscall.SIGTERM)

	// Wait for shutdown signal or server error
	select {
	case err := <-serverErrors:
		if err != nil {
			log.Error().Err(err).Msg("Server error")
		}
	case sig := <-shutdown:
		log.Info().Str("signal", sig.String()).Msg("Shutdown signal received")

		// Create shutdown context with timeout
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		// Gracefully shutdown server
		if err := server.Shutdown(ctx); err != nil {
			log.Error().Err(err).Msg("Failed to shutdown server gracefully")
		}

		// Close WebSocket client
		if err := wsClient.Close(); err != nil {
			log.Error().Err(err).Msg("Failed to close WebSocket client")
		}

		log.Info().Msg("Shutdown complete")
	}
}

// initializeWebSocketClient creates and configures the WebSocket client
func initializeWebSocketClient(config *Config) (*websocket.Client, error) {
	// Get WebSocket URL from environment or use default
	wsURL := os.Getenv("WEBSOCKET_URL")
	if wsURL == "" {
		wsURL = "wss://stream.binance.com:9443/ws"
	}

	// For Phase 4, we'll create a placeholder client
	// In production, this would be properly integrated with the WebSocket implementation
	client := websocket.NewClient()

	log.Info().Str("url", wsURL).Msg("WebSocket client initialized")
	return client, nil
}
