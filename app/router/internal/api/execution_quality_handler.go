package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"

	"router/internal/storage"
)

// ExecutionQualityHandler handles execution quality metrics requests
type ExecutionQualityHandler struct {
	pool   *pgxpool.Pool
	orders *storage.OrderRepo
	logger zerolog.Logger
}

// NewExecutionQualityHandler creates a new execution quality handler
func NewExecutionQualityHandler(pool *pgxpool.Pool, logger zerolog.Logger) *ExecutionQualityHandler {
	return &ExecutionQualityHandler{
		pool:   pool,
		orders: storage.NewOrderRepo(),
		logger: logger,
	}
}

// ExecutionQualityRequest represents the query parameters for execution quality
type ExecutionQualityRequest struct {
	Venue     string    `json:"venue"`      // Optional: filter by venue (spot, futures)
	StartTime time.Time `json:"start_time"` // Required: start of time range
	EndTime   time.Time `json:"end_time"`   // Required: end of time range
	Limit     int       `json:"limit"`      // Optional: max orders to analyze
}

// GetExecutionQuality handles GET /internal/stats/execution-quality
func (h *ExecutionQualityHandler) GetExecutionQuality(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		h.logger.Warn().
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Msg("Invalid method for execution-quality")
		writeError(w, http.StatusMethodNotAllowed, "Method not allowed")
		return
	}

	// Parse query parameters
	query := r.URL.Query()

	venue := query.Get("venue")

	startTimeStr := query.Get("start_time")
	if startTimeStr == "" {
		// Default to last 24 hours
		startTimeStr = time.Now().Add(-24 * time.Hour).Format(time.RFC3339)
	}
	startTime, err := time.Parse(time.RFC3339, startTimeStr)
	if err != nil {
		h.logger.Warn().
			Err(err).
			Str("start_time", startTimeStr).
			Msg("Invalid start_time format")
		writeError(w, http.StatusBadRequest, "Invalid start_time format, use RFC3339")
		return
	}

	endTimeStr := query.Get("end_time")
	if endTimeStr == "" {
		endTimeStr = time.Now().Format(time.RFC3339)
	}
	endTime, err := time.Parse(time.RFC3339, endTimeStr)
	if err != nil {
		h.logger.Warn().
			Err(err).
			Str("end_time", endTimeStr).
			Msg("Invalid end_time format")
		writeError(w, http.StatusBadRequest, "Invalid end_time format, use RFC3339")
		return
	}

	limit := 1000 // Default limit

	h.logger.Info().
		Str("venue", venue).
		Time("start_time", startTime).
		Time("end_time", endTime).
		Int("limit", limit).
		Msg("Processing execution quality request")

	// Query orders from database
	ctx := r.Context()
	quality, err := h.computeExecutionQuality(ctx, venue, startTime, endTime, limit)
	if err != nil {
		h.logger.Error().
			Err(err).
			Msg("Failed to compute execution quality")
		writeError(w, http.StatusInternalServerError, "Failed to compute execution quality")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	if err := json.NewEncoder(w).Encode(quality); err != nil {
		h.logger.Error().Err(err).Msg("Failed to encode response")
	}
}

func (h *ExecutionQualityHandler) computeExecutionQuality(
	ctx context.Context,
	venue string,
	startTime time.Time,
	endTime time.Time,
	limit int,
) (ExecutionQuality, error) {
	if h.pool == nil {
		return ExecutionQuality{}, nil
	}

	conn, err := h.pool.Acquire(ctx)
	if err != nil {
		return ExecutionQuality{}, err
	}
	defer conn.Release()

	tx, err := conn.Begin(ctx)
	if err != nil {
		return ExecutionQuality{}, err
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	storageRows, err := h.orders.GetOrdersForExecutionQuality(ctx, tx, venue, startTime, endTime, limit)
	if err != nil {
		return ExecutionQuality{}, err
	}

	// Convert storage rows to API OrderExecutionRow
	apiRows := make([]OrderExecutionRow, len(storageRows))
	for i, sr := range storageRows {
		apiRows[i] = OrderExecutionRow{
			Side:             sr.Side,
			ExpectedPrice:    sr.ExpectedPrice,
			AverageFillPrice: sr.AverageFillPrice,
			Status:           sr.Status,
			DecisionTs:       sr.DecisionTs,
			RouterReceivedTs: sr.RouterReceivedTs,
			RouterSentTs:     sr.RouterSentTs,
			ExchangeAckTs:    sr.ExchangeAckTs,
			FirstFillTs:      sr.FirstFillTs,
			FilledTs:         sr.FilledTs,
		}
	}

	return ComputeExecutionQuality(apiRows), nil
}
