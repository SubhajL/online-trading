package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rs/zerolog"
	"router/internal/api"
	"router/internal/binance"
	"router/internal/config"
	"router/internal/orders"
)

func main() {
	// Set up logger
	output := zerolog.ConsoleWriter{Out: os.Stdout, TimeFormat: time.RFC3339}
	logger := zerolog.New(output).With().Timestamp().Logger()

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal().Err(err).Msg("Failed to load config")
	}

	// Apply testnet URLs if enabled
	cfg.GetBinanceTestnetURLs()

	// Create Binance clients
	spotClient, err := binance.NewTestnetSpotClient(&cfg.Binance, logger.With().Str("client", "spot").Logger())
	if err != nil {
		logger.Fatal().Err(err).Msg("Failed to create spot client")
	}

	futuresClient, err := binance.NewTestnetFuturesClient(&cfg.Binance, logger.With().Str("client", "futures").Logger())
	if err != nil {
		logger.Fatal().Err(err).Msg("Failed to create futures client")
	}

	// Create event emitter
	var eventEmitter orders.EventEmitter
	orderUpdateURL := os.Getenv("ORDER_UPDATE_URL")
	if orderUpdateURL != "" {
		eventEmitter = orders.NewHTTPEventEmitter(orderUpdateURL)
		logger.Info().Str("url", orderUpdateURL).Msg("Order updates will be sent via HTTP")
	} else {
		eventEmitter = orders.NewLogEventEmitter(logger)
		logger.Info().Msg("Order updates will be logged to console")
	}

	// Create order manager
	orderManager := orders.NewManager(spotClient, futuresClient, eventEmitter, logger)

	// Create HTTP handlers
	handlers := api.NewHandlers(orderManager, logger)

	// Create and configure HTTP server
	mux := http.NewServeMux()

	// Register routes
	mux.HandleFunc("/place_bracket", handlers.PlaceBracketHandler)
	mux.HandleFunc("/cancel", handlers.CancelHandler)
	mux.HandleFunc("/close_all", handlers.CloseAllHandler)
	mux.HandleFunc("/healthz", handlers.HealthzHandler)
	mux.HandleFunc("/readyz", handlers.ReadyzHandler)

	// Create server
	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Server.Port),
		Handler:      loggingMiddleware(mux),
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
		IdleTimeout:  cfg.Server.IdleTimeout,
	}

	// Start server in goroutine
	serverErrors := make(chan error, 1)
	go func() {
		logger.Info().
			Str("addr", server.Addr).
			Bool("testnet", cfg.Binance.Testnet).
			Str("spot_url", cfg.Binance.BaseURL).
			Str("futures_url", cfg.Binance.FuturesBaseURL).
			Msg("Order Router starting")
		serverErrors <- server.ListenAndServe()
	}()

	// Setup signal handling
	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, os.Interrupt, syscall.SIGTERM)

	// Wait for shutdown signal or server error
	select {
	case err := <-serverErrors:
		if err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	case sig := <-shutdown:
		fmt.Printf("Shutdown signal received: %v\n", sig)

		// Create shutdown context with timeout
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()

		// Gracefully shutdown server
		if err := server.Shutdown(ctx); err != nil {
			log.Printf("Failed to shutdown server gracefully: %v", err)
		}

		fmt.Println("Server shutdown complete")
	}
}

// loggingMiddleware logs HTTP requests
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Create wrapped response writer to capture status
		wrapped := &responseWriter{ResponseWriter: w, statusCode: http.StatusOK}

		next.ServeHTTP(wrapped, r)

		duration := time.Since(start)
		fmt.Printf("%s %s %s - %d - %v\n",
			r.Method,
			r.URL.Path,
			r.RemoteAddr,
			wrapped.statusCode,
			duration,
		)
	})
}

// responseWriter wraps http.ResponseWriter to capture status code
type responseWriter struct {
	http.ResponseWriter
	statusCode int
	written    bool
}

func (rw *responseWriter) WriteHeader(code int) {
	if !rw.written {
		rw.statusCode = code
		rw.ResponseWriter.WriteHeader(code)
		rw.written = true
	}
}

func (rw *responseWriter) Write(b []byte) (int, error) {
	if !rw.written {
		rw.WriteHeader(http.StatusOK)
	}
	return rw.ResponseWriter.Write(b)
}
