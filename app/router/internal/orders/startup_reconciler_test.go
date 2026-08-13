package orders

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

// reconExchange serves per-client-order-id lookups and cancels on both
// venue order paths.
type reconExchange struct {
	mu       sync.Mutex
	orders   map[string]map[string]any // keyed by clientOrderId
	canceled []int64
}

func newReconExchange() *reconExchange {
	return &reconExchange{orders: map[string]map[string]any{}}
}

func (f *reconExchange) set(clientOrderID string, fields map[string]any) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.orders[clientOrderID] = fields
}

func (f *reconExchange) canceledIDs() []int64 {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]int64(nil), f.canceled...)
}

func (f *reconExchange) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		isOrderPath := r.URL.Path == "/api/v3/order" || r.URL.Path == "/fapi/v1/order"
		switch {
		case r.Method == http.MethodGet && isOrderPath:
			f.mu.Lock()
			resp, ok := f.orders[q.Get("origClientOrderId")]
			f.mu.Unlock()
			if !ok {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2013,"msg":"Order does not exist."}`))
				return
			}
			_ = json.NewEncoder(w).Encode(resp)
		case r.Method == http.MethodDelete && isOrderPath:
			orderID, _ := strconv.ParseInt(q.Get("orderId"), 10, 64)
			f.mu.Lock()
			f.canceled = append(f.canceled, orderID)
			f.mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": q.Get("symbol"), "orderId": orderID, "status": "CANCELED",
				"clientOrderId": "canceled", "origQty": "0.02", "executedQty": "0",
				"price": "0", "cummulativeQuoteQty": "0", "timeInForce": "GTC",
				"type": "LIMIT", "side": "SELL",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}
}

func exchangeOrder(clientOrderID, status, executedQty string, orderID int64) map[string]any {
	return map[string]any{
		"symbol": "BTCUSDT", "orderId": orderID, "clientOrderId": clientOrderID,
		"price": "51000", "origQty": "0.02", "executedQty": executedQty,
		"cummulativeQuoteQty": "0", "status": status, "timeInForce": "GTC",
		"type": "LIMIT", "side": "SELL", "updateTime": 1,
	}
}

// recordingEmitter captures every emitted update (mockSuccessEmitter only
// keeps the last one).
type recordingEmitter struct {
	mu      sync.Mutex
	updates []*OrderUpdate
}

func (e *recordingEmitter) EmitOrderUpdate(_ context.Context, update *OrderUpdate) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.updates = append(e.updates, update)
	return nil
}

func (e *recordingEmitter) emitted() []*OrderUpdate {
	e.mu.Lock()
	defer e.mu.Unlock()
	return append([]*OrderUpdate(nil), e.updates...)
}

func newReconcilerFixture(
	t *testing.T,
	handler http.HandlerFunc,
	store *fakeWatcherStore,
	venue string,
) (*StartupReconciler, *recordingEmitter) {
	t.Helper()
	server := httptest.NewServer(handler)
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	restClient := rest.NewClient(server.URL, signer)

	var spotClient, futuresClient *binance.Client
	var err error
	if venue == "USD_M" {
		futuresClient, err = binance.NewFuturesClient(server.URL, signer, restClient, logger)
	} else {
		spotClient, err = binance.NewSpotClient(server.URL, signer, restClient, logger)
	}
	require.NoError(t, err)

	emitter := &recordingEmitter{}
	watcher := NewEntryFillWatcher(store, spotClient, nil, futuresClient, nil, time.Millisecond, time.Hour, logger)
	reconciler := NewStartupReconciler(store, watcher, spotClient, futuresClient, emitter, time.Hour, logger)
	return reconciler, emitter
}

// fastReconRepoll shrinks the -2013 repoll so confirmed-absent tests do not
// sleep.
func fastReconRepoll(t *testing.T) {
	t.Helper()
	prevDelay, prevAttempts := ocoRepollDelay, ocoRepollAttempts
	ocoRepollDelay, ocoRepollAttempts = time.Millisecond, 1
	t.Cleanup(func() { ocoRepollDelay, ocoRepollAttempts = prevDelay, prevAttempts })
}

// raceOnDemoteStore simulates a concurrent armer that flips a leg to a new
// status the instant before the reconciler's guarded demote runs.
type raceOnDemoteStore struct {
	fakeWatcherStore
	flipTo  string
	flipLeg string
	flipped bool
}

func (s *raceOnDemoteStore) UpdateLegStatusIf(ctx context.Context, bracketID uuid.UUID, clientOrderID, expected, status string, exchangeOrderID int64) (bool, error) {
	if !s.flipped && clientOrderID == s.flipLeg {
		s.flipped = true
		// The armer wins: the leg is no longer PLACING when the CAS lands
		for i := range s.record.Legs {
			if s.record.Legs[i].ClientOrderID == s.flipLeg {
				s.record.Legs[i].Status = s.flipTo
			}
		}
	}
	return s.fakeWatcherStore.UpdateLegStatusIf(ctx, bracketID, clientOrderID, expected, status, exchangeOrderID)
}

// legsPlacedRecord returns a bracket whose exits are live on the exchange.
func legsPlacedRecord(venue string) *storage.BracketRecord {
	rec := armerRecord()
	rec.Venue = venue
	rec.Status = storage.BracketStatusLegsPlaced
	rec.Legs[1].Status = storage.LegStatusPlaced
	rec.Legs[1].ExchangeOrderID = 101
	rec.Legs[2].Status = storage.LegStatusPlaced
	rec.Legs[2].ExchangeOrderID = 102
	return rec
}

func TestStartupReconciler_SpotExitFillsCloseBracket(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("SPOT")}}
	fake := newReconExchange()
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	fake.set("arm-sl", exchangeOrder("arm-sl", "EXPIRED", "0", 102))
	reconciler, emitter := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, &ReconcileSummary{
		BracketsSwept:   1,
		ExitLegsUpdated: 2,
		BracketsClosed:  1,
	}, summary)
	assert.Contains(t, store.legUpdates, "arm-tp1:FILLED")
	assert.Contains(t, store.legUpdates, "arm-sl:EXPIRED")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
	assert.Empty(t, emitter.emitted(), "the transactional leg-status trigger owns delivery")
	assert.Empty(t, fake.canceledIDs(), "spot sibling-cancel belongs to the exchange")
}

func TestStartupReconciler_SpotOpenExitsStayOpen(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("SPOT")}}
	fake := newReconExchange()
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "NEW", "0", 101))
	fake.set("arm-sl", exchangeOrder("arm-sl", "NEW", "0", 102))
	reconciler, emitter := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 0, summary.ExitLegsUpdated)
	assert.Empty(t, store.bracketUpdates, "working exits must keep the bracket open")
	assert.Empty(t, emitter.emitted())
}

func TestStartupReconciler_SpotNeverCancelsSiblingSlices(t *testing.T) {
	record := legsPlacedRecord("SPOT")
	record.Legs = append(record.Legs,
		storage.BracketLegRecord{Role: "TP", TPIndex: 2, ClientOrderID: "arm-tp2",
			Status: storage.LegStatusPlaced, ExchangeOrderID: 103, Price: decimal.RequireFromString("52000")},
		storage.BracketLegRecord{Role: "SL", TPIndex: 1, ClientOrderID: "arm-sl-1",
			Status: storage.LegStatusPlaced, ExchangeOrderID: 104, StopPrice: decimal.RequireFromString("49000")},
	)
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	// Slice 0's stop filled and its sibling TP expired; slice 1 still works
	fake.set("arm-sl", exchangeOrder("arm-sl", "FILLED", "0.01", 102))
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "EXPIRED", "0", 101))
	fake.set("arm-tp2", exchangeOrder("arm-tp2", "NEW", "0", 103))
	fake.set("arm-sl-1", exchangeOrder("arm-sl-1", "NEW", "0", 104))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Empty(t, fake.canceledIDs(),
		"cancelling one slice's legs would strip live stops off sibling OCO slices")
	assert.Empty(t, store.bracketUpdates, "slice 1 still protects an open sub-position")
	assert.Equal(t, 2, summary.ExitLegsUpdated)
}

func TestStartupReconciler_FuturesSLFillCancelsTPsAndCloses(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("USD_M")}}
	fake := newReconExchange()
	fake.set("arm-sl", exchangeOrder("arm-sl", "FILLED", "0.02", 102))
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "NEW", "0", 101))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, []int64{101}, fake.canceledIDs(),
		"the SL closed the position; resting TPs must be cancelled")
	assert.Contains(t, store.legUpdates, "arm-sl:FILLED")
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
	assert.Equal(t, 1, summary.BracketsClosed)
}

func TestStartupReconciler_FuturesAllTPsFilledCancelsSL(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("USD_M")}}
	fake := newReconExchange()
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	fake.set("arm-sl", exchangeOrder("arm-sl", "NEW", "0", 102))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	_, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, []int64{102}, fake.canceledIDs())
	assert.Contains(t, store.legUpdates, "arm-sl:CANCELED")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
}

func TestStartupReconciler_FuturesStalePlacingLegAdopted(t *testing.T) {
	record := armerRecord() // USD_M, ENTRY_PLACED
	record.Status = storage.BracketStatusEntryFilled
	record.Legs[1].Status = storage.LegStatusPlacing // crashed mid-placement
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	fake.set("arm-main", exchangeOrder("arm-main", "FILLED", "0.02", 100))
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "NEW", "0", 555))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 1, summary.LegsResolved)
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Equal(t, int64(555), store.legExchangeIDs["arm-tp1"],
		"the live order's exchange id must be adopted, not re-POSTed")
}

func TestStartupReconciler_FuturesStalePlacingLegConfirmedAbsentFails(t *testing.T) {
	fastReconRepoll(t)
	record := armerRecord()
	record.Status = storage.BracketStatusEntryFilled
	record.Legs[1].Status = storage.LegStatusPlacing
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	fake.set("arm-main", exchangeOrder("arm-main", "FILLED", "0.02", 100))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 1, summary.LegsResolved)
	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED",
		"a PLACING leg the exchange never saw must become re-claimable")
}

func TestStartupReconciler_PlacingDemoteYieldsToConcurrentArmerWrite(t *testing.T) {
	fastReconRepoll(t)
	record := armerRecord()
	record.Status = storage.BracketStatusEntryFilled
	record.Legs[1].Status = storage.LegStatusPlacing
	// A concurrent armer places the leg PLACED between the reconciler's DB
	// load and its guarded demote; the CAS on PLACING must not overwrite it.
	store := &raceOnDemoteStore{
		fakeWatcherStore: fakeWatcherStore{fakeArmerStore{record: record}},
		flipTo:           storage.LegStatusPlaced,
		flipLeg:          "arm-tp1",
	}
	fake := newReconExchange()
	fake.set("arm-main", exchangeOrder("arm-main", "FILLED", "0.02", 100))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), &store.fakeWatcherStore, "USD_M")
	// Rebuild against the racing store
	reconciler.store = store

	_, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.NotContains(t, store.legUpdates, "arm-tp1:FAILED",
		"the guarded demote must lose to a concurrent PLACED write")
	assert.Equal(t, storage.LegStatusPlaced, legByClientOrderID(store.record, "arm-tp1").Status)
}

func TestStartupReconciler_LegsPlacedWithPlannedLegAdoptsLiveExit(t *testing.T) {
	// Crash in persistPlacementOutcome's window: bracket LEGS_PLACED but a
	// leg still PLANNED though live on the exchange.
	record := legsPlacedRecord("SPOT")
	record.Legs[1].Status = storage.LegStatusPlanned
	record.Legs[1].ExchangeOrderID = 0
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "NEW", "0", 101)) // live, working
	fake.set("arm-sl", exchangeOrder("arm-sl", "NEW", "0", 102))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED",
		"a PLANNED-but-live exit must be recorded so settlement sees it")
	assert.Equal(t, int64(101), store.legExchangeIDs["arm-tp1"])
	assert.Empty(t, store.bracketUpdates, "both exits still working; bracket stays open")
	assert.Equal(t, 0, summary.UnrepairedLegs)
}

func TestStartupReconciler_LegsPlacedWithFailedLegCountedNotClosed(t *testing.T) {
	record := legsPlacedRecord("SPOT")
	record.Legs[1].Status = storage.LegStatusFailed // never reached the exchange
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	fake.set("arm-sl", exchangeOrder("arm-sl", "NEW", "0", 102))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 1, summary.UnrepairedLegs,
		"an unprotected FAILED exit must be surfaced, not silently skipped")
	assert.Empty(t, store.bracketUpdates, "a bracket with unplaced protection must not be closed")
}

func TestStartupReconciler_ExpiredInMatchDropsProtection(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("SPOT")}}
	fake := newReconExchange()
	// STP-expired SL must be recorded terminal, not kept as live protection
	fake.set("arm-sl", exchangeOrder("arm-sl", "EXPIRED_IN_MATCH", "0", 102))
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	_, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Contains(t, store.legUpdates, "arm-sl:EXPIRED",
		"EXPIRED_IN_MATCH is terminal; recording it PLACED would claim a dead stop is live")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
}

func TestStartupReconciler_FuturesSLAndTPBothFilledClosesOnce(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("USD_M")}}
	fake := newReconExchange()
	fake.set("arm-sl", exchangeOrder("arm-sl", "FILLED", "0.02", 102))
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Empty(t, fake.canceledIDs(), "both legs already terminal; nothing to cancel")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
	assert.Equal(t, 1, summary.BracketsClosed)
}

func TestStartupReconciler_TerminalPlacingLegReliesOnTransactionalTrigger(t *testing.T) {
	record := legsPlacedRecord("USD_M")
	record.Legs[1].Status = storage.LegStatusPlacing // crashed mid-placement
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange()
	// The TP filled while the router was down; the fill was never emitted
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	fake.set("arm-sl", exchangeOrder("arm-sl", "NEW", "0", 102))
	reconciler, emitter := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	_, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Contains(t, store.legUpdates, "arm-tp1:FILLED")
	assert.Empty(t, emitter.emitted(), "the reconciler must not duplicate the database-triggered event")
}

func TestStartupReconciler_StaleReservedCountedNotClosed(t *testing.T) {
	record := armerRecord()
	record.Status = storage.BracketStatusReserved
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := newReconExchange() // entry unknown everywhere
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "USD_M")

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 1, summary.StaleReserved)
	assert.Empty(t, store.bracketUpdates,
		"closing a reservation can race an in-flight engine replay")
	assert.Empty(t, store.legUpdates)
}

func TestStartupReconciler_EntryPhaseArmsThroughWatcher(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{}
	armer, spotClient := newSpotArmerFixture(t, fake, &store.fakeArmerStore)
	watcher := NewEntryFillWatcher(store, spotClient, armer, nil, nil, time.Millisecond, time.Hour, zerolog.Nop())
	reconciler := NewStartupReconciler(store, watcher, spotClient, nil, nil, time.Hour, zerolog.Nop())

	summary, err := reconciler.Reconcile(context.Background())

	require.NoError(t, err)
	assert.Equal(t, 1, summary.EntriesChecked)
	require.Len(t, fake.requests(), 1, "a filled deferred entry must arm its OCO exits")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

// blockingStore gates LoadOpenBrackets so a pass can be held in flight.
type blockingStore struct {
	fakeWatcherStore
	release chan struct{}
}

func (b *blockingStore) LoadOpenBrackets(ctx context.Context, lookback time.Duration) ([]storage.BracketRecord, error) {
	<-b.release
	return b.fakeWatcherStore.LoadOpenBrackets(ctx, lookback)
}

func TestStartupReconciler_StatusCachesLastCompletedPass(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: legsPlacedRecord("SPOT")}}
	fake := newReconExchange()
	fake.set("arm-tp1", exchangeOrder("arm-tp1", "FILLED", "0.02", 101))
	fake.set("arm-sl", exchangeOrder("arm-sl", "EXPIRED", "0", 102))
	reconciler, _ := newReconcilerFixture(t, fake.handler(), store, "SPOT")

	before := reconciler.Status()
	require.False(t, before.HasRun, "no pass has run yet")

	summary, err := reconciler.Reconcile(context.Background())
	require.NoError(t, err)

	after := reconciler.Status()
	assert.True(t, after.HasRun)
	require.NotNil(t, after.Summary)
	assert.Equal(t, *summary, *after.Summary, "status must reflect the last pass")
	require.NotNil(t, after.LastRunAt)
	// The cached summary is a copy: mutating it must not change the source
	after.Summary.BracketsClosed = 999
	assert.NotEqual(t, 999, reconciler.Status().Summary.BracketsClosed)
}

func TestStartupReconciler_SingleFlight(t *testing.T) {
	store := &blockingStore{
		fakeWatcherStore: fakeWatcherStore{fakeArmerStore{record: nil}},
		release:          make(chan struct{}),
	}
	fake := newReconExchange()
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	spotClient, err := binance.NewSpotClient(server.URL, signer, rest.NewClient(server.URL, signer), zerolog.Nop())
	require.NoError(t, err)
	watcher := NewEntryFillWatcher(store, spotClient, nil, nil, nil, time.Millisecond, time.Hour, zerolog.Nop())
	reconciler := NewStartupReconciler(store, watcher, spotClient, nil, nil, time.Hour, zerolog.Nop())

	firstDone := make(chan error, 1)
	go func() {
		_, err := reconciler.Reconcile(context.Background())
		firstDone <- err
	}()

	require.Eventually(t, func() bool {
		_, err := reconciler.Reconcile(context.Background())
		return errors.Is(err, ErrReconcileInFlight)
	}, time.Second, 5*time.Millisecond, "a concurrent pass must be rejected")

	close(store.release)
	require.NoError(t, <-firstDone)

	_, err = reconciler.Reconcile(context.Background())
	assert.NoError(t, err, "the gate must be released after the pass completes")
}
