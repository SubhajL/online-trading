package orders

import (
	"context"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"

	"router/internal/binance"
	"router/internal/storage"
)

// bracketLegExecutionProgressUpdater is implemented by the durable bracket
// repository. Keeping it optional preserves compatibility with the small
// in-memory stores used by callers that do not enable deferred execution.
type bracketLegExecutionProgressUpdater interface {
	UpdateLegExecutionProgress(
		ctx context.Context,
		bracketID uuid.UUID,
		clientOrderID, status string,
		exchangeOrderID int64,
		executedQuantity, averageFillPrice decimal.Decimal,
		observedAt time.Time,
	) error
}

type bracketLegQuantityUpdater interface {
	UpdateLegQuantity(
		ctx context.Context,
		bracketID uuid.UUID,
		clientOrderID string,
		quantity decimal.Decimal,
	) error
}

type entryFinalizationClaimer interface {
	TryClaimEntryFinalization(ctx context.Context, bracketID, leaseToken uuid.UUID) (bool, error)
	ReleaseEntryFinalization(ctx context.Context, bracketID, leaseToken uuid.UUID) error
}

func persistLegExecutionProgress(
	ctx context.Context,
	store armerStore,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
	executedQuantity, averageFillPrice decimal.Decimal,
	observedAt time.Time,
) error {
	if updater, ok := store.(bracketLegExecutionProgressUpdater); ok {
		return updater.UpdateLegExecutionProgress(
			ctx,
			bracketID,
			clientOrderID,
			status,
			exchangeOrderID,
			executedQuantity,
			averageFillPrice,
			observedAt,
		)
	}
	return persistLegExecution(ctx, store, bracketID, clientOrderID, status, exchangeOrderID, averageFillPrice)
}

func updateLegQuantity(
	ctx context.Context,
	store armerStore,
	bracketID uuid.UUID,
	clientOrderID string,
	quantity decimal.Decimal,
) error {
	if updater, ok := store.(bracketLegQuantityUpdater); ok {
		return updater.UpdateLegQuantity(ctx, bracketID, clientOrderID, quantity)
	}
	return nil
}

func withEntryFinalizationLease(
	ctx context.Context,
	store armerStore,
	bracketID uuid.UUID,
	logger zerolog.Logger,
	fn func() bool,
) bool {
	claimer, ok := store.(entryFinalizationClaimer)
	if !ok {
		return fn()
	}

	token := uuid.New()
	claimed, err := claimer.TryClaimEntryFinalization(ctx, bracketID, token)
	if err != nil {
		logger.Warn().Err(err).Str("bracket_id", bracketID.String()).
			Msg("entry finalizer: failed to claim finalization lease")
		return false
	}
	if !claimed {
		return false
	}
	defer func() {
		if err := claimer.ReleaseEntryFinalization(context.WithoutCancel(ctx), bracketID, token); err != nil {
			logger.Warn().Err(err).Str("bracket_id", bracketID.String()).
				Msg("entry finalizer: failed to release finalization lease")
		}
	}()
	return fn()
}

func exchangeObservationTime(transactTime int64) time.Time {
	if transactTime <= 0 {
		return time.Time{}
	}
	return time.UnixMilli(transactTime).UTC()
}

// finalizePartialEntry makes a live partial entry immutable before protecting
// it. The cancellation response is deliberately ignored: futures does not
// return an authoritative body and spot can race a last fill. The stable
// client-id query is the only terminal decision.
func finalizePartialEntry(
	ctx context.Context,
	store armerStore,
	client *binance.Client,
	record *storage.BracketRecord,
	observed *binance.OrderResponse,
	logger zerolog.Logger,
	arm func(context.Context, *storage.BracketRecord, *binance.OrderResponse),
) bool {
	if client == nil || record == nil || observed == nil || !observed.ExecutedQty.IsPositive() {
		return false
	}

	if err := persistLegExecutionProgress(
		ctx,
		store,
		record.BracketID,
		record.EntryClientOrderID,
		"PARTIALLY_FILLED",
		observed.OrderID,
		observed.ExecutedQty,
		observed.AverageFillPrice,
		exchangeObservationTime(observed.TransactTime),
	); err != nil {
		logger.Warn().Err(err).Str("client_order_id", record.EntryClientOrderID).
			Msg("entry finalizer: failed to persist partial progress")
		return false
	}

	return withEntryFinalizationLease(ctx, store, record.BracketID, logger, func() bool {
		entryLeg := legByClientOrderID(record, record.EntryClientOrderID)
		if entryLeg != nil && isTerminalEntryLeg(entryLeg.Status) &&
			(entryLeg.ExecutedQuantity.IsPositive() || record.Status == storage.BracketStatusLegsPlaced) {
			terminal := finalizedEntryResponse(record, observed, observed, entryLeg.ExecutedQuantity, entryLeg.Status)
			arm(ctx, record, terminal)
			return true
		}

		// Cancellation is best effort. In particular, a futures cancellation
		// response is not trusted; the mandatory query below is authoritative.
		cancelOrderID := observed.OrderID
		if cancelOrderID == 0 && entryLeg != nil {
			cancelOrderID = entryLeg.ExchangeOrderID
		}
		if cancelOrderID > 0 {
			if _, err := client.CancelOrder(ctx, record.Symbol, cancelOrderID); err != nil {
				logger.Warn().Err(err).Str("client_order_id", record.EntryClientOrderID).
					Msg("entry finalizer: entry cancel unresolved; querying exchange state")
			}
		}

		terminal, err := queryWithRepoll(ctx, client, record.Symbol, record.EntryClientOrderID)
		if err != nil {
			logger.Warn().Err(err).Str("client_order_id", record.EntryClientOrderID).
				Msg("entry finalizer: terminal entry query unavailable; leaving exits unarmed")
			return false
		}
		if !isFinalEntryStatus(terminal.Status) {
			logger.Info().Str("client_order_id", record.EntryClientOrderID).
				Str("status", terminal.Status).
				Msg("entry finalizer: entry remains working; leaving exits unarmed")
			return false
		}

		durableQuantity := decimal.Zero
		if entryLeg != nil {
			durableQuantity = entryLeg.ExecutedQuantity
		}
		final := finalizedEntryResponse(record, terminal, observed, durableQuantity, "")
		finalStatus := finalEntryLegStatus(final.Status)
		if err := persistLegExecutionProgress(
			ctx,
			store,
			record.BracketID,
			record.EntryClientOrderID,
			finalStatus,
			final.OrderID,
			final.ExecutedQty,
			final.AverageFillPrice,
			exchangeObservationTime(final.TransactTime),
		); err != nil {
			logger.Warn().Err(err).Str("client_order_id", record.EntryClientOrderID).
				Msg("entry finalizer: failed to persist terminal progress")
			return false
		}
		arm(ctx, record, final)
		return true
	})
}

func isTerminalEntryLeg(status string) bool {
	switch normalizeOrderStatus(status) {
	case storage.LegStatusFilled, storage.LegStatusCanceled, storage.LegStatusExpired, storage.LegStatusFailed:
		return true
	default:
		return false
	}
}

func isFinalEntryStatus(status string) bool {
	switch normalizeOrderStatus(status) {
	case "FILLED", "CANCELED", "CANCELLED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED":
		return true
	default:
		return false
	}
}

func finalEntryLegStatus(status string) string {
	switch normalizeOrderStatus(status) {
	case "FILLED":
		return storage.LegStatusFilled
	case "CANCELED", "CANCELLED":
		return storage.LegStatusCanceled
	case "REJECTED":
		return storage.LegStatusFailed
	default:
		return storage.LegStatusExpired
	}
}

func finalizedEntryResponse(
	record *storage.BracketRecord,
	response *binance.OrderResponse,
	observed *binance.OrderResponse,
	durableQuantity decimal.Decimal,
	storedStatus string,
) *binance.OrderResponse {
	final := *response
	selected := response
	quantity := response.ExecutedQty
	if observed != nil && observed.ExecutedQty.GreaterThan(quantity) {
		selected = observed
		quantity = observed.ExecutedQty
	}
	durableWon := durableQuantity.GreaterThan(quantity)
	if durableQuantity.GreaterThan(quantity) {
		quantity = durableQuantity
	}
	if normalizeOrderStatus(response.Status) == "FILLED" && record.Quantity.IsPositive() {
		quantity = record.Quantity
	}
	if record.Quantity.IsPositive() && quantity.GreaterThan(record.Quantity) {
		quantity = record.Quantity
	}
	final.ExecutedQty = quantity
	if durableWon {
		final.AverageFillPrice = decimal.Zero
		final.TransactTime = 0
	} else {
		final.AverageFillPrice = selected.AverageFillPrice
		final.TransactTime = selected.TransactTime
	}
	if storedStatus != "" {
		switch normalizeOrderStatus(storedStatus) {
		case storage.LegStatusFilled:
			final.Status = "FILLED"
		case storage.LegStatusCanceled:
			final.Status = "CANCELED"
		case storage.LegStatusExpired:
			final.Status = "EXPIRED"
		case storage.LegStatusFailed:
			final.Status = "REJECTED"
		}
	}
	return &final
}
