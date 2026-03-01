package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"router/internal/api"
	"router/internal/auth"
	"router/internal/binance"
	"router/internal/config"
	"router/internal/execution"
	"router/internal/funding"
	"router/internal/orders"
	"router/internal/rest"
	"router/internal/storage"
	"router/internal/websocket"
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

	// Create Binance clients based on enabled trading modes
	var spotClient *binance.Client
	var futuresClient *binance.Client

	if cfg.Binance.IsSpotEnabled() {
		spotClient, err = newSpotClientFromConfig(&cfg.Binance, logger.With().Str("client", "spot").Logger())
		if err != nil {
			logger.Fatal().Err(err).Msg("Failed to create spot client")
		}
		logger.Info().Msg("Spot trading enabled")
	} else {
		logger.Info().Msg("Spot trading disabled")
	}

	if cfg.Binance.IsFuturesEnabled() {
		futuresClient, err = newFuturesClientFromConfig(&cfg.Binance, logger.With().Str("client", "futures").Logger())
		if err != nil {
			logger.Fatal().Err(err).Msg("Failed to create futures client")
		}
		logger.Info().Msg("Futures trading enabled")
	} else {
		logger.Info().Msg("Futures trading disabled")
	}

	var dbPool *pgxpool.Pool
	var intentPersister api.IntentPersister
	var userDataIngestor *execution.Ingestor
	var fundingCancel context.CancelFunc

	if databaseURL := os.Getenv("DATABASE_URL"); databaseURL != "" {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		dbPool, err = storage.NewPostgresPool(ctx, databaseURL)
		cancel()
		if err != nil {
			logger.Fatal().Err(err).Msg("Failed to connect to Postgres")
		}

		intentPersister = api.NewPostgresIntentPersister(dbPool, logger.With().Str("component", "persistence").Logger())

		if cfg.Binance.IsFuturesEnabled() {
			userWSBase := normalizeWSBaseURL(cfg.Binance.FuturesWSURL)
			wsClient := websocket.NewClient(
				websocket.WithBaseURL(userWSBase),
				websocket.WithAutoReconnectClient(true),
			)

			signer := auth.NewSignerWithRecvWindow(
				cfg.Binance.FuturesAPIKey,
				cfg.Binance.FuturesSecretKey,
				cfg.Binance.RecvWindow,
			)
			futuresRestClient := rest.NewClient(
				cfg.Binance.FuturesBaseURL,
				signer,
				rest.WithTimeout(cfg.Binance.Timeout),
				rest.WithMaxRetries(cfg.Binance.MaxRetries),
			)

			processor, err := execution.NewTradeProcessor(
				dbPool,
				storage.NewOrderRepo(),
				storage.NewFillRepo(),
				storage.NewPositionRepo(),
				"USD_M",
			)
			if err != nil {
				logger.Fatal().Err(err).Msg("Failed to initialize trade processor")
			}

			userDataIngestor = execution.NewIngestor(
				futuresRestClient,
				wsClient,
				logger.With().Str("component", "user_stream").Logger(),
				execution.WithOrderTradeUpdateHandler(func(event *websocket.FuturesOrderTradeUpdateEvent) error {
					return processor.HandleFuturesOrderTradeUpdate(context.Background(), event)
				}),
			)

			if err := userDataIngestor.Start(context.Background()); err != nil {
				logger.Fatal().Err(err).Msg("Failed to start user data ingestor")
			}
			logger.Info().Msg("User data ingestor started")

			interval := 8 * time.Hour
			if raw := os.Getenv("FUNDING_POLL_INTERVAL"); raw != "" {
				if parsed, err := time.ParseDuration(raw); err == nil && parsed > 0 {
					interval = parsed
				}
			}

			poller, err := funding.NewFundingPoller(
				futuresRestClient,
				dbPool,
				interval,
				logger.With().Str("component", "funding_poller").Logger(),
			)
			if err != nil {
				logger.Fatal().Err(err).Msg("Failed to initialize funding poller")
			}

			fundingCtx, cancel := context.WithCancel(context.Background())
			fundingCancel = cancel
			go poller.Start(fundingCtx)
			logger.Info().Dur("interval", interval).Msg("Funding poller started")
		}
	} else {
		logger.Warn().Msg("DATABASE_URL not set; router persistence disabled")
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
	handlers := api.NewHandlers(orderManager, logger, intentPersister)

	// Create and configure HTTP server
	mux := http.NewServeMux()

	// Register routes
	mux.HandleFunc("/place_bracket", handlers.PlaceBracketHandler)
	mux.HandleFunc("/cancel", handlers.CancelHandler)
	mux.HandleFunc("/close_all", handlers.CloseAllHandler)
	mux.HandleFunc("/cancel_open_orders", handlers.CancelOpenOrdersHandler)
	mux.HandleFunc("/close_positions", handlers.ClosePositionsHandler)
	mux.HandleFunc("/healthz", handlers.HealthzHandler)
	mux.HandleFunc("/readyz", handlers.ReadyzHandler)
	equityProvider := api.NewBinanceEquityProvider(spotClient, futuresClient)
	mux.HandleFunc(
		"/internal/equity",
		api.NewEquityHandler(equityProvider, logger.With().Str("component", "equity").Logger()),
	)
	if dbPool != nil {
		mux.HandleFunc("/stats", api.NewStatsHandler(api.NewPostgresStatsProvider(dbPool), logger))
		executionQualityHandler := api.NewExecutionQualityHandler(dbPool, logger.With().Str("component", "execution_quality").Logger())
		mux.HandleFunc("/internal/stats/execution-quality", executionQualityHandler.GetExecutionQuality)
	}

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

		if userDataIngestor != nil {
			_ = userDataIngestor.Stop(context.Background())
		}
		if fundingCancel != nil {
			fundingCancel()
		}
		if dbPool != nil {
			dbPool.Close()
		}

		fmt.Println("Server shutdown complete")
	}
}

func normalizeWSBaseURL(url string) string {
	trimmed := strings.TrimRight(url, "/")
	trimmed = strings.TrimSuffix(trimmed, "/stream")
	trimmed = strings.TrimSuffix(trimmed, "/ws")
	return trimmed
}

func newSpotClientFromConfig(cfg *config.BinanceConfig, logger zerolog.Logger) (*binance.Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("binance config is required")
	}

	signer := auth.NewSignerWithRecvWindow(cfg.SpotAPIKey, cfg.SpotSecretKey, cfg.RecvWindow)
	restClient := rest.NewClient(
		cfg.BaseURL,
		signer,
		rest.WithTimeout(cfg.Timeout),
		rest.WithMaxRetries(cfg.MaxRetries),
	)

	client, err := binance.NewSpotClient(cfg.BaseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}

	client.SetExchangeInfoCache(
		binance.NewExchangeInfoCache(
			restClient,
			nil,
			cfg.ExchangeInfoCacheTTL,
			logger.With().Str("component", "exchange_info").Logger(),
		),
	)
	return client, nil
}

func newFuturesClientFromConfig(cfg *config.BinanceConfig, logger zerolog.Logger) (*binance.Client, error) {
	if cfg == nil {
		return nil, fmt.Errorf("binance config is required")
	}

	signer := auth.NewSignerWithRecvWindow(cfg.FuturesAPIKey, cfg.FuturesSecretKey, cfg.RecvWindow)
	restClient := rest.NewClient(
		cfg.FuturesBaseURL,
		signer,
		rest.WithTimeout(cfg.Timeout),
		rest.WithMaxRetries(cfg.MaxRetries),
	)

	client, err := binance.NewFuturesClient(cfg.FuturesBaseURL, signer, restClient, logger)
	if err != nil {
		return nil, err
	}

	client.SetExchangeInfoCache(
		binance.NewExchangeInfoCache(
			nil,
			restClient,
			cfg.ExchangeInfoCacheTTL,
			logger.With().Str("component", "exchange_info").Logger(),
		),
	)
	return client, nil
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
