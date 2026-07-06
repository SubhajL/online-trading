package main

import (
	"context"
	"fmt"
	"html"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
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
	if strings.TrimSpace(cfg.Security.RequiredAPIKey) == "" {
		logger.Fatal().Msg("SECURITY_REQUIRED_API_KEY must be configured for active router runtime")
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
	var spotTradeProcessor *execution.SpotTradeProcessor
	var fundingCancel context.CancelFunc
	var legArmer *orders.LegArmer

	// Create event emitter (needed by the leg armer inside the DB block)
	var eventEmitter orders.EventEmitter
	orderUpdateURL := os.Getenv("ORDER_UPDATE_URL")
	if orderUpdateURL != "" {
		eventEmitter = orders.NewHTTPEventEmitter(orderUpdateURL)
		logger.Info().Str("url", orderUpdateURL).Msg("Order updates will be sent via HTTP")
	} else {
		eventEmitter = orders.NewLogEventEmitter(logger)
		logger.Info().Msg("Order updates will be logged to console")
	}

	legsOnFill, _ := strconv.ParseBool(os.Getenv("BRACKET_LEGS_ON_FILL"))

	if databaseURL := os.Getenv("DATABASE_URL"); databaseURL != "" {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		dbPool, err = storage.NewPostgresPool(ctx, databaseURL)
		cancel()
		if err != nil {
			logger.Fatal().Err(err).Msg("Failed to connect to Postgres")
		}

		intentPersister = api.NewPostgresIntentPersister(dbPool, logger.With().Str("component", "persistence").Logger())
		if cfg.Binance.IsSpotEnabled() {
			spotTradeProcessor, err = execution.NewSpotTradeProcessor(
				dbPool,
				storage.NewOrderRepo(),
				storage.NewFillRepo(),
				storage.NewPositionRepo(),
			)
			if err != nil {
				logger.Fatal().Err(err).Msg("Failed to initialize spot trade processor")
			}
		}

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

			if legsOnFill && futuresClient != nil {
				legArmer = orders.NewLegArmer(
					storage.NewBracketRepo(dbPool),
					futuresClient,
					eventEmitter,
					logger.With().Str("component", "leg_armer").Logger(),
				)
				logger.Info().Msg("BRACKET_LEGS_ON_FILL enabled: futures exit legs placed on entry fill")
			}

			userDataIngestor = execution.NewIngestor(
				futuresRestClient,
				wsClient,
				logger.With().Str("component", "user_stream").Logger(),
				execution.WithOrderTradeUpdateHandler(func(event *websocket.FuturesOrderTradeUpdateEvent) error {
					err := processor.HandleFuturesOrderTradeUpdate(context.Background(), event)
					if legArmer != nil {
						legArmer.OnOrderTradeUpdate(context.Background(), event)
					}
					return err
				}),
			)
			wsClient.SetUserDataReconnectHandler(userDataIngestor.OnSocketReconnected)

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

	// Create order manager
	orderManager := orders.NewManager(spotClient, futuresClient, eventEmitter, logger)
	if dbPool != nil {
		orderManager.SetBracketStore(storage.NewBracketRepo(dbPool))
		logger.Info().Msg("Durable bracket reservations enabled")
	}
	if legArmer != nil {
		// Deferring legs is only safe when an armer exists to place them
		orderManager.SetLegsOnFill(true)
	}

	// The entry-fill watcher is spot's fill trigger (no production spot
	// user-data stream) and the futures fallback sweep for events missed
	// while the router was down.
	var entryFillWatcher *orders.EntryFillWatcher
	if legsOnFill && dbPool != nil {
		var spotArmer *orders.SpotLegArmer
		if spotClient != nil {
			spotArmer = orders.NewSpotLegArmer(
				storage.NewBracketRepo(dbPool),
				spotClient,
				eventEmitter,
				logger.With().Str("component", "spot_leg_armer").Logger(),
			)
			orderManager.SetSpotLegsOnFill(true)
			logger.Info().Msg("BRACKET_LEGS_ON_FILL enabled: spot exits placed as OCO on entry fill")
		}
		pollInterval := 2 * time.Second
		if raw := os.Getenv("ENTRY_FILL_POLL_INTERVAL"); raw != "" {
			if parsed, err := time.ParseDuration(raw); err == nil && parsed > 0 {
				pollInterval = parsed
			}
		}
		entryFillWatcher = orders.NewEntryFillWatcher(
			storage.NewBracketRepo(dbPool),
			spotClient,
			spotArmer,
			futuresClient,
			legArmer,
			pollInterval,
			0, // default lookback
			logger.With().Str("component", "entry_fill_watcher").Logger(),
		)
		entryFillWatcher.Start(context.Background())
		logger.Info().Dur("interval", pollInterval).Msg("Entry fill watcher started")
	} else if legsOnFill {
		logger.Warn().Msg("BRACKET_LEGS_ON_FILL set but DATABASE_URL is missing; " +
			"exit legs will place synchronously")
	}
	var spotReconciler *orders.SpotReconciler
	if spotClient != nil {
		if enabled, err := strconv.ParseBool(os.Getenv("SPOT_RECONCILIATION_ENABLED")); err == nil && enabled {
			pollInterval := 3 * time.Second
			if raw := os.Getenv("SPOT_RECONCILIATION_POLL_INTERVAL"); raw != "" {
				if parsed, parseErr := time.ParseDuration(raw); parseErr == nil && parsed > 0 {
					pollInterval = parsed
				}
			}
			spotReconciler = orders.NewSpotReconciler(
				spotClient,
				eventEmitter,
				logger.With().Str("component", "spot_reconciler").Logger(),
				orders.WithSpotReconcilerLedger(spotTradeProcessor),
				orders.WithSpotReconcilerPollInterval(pollInterval),
			)
			spotReconciler.Start(context.Background())
			orderManager.SetSpotReconciler(spotReconciler)
			logger.Info().Dur("poll_interval", pollInterval).Msg("Spot reconciliation enabled")
		}
	}

	// The startup reconciler repairs whatever a crash or missed event left
	// behind in the brackets table before the router reports ready, and
	// serves on-demand passes via POST /internal/reconcile.
	var startupReconciler *orders.StartupReconciler
	if dbPool != nil {
		reconcileWatcher := entryFillWatcher
		if reconcileWatcher == nil {
			// Not started: the reconciler only borrows its entry-phase logic
			reconcileWatcher = orders.NewEntryFillWatcher(
				storage.NewBracketRepo(dbPool),
				spotClient,
				nil,
				futuresClient,
				legArmer,
				0, // default interval (unused, never started)
				0, // default lookback
				logger.With().Str("component", "entry_fill_watcher").Logger(),
			)
		}
		startupReconciler = orders.NewStartupReconciler(
			storage.NewBracketRepo(dbPool),
			reconcileWatcher,
			spotClient,
			futuresClient,
			eventEmitter,
			0, // default lookback
			logger.With().Str("component", "startup_reconciler").Logger(),
		)
	}

	// Create HTTP handlers
	handlers := api.NewHandlers(orderManager, logger, intentPersister, spotTradeProcessor)
	if cfg.Binance.Testnet {
		handlers.SetExecutionEnv("testnet")
	} else {
		handlers.SetExecutionEnv("mainnet")
	}

	if startupReconciler != nil {
		handlers.SetReady(false)
		go func() {
			defer handlers.SetReady(true)
			const maxAttempts = 3
			for attempt := 1; attempt <= maxAttempts; attempt++ {
				reconcileCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
				summary, err := startupReconciler.Reconcile(reconcileCtx)
				cancel()
				if err == nil {
					event := logger.Info()
					if summary.Errors > 0 || summary.UnrepairedLegs > 0 {
						// Completed the sweep but left work behind; surface it
						event = logger.Error()
					}
					event.
						Int("brackets_swept", summary.BracketsSwept).
						Int("legs_resolved", summary.LegsResolved).
						Int("brackets_closed", summary.BracketsClosed).
						Int("unrepaired_legs", summary.UnrepairedLegs).
						Int("errors", summary.Errors).
						Msg("Startup reconciliation complete")
					return
				}
				logger.Error().Err(err).Int("attempt", attempt).
					Msg("Startup reconciliation failed")
				if attempt < maxAttempts {
					time.Sleep(time.Duration(attempt) * 5 * time.Second)
				}
			}
			// Fail open: a broken DB must not brick deploys. The gap is
			// repairable via POST /internal/reconcile.
			logger.Error().Msg("Startup reconciliation exhausted retries; " +
				"serving anyway — POST /internal/reconcile to repair")
		}()
	}

	// Create and configure HTTP server
	mux := http.NewServeMux()

	// Register routes
	mux.HandleFunc("/place_bracket", handlers.PlaceBracketHandler)
	mux.HandleFunc("/cancel", handlers.CancelHandler)
	mux.HandleFunc("/close_all", handlers.CloseAllHandler)
	mux.HandleFunc("/cancel_open_orders", handlers.CancelOpenOrdersHandler)
	mux.HandleFunc("/close_positions", handlers.ClosePositionsHandler)
	api.RegisterHealthRoutes(mux, handlers)
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
	if startupReconciler != nil {
		mux.HandleFunc(
			"/internal/reconcile",
			api.NewReconcileHandler(startupReconciler, logger.With().Str("component", "startup_reconciler").Logger()),
		)
	}

	// Create server
	server := &http.Server{
		Addr:         fmt.Sprintf(":%d", cfg.Server.Port),
		Handler:      loggingMiddleware(authMiddleware(mux, cfg.Security.RequiredAPIKey)),
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
		if entryFillWatcher != nil {
			entryFillWatcher.Stop()
		}
		if fundingCancel != nil {
			fundingCancel()
		}
		if spotReconciler != nil {
			spotReconciler.Stop()
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

var unauthenticatedPaths = map[string]struct{}{
	"/health":  {},
	"/healthz": {},
	"/ready":   {},
	"/readyz":  {},
}

func authMiddleware(next http.Handler, requiredToken string) http.Handler {
	requiredToken = strings.TrimSpace(requiredToken)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, ok := unauthenticatedPaths[r.URL.Path]; ok || r.Method == http.MethodOptions {
			next.ServeHTTP(w, r)
			return
		}

		if providedToken(r) != requiredToken {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func providedToken(r *http.Request) string {
	if token := strings.TrimSpace(r.Header.Get("X-API-Key")); token != "" {
		return token
	}

	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	if !strings.HasPrefix(strings.ToLower(authHeader), "bearer ") {
		return ""
	}
	return strings.TrimSpace(authHeader[len("Bearer "):])
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
			html.EscapeString(r.URL.Path),
			html.EscapeString(r.RemoteAddr),
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
