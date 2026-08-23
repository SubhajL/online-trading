package orders

import (
	"context"
	"time"

	"github.com/rs/zerolog"

	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

const (
	defaultEntryFillLookback = 168 * time.Hour
	openBracketPageSize      = 100
)

// watcherStore is the store slice the watcher needs beyond the armers.
type watcherStore interface {
	armerStore
	LoadOpenBracketPage(
		ctx context.Context,
		cursor *storage.OpenBracketCursor,
		pageSize int,
	) ([]storage.BracketRecord, *storage.OpenBracketCursor, error)
}

// EntryFillWatcher polls open deferred brackets and arms exit legs once
// their entries fill. Spot has no production user-data stream, so this loop
// IS the spot fill trigger; for futures it is a fallback sweep behind the
// event-driven leg armer (a fill received while the router was down would
// otherwise never arm). The brackets table is the queue, so the watcher is
// restart-safe by construction.
type EntryFillWatcher struct {
	store         watcherStore
	spotClient    *binance.Client
	spotArmer     *SpotLegArmer
	futures       *LegArmer
	futuresClient *binance.Client
	interval      time.Duration
	lookback      time.Duration
	logger        zerolog.Logger

	cancel context.CancelFunc
	done   chan struct{}
}

func NewEntryFillWatcher(
	store watcherStore,
	spotClient *binance.Client,
	spotArmer *SpotLegArmer,
	futuresClient *binance.Client,
	futuresArmer *LegArmer,
	interval time.Duration,
	lookback time.Duration,
	logger zerolog.Logger,
) *EntryFillWatcher {
	if interval <= 0 {
		interval = 2 * time.Second
	}
	if lookback <= 0 {
		lookback = defaultEntryFillLookback
	}
	return &EntryFillWatcher{
		store:         store,
		spotClient:    spotClient,
		spotArmer:     spotArmer,
		futures:       futuresArmer,
		futuresClient: futuresClient,
		interval:      interval,
		lookback:      lookback,
		logger:        logger,
	}
}

func (w *EntryFillWatcher) Start(ctx context.Context) {
	ctx, w.cancel = context.WithCancel(ctx)
	w.done = make(chan struct{})
	go func() {
		defer close(w.done)
		ticker := time.NewTicker(w.interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				w.pollOnce(ctx)
			}
		}
	}()
}

func (w *EntryFillWatcher) Stop() {
	if w.cancel != nil {
		w.cancel()
	}
	if w.done != nil {
		<-w.done
	}
}

func (w *EntryFillWatcher) pollOnce(ctx context.Context) {
	var cursor *storage.OpenBracketCursor
	for {
		if err := ctx.Err(); err != nil {
			return
		}
		brackets, next, err := w.store.LoadOpenBracketPage(ctx, cursor, openBracketPageSize)
		if err != nil {
			w.logger.Warn().Err(err).Msg("entry fill watcher: load failed")
			return
		}

		for i := range brackets {
			record := &brackets[i]
			if !record.LegsOnFill {
				continue
			}
			// RESERVED is included: a crash between the entry POST and the
			// bookkeeping write leaves a live entry on a RESERVED bracket, and
			// nothing else would ever protect its fill. A not-yet-POSTed entry
			// just resolves to -2013 and is skipped.
			if record.Status != storage.BracketStatusReserved &&
				record.Status != storage.BracketStatusEntryPlaced &&
				record.Status != storage.BracketStatusEntryFilled {
				continue
			}
			w.checkBracket(ctx, record)
		}
		if next == nil {
			return
		}
		cursor = next
	}
}

func (w *EntryFillWatcher) checkBracket(ctx context.Context, record *storage.BracketRecord) {
	client := w.spotClient
	if record.Venue == "USD_M" {
		client = w.futuresClient
	}
	if client == nil {
		return
	}

	entry, err := client.GetOrderByClientID(ctx, record.Symbol, record.EntryClientOrderID)
	if err != nil {
		if !rest.IsOrderNotFound(err) {
			w.logger.Warn().Err(err).
				Str("client_order_id", record.EntryClientOrderID).
				Msg("entry fill watcher: entry lookup failed")
		}
		return
	}
	w.checkBracketWithEntry(ctx, record, entry)
}

// checkBracketWithEntry applies the fill/dead-entry decision to an entry the
// caller already fetched (the reconciler reuses this after its own lookup).
func (w *EntryFillWatcher) checkBracketWithEntry(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
	if record == nil || entry == nil {
		return
	}
	switch normalizeOrderStatus(entry.Status) {
	case "PARTIALLY_FILLED":
		client := w.spotClient
		if record.Venue == "USD_M" {
			client = w.futuresClient
		}
		finalizePartialEntry(ctx, w.store, client, record, entry, w.logger,
			func(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
				w.armFinalized(ctx, record, entry)
			})
	case "FILLED":
		w.arm(ctx, record, entry)
	case "CANCELED", "EXPIRED", "EXPIRED_IN_MATCH", "REJECTED":
		if entry.ExecutedQty.IsPositive() {
			// A partial position exists and must still be protected
			w.arm(ctx, record, entry)
			return
		}
		w.releaseDeadBracket(ctx, record)
	}
}

func (w *EntryFillWatcher) arm(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
	status, _ := legStatusFromOrder(entry.Status)
	quantity := entry.ExecutedQty
	if normalizeOrderStatus(entry.Status) == "FILLED" && quantity.IsZero() {
		quantity = record.Quantity
	}
	if err := persistLegExecutionProgress(ctx, w.store, record.BracketID, record.EntryClientOrderID,
		status, entry.OrderID, quantity, entry.AverageFillPrice,
		exchangeObservationTime(entry.TransactTime)); err != nil {
		w.logger.Warn().Err(err).
			Str("client_order_id", record.EntryClientOrderID).
			Msg("entry fill watcher: failed to persist entry execution")
		return
	}
	effectiveEntry := *entry
	effectiveEntry.ExecutedQty = quantity
	w.armFinalized(ctx, record, &effectiveEntry)
}

func (w *EntryFillWatcher) armFinalized(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
	if record.Venue == "USD_M" {
		if w.futures != nil {
			w.futures.armLegs(ctx, record, entry.ExecutedQty)
			return
		}
	} else if w.spotArmer != nil {
		w.spotArmer.Arm(ctx, record, entry)
		return
	}
	// A filled entry with no armer for its venue leaves the position
	// unprotected; only an engine replay can repair it. Never silent.
	w.logger.Error().
		Str("bracket_id", record.BracketID.String()).
		Str("venue", record.Venue).
		Str("symbol", record.Symbol).
		Str("executed_qty", entry.ExecutedQty.String()).
		Msg("entry fill watcher: entry filled but no armer for venue; position UNPROTECTED")
}

func (w *EntryFillWatcher) releaseDeadBracket(ctx context.Context, record *storage.BracketRecord) {
	for _, leg := range record.Legs {
		if leg.Role == "ENTRY" || leg.Status == storage.LegStatusPlanned {
			if err := w.store.UpdateLegStatus(ctx, record.BracketID, leg.ClientOrderID,
				storage.LegStatusCanceled, leg.ExchangeOrderID); err != nil {
				w.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
					Msg("entry fill watcher: failed to release leg")
			}
		}
	}
	if err := w.store.UpdateBracketStatus(ctx, record.BracketID, storage.BracketStatusClosed); err != nil {
		w.logger.Warn().Err(err).Str("bracket_id", record.BracketID.String()).
			Msg("entry fill watcher: failed to close dead bracket")
	}
}
