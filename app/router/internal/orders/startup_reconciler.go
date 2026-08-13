package orders

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/rs/zerolog"

	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

// ErrReconcileInFlight rejects concurrent reconcile passes; the running one
// already covers the caller's intent.
var ErrReconcileInFlight = errors.New("reconcile already in flight")

// ReconcileSummary reports what one reconcile pass observed and repaired.
type ReconcileSummary struct {
	BracketsSwept   int `json:"brackets_swept"`
	EntriesChecked  int `json:"entries_checked"`
	LegsResolved    int `json:"legs_resolved"`
	ExitLegsUpdated int `json:"exit_legs_updated"`
	BracketsClosed  int `json:"brackets_closed"`
	StaleReserved   int `json:"stale_reserved"`
	UnrepairedLegs  int `json:"unrepaired_legs"`
	Errors          int `json:"errors"`
}

// StartupReconciler sweeps every open bracket and repairs whatever a crash,
// missed event, or failed placement left behind: it settles legs stuck
// PLACING against the exchange, re-drives entry-phase brackets through the
// entry-fill watcher's logic, observes exit-leg outcomes for LEGS_PLACED
// brackets, and closes brackets whose position is gone. It runs once at
// startup (gating readiness) and on demand via POST /internal/reconcile.
type StartupReconciler struct {
	store         watcherStore
	watcher       *EntryFillWatcher
	spotClient    *binance.Client
	futuresClient *binance.Client
	emitter       EventEmitter
	lookback      time.Duration
	logger        zerolog.Logger

	inFlight chan struct{}

	// Last completed pass, cached for read-only observability (GET
	// /internal/reconcile) so an operator can see reconciler state without
	// triggering a mutating pass.
	mu         sync.Mutex
	lastResult *ReconcileSummary
	lastRunAt  time.Time
}

// ReconcileStatus is the read-only view of the reconciler's last pass.
type ReconcileStatus struct {
	HasRun    bool              `json:"has_run"`
	LastRunAt *time.Time        `json:"last_run_at,omitempty"`
	Summary   *ReconcileSummary `json:"summary,omitempty"`
}

func NewStartupReconciler(
	store watcherStore,
	watcher *EntryFillWatcher,
	spotClient *binance.Client,
	futuresClient *binance.Client,
	emitter EventEmitter,
	lookback time.Duration,
	logger zerolog.Logger,
) *StartupReconciler {
	if lookback <= 0 {
		lookback = defaultEntryFillLookback
	}
	gate := make(chan struct{}, 1)
	gate <- struct{}{}
	return &StartupReconciler{
		store:         store,
		watcher:       watcher,
		spotClient:    spotClient,
		futuresClient: futuresClient,
		emitter:       emitter,
		lookback:      lookback,
		logger:        logger,
		inFlight:      gate,
	}
}

// Reconcile runs one full pass. Single-flight: a pass already running makes
// this return ErrReconcileInFlight.
func (r *StartupReconciler) Reconcile(ctx context.Context) (*ReconcileSummary, error) {
	select {
	case <-r.inFlight:
	default:
		return nil, ErrReconcileInFlight
	}
	defer func() { r.inFlight <- struct{}{} }()

	brackets, err := r.store.LoadOpenBrackets(ctx, r.lookback)
	if err != nil {
		return nil, err
	}

	summary := &ReconcileSummary{}
	for i := range brackets {
		if ctx.Err() != nil {
			// A partial pass must not read as success: callers retry
			return summary, ctx.Err()
		}
		record := &brackets[i]
		summary.BracketsSwept++
		r.reconcileBracket(ctx, record, summary)
	}
	r.logger.Info().
		Int("brackets_swept", summary.BracketsSwept).
		Int("entries_checked", summary.EntriesChecked).
		Int("legs_resolved", summary.LegsResolved).
		Int("exit_legs_updated", summary.ExitLegsUpdated).
		Int("brackets_closed", summary.BracketsClosed).
		Int("stale_reserved", summary.StaleReserved).
		Int("errors", summary.Errors).
		Msg("reconciler: pass complete")
	r.storeResult(summary)
	return summary, nil
}

// storeResult caches the last completed pass for read-only observability.
func (r *StartupReconciler) storeResult(summary *ReconcileSummary) {
	snapshot := *summary
	r.mu.Lock()
	r.lastResult = &snapshot
	r.lastRunAt = time.Now().UTC()
	r.mu.Unlock()
}

// Status returns the read-only view of the last completed reconcile pass.
func (r *StartupReconciler) Status() ReconcileStatus {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.lastResult == nil {
		return ReconcileStatus{HasRun: false}
	}
	summary := *r.lastResult
	runAt := r.lastRunAt
	return ReconcileStatus{HasRun: true, LastRunAt: &runAt, Summary: &summary}
}

func (r *StartupReconciler) clientFor(venue string) *binance.Client {
	if venue == "USD_M" {
		return r.futuresClient
	}
	return r.spotClient
}

func (r *StartupReconciler) reconcileBracket(ctx context.Context, record *storage.BracketRecord, summary *ReconcileSummary) {
	client := r.clientFor(record.Venue)
	if client == nil {
		return
	}

	// A leg stuck PLACING outlived its process; the exchange is the only
	// authority on whether that placement landed.
	r.resolvePlacingLegs(ctx, client, record, summary)

	switch record.Status {
	case storage.BracketStatusReserved:
		entry, err := client.GetOrderByClientID(ctx, record.Symbol, record.EntryClientOrderID)
		if err != nil {
			if rest.IsOrderNotFound(err) {
				// Never POSTed. Closing it could race an in-flight engine
				// replay, so it is only surfaced, not repaired.
				summary.StaleReserved++
				r.logger.Warn().
					Str("bracket_id", record.BracketID.String()).
					Str("entry_client_order_id", record.EntryClientOrderID).
					Time("created_at", record.CreatedAt).
					Msg("reconciler: reservation has no exchange entry")
			} else {
				summary.Errors++
				r.logger.Warn().Err(err).
					Str("entry_client_order_id", record.EntryClientOrderID).
					Msg("reconciler: reserved entry lookup failed")
			}
			return
		}
		summary.EntriesChecked++
		r.watcher.checkBracketWithEntry(ctx, record, entry)
	case storage.BracketStatusEntryPlaced, storage.BracketStatusEntryFilled:
		// Entry-phase repair reuses the watcher's logic (arm on fill,
		// release on dead entry). Unlike the 2s loop, the reconciler also
		// drives non-deferred brackets that crashed before their exits
		// were placed.
		summary.EntriesChecked++
		r.watcher.checkBracket(ctx, record)
	case storage.BracketStatusLegsPlaced:
		r.sweepExitLegs(ctx, client, record, summary)
	}
}

// resolvePlacingLegs settles legs left PLACING by a crash. A live armer may
// be placing the same leg concurrently (the startup pass overlaps the 2s
// watcher and the user-data armer, and /internal/reconcile can fire any
// time), so a confirmed-absent leg is demoted with a CAS guarded on PLACING
// — a fresher armer write is never overwritten — and only after a repoll,
// since a freshly accepted order can lag the query path (#193).
func (r *StartupReconciler) resolvePlacingLegs(
	ctx context.Context,
	client *binance.Client,
	record *storage.BracketRecord,
	summary *ReconcileSummary,
) {
	for i := range record.Legs {
		leg := &record.Legs[i]
		if leg.Status != storage.LegStatusPlacing {
			continue
		}
		resp, err := r.getOrderWithRepoll(ctx, client, record.Symbol, leg.ClientOrderID)
		if err != nil {
			if rest.IsOrderNotFound(err) {
				// Confirmed absent after repoll: release the claim so an
				// armer can re-place it, but only if still PLACING.
				if r.demotePlacing(ctx, record, leg) {
					summary.LegsResolved++
				}
			} else {
				summary.Errors++
				r.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
					Msg("reconciler: PLACING leg lookup failed; leaving for next pass")
			}
			continue
		}
		// Found on the exchange: adopt its real state. Terminal states must
		// win over any concurrent armer PLACED write, so this is unguarded.
		status, _ := legStatusFromOrder(resp.Status)
		if r.updateLeg(ctx, record, leg, status, resp.OrderID) {
			summary.LegsResolved++
		}
	}
}

// demotePlacing releases a confirmed-absent PLACING claim to FAILED, guarded
// so a concurrent armer's PLACED write wins the race. Returns whether it
// applied.
func (r *StartupReconciler) demotePlacing(ctx context.Context, record *storage.BracketRecord, leg *storage.BracketLegRecord) bool {
	applied, err := r.store.UpdateLegStatusIf(ctx, record.BracketID, leg.ClientOrderID,
		storage.LegStatusPlacing, storage.LegStatusFailed, 0)
	if err != nil {
		r.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
			Msg("reconciler: failed to demote PLACING leg")
		return false
	}
	if applied {
		leg.Status = storage.LegStatusFailed
	}
	return applied
}

// getOrderWithRepoll looks an order up by client id, re-polling on -2013 to
// bridge the exchange's post-accept visibility lag (#193).
func (r *StartupReconciler) getOrderWithRepoll(
	ctx context.Context,
	client *binance.Client,
	symbol, clientOrderID string,
) (*binance.OrderResponse, error) {
	resp, err := client.GetOrderByClientID(ctx, symbol, clientOrderID)
	for attempt := 0; attempt < ocoRepollAttempts && err != nil && rest.IsOrderNotFound(err); attempt++ {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(ocoRepollDelay):
		}
		resp, err = client.GetOrderByClientID(ctx, symbol, clientOrderID)
	}
	return resp, err
}

// sweepExitLegs observes the exchange state of every placed exit leg,
// forwards transitions to the engine, and settles the bracket.
//
// Closure semantics are venue-specific. Futures exits are position-scoped:
// an SL fill closed the whole position, so resting TPs are cancelled (and
// vice versa). Spot exits are slice-scoped OCO pairs: the exchange cancels
// each pair's sibling itself, and cancelling another slice's leg would
// strip a live stop off a still-open sub-position — so spot never cancels,
// it only closes the bracket once every exit leg is terminal.
func (r *StartupReconciler) sweepExitLegs(
	ctx context.Context,
	client *binance.Client,
	record *storage.BracketRecord,
	summary *ReconcileSummary,
) {
	for i := range record.Legs {
		leg := &record.Legs[i]
		if leg.Role == "ENTRY" {
			continue
		}
		switch leg.Status {
		case storage.LegStatusPlaced, storage.LegStatusPlanned:
			// PLANNED under LEGS_PLACED means a crash in persistPlacementOutcome's
			// window (bracket status written before leg statuses) left a live
			// exit unrecorded — resolve it against the exchange like a placed leg.
			r.sweepOneExitLeg(ctx, client, record, leg, summary)
		case storage.LegStatusFailed:
			// A FAILED exit is unprotected coverage that keeps the bracket
			// open; the armers own re-placement, so surface it, don't settle.
			summary.UnrepairedLegs++
			r.logger.Warn().
				Str("bracket_id", record.BracketID.String()).
				Str("client_order_id", leg.ClientOrderID).
				Str("role", leg.Role).
				Msg("reconciler: LEGS_PLACED bracket has a FAILED exit leg; awaiting re-arm")
		}
	}

	r.settleBracket(ctx, client, record, summary)
}

// sweepOneExitLeg resolves one exit leg against the exchange, persisting and
// emitting any terminal transition. -2013 on a leg the DB thinks is live is
// a real anomaly (surfaced), not a silent skip.
func (r *StartupReconciler) sweepOneExitLeg(
	ctx context.Context,
	client *binance.Client,
	record *storage.BracketRecord,
	leg *storage.BracketLegRecord,
	summary *ReconcileSummary,
) {
	resp, err := client.GetOrderByClientID(ctx, record.Symbol, leg.ClientOrderID)
	if err != nil {
		summary.Errors++
		if rest.IsOrderNotFound(err) {
			summary.UnrepairedLegs++
			r.logger.Warn().
				Str("client_order_id", leg.ClientOrderID).
				Str("status", leg.Status).
				Msg("reconciler: exit leg not found on exchange; leaving for re-arm")
		} else {
			r.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
				Msg("reconciler: exit leg lookup failed")
		}
		return
	}
	status, working := legStatusFromOrder(resp.Status)
	if working {
		if leg.Status == storage.LegStatusPlanned {
			// Record that the exit is in fact live so settlement and the
			// engine both see it.
			r.updateLeg(ctx, record, leg, status, resp.OrderID)
		}
		return
	}
	if !r.updateLeg(ctx, record, leg, status, resp.OrderID) {
		return // persist failed; re-observed next pass, no premature emit
	}
	summary.ExitLegsUpdated++
}

func (r *StartupReconciler) settleBracket(
	ctx context.Context,
	client *binance.Client,
	record *storage.BracketRecord,
	summary *ReconcileSummary,
) {
	slFilled, allTPsFilled, allTerminal := exitLegOutcomes(record)

	if record.Venue == "USD_M" {
		if slFilled {
			r.cancelFuturesLegs(ctx, client, record, "TP", summary)
			r.closeBracket(ctx, record, summary)
			return
		}
		if allTPsFilled {
			r.cancelFuturesLegs(ctx, client, record, "SL", summary)
			r.closeBracket(ctx, record, summary)
			return
		}
	}
	if allTerminal {
		r.closeBracket(ctx, record, summary)
	}
}

// exitLegOutcomes reduces the exit legs to the three signals settlement
// needs. FAILED legs count as non-terminal: they represent protection that
// never reached the exchange.
func exitLegOutcomes(record *storage.BracketRecord) (slFilled, allTPsFilled, allTerminal bool) {
	tpCount := 0
	allTPsFilled = true
	allTerminal = true
	for _, leg := range record.Legs {
		if leg.Role == "ENTRY" {
			continue
		}
		switch leg.Status {
		case storage.LegStatusFilled:
			if leg.Role == "SL" {
				slFilled = true
			}
		case storage.LegStatusCanceled, storage.LegStatusExpired:
		default:
			allTerminal = false
		}
		if leg.Role == "TP" {
			tpCount++
			if leg.Status != storage.LegStatusFilled {
				allTPsFilled = false
			}
		}
	}
	if tpCount == 0 {
		allTPsFilled = false
	}
	return slFilled, allTPsFilled, allTerminal
}

func (r *StartupReconciler) cancelFuturesLegs(
	ctx context.Context,
	client *binance.Client,
	record *storage.BracketRecord,
	role string,
	summary *ReconcileSummary,
) {
	for i := range record.Legs {
		leg := &record.Legs[i]
		if leg.Role != role || leg.Status != storage.LegStatusPlaced || leg.ExchangeOrderID == 0 {
			continue
		}
		if _, err := client.CancelOrder(ctx, record.Symbol, leg.ExchangeOrderID); err != nil {
			summary.Errors++
			r.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
				Msg("reconciler: sibling cancel failed; next pass retries")
			continue
		}
		r.updateLeg(ctx, record, leg, storage.LegStatusCanceled, leg.ExchangeOrderID)
	}
}

func (r *StartupReconciler) closeBracket(ctx context.Context, record *storage.BracketRecord, summary *ReconcileSummary) {
	if err := r.store.UpdateBracketStatus(ctx, record.BracketID, storage.BracketStatusClosed); err != nil {
		summary.Errors++
		r.logger.Warn().Err(err).Str("bracket_id", record.BracketID.String()).
			Msg("reconciler: failed to close bracket")
		return
	}
	record.Status = storage.BracketStatusClosed
	summary.BracketsClosed++
}

// updateLeg persists a leg status and mirrors it onto the in-memory record.
// Returns whether the write landed, so callers only count/emit real repairs.
func (r *StartupReconciler) updateLeg(
	ctx context.Context,
	record *storage.BracketRecord,
	leg *storage.BracketLegRecord,
	status string,
	exchangeOrderID int64,
) bool {
	if err := r.store.UpdateLegStatus(ctx, record.BracketID, leg.ClientOrderID, status, exchangeOrderID); err != nil {
		r.logger.Warn().Err(err).
			Str("client_order_id", leg.ClientOrderID).
			Str("status", status).
			Msg("reconciler: failed to persist leg status")
		return false
	}
	leg.Status = status
	if exchangeOrderID != 0 {
		leg.ExchangeOrderID = exchangeOrderID
	}
	return true
}

// legStatusFromOrder maps an exchange order status onto a leg status. Only
// NEW/PARTIALLY_FILLED are still working; every other status is terminal, so
// unknown values are treated as EXPIRED (drop protection loudly) rather than
// silently kept as live — recording a dead order as live protection is the
// exact failure C6 exists to prevent.
func legStatusFromOrder(orderStatus string) (status string, working bool) {
	switch normalizeOrderStatus(orderStatus) {
	case "NEW", "PARTIALLY_FILLED", "PENDING_NEW":
		return storage.LegStatusPlaced, true
	case "FILLED":
		return storage.LegStatusFilled, false
	case "CANCELED", "PENDING_CANCEL":
		return storage.LegStatusCanceled, false
	case "EXPIRED", "EXPIRED_IN_MATCH":
		return storage.LegStatusExpired, false
	case "REJECTED":
		return storage.LegStatusFailed, false
	default:
		return storage.LegStatusExpired, false
	}
}
