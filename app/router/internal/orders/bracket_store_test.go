package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

type fakeBracketStore struct {
	mu             sync.Mutex
	reserveErr     error
	updateErr      error
	existingRecord *storage.BracketRecord // nil => this store wins the insert

	reserved       []storage.BracketRecord
	bracketUpdates []string
	legUpdates     map[string]string
}

func newFakeBracketStore() *fakeBracketStore {
	return &fakeBracketStore{legUpdates: make(map[string]string)}
}

func TestPersistPlacementOutcomePreservesImmediateFill(t *testing.T) {
	store := newFakeBracketStore()
	manager := NewManager(nil, nil, nil, zerolog.Nop())
	manager.SetBracketStore(store)
	bracketID := uuid.New()

	err := manager.persistPlacementOutcome(
		context.Background(),
		bracketID,
		&bracketPlacementResult{
			IDs: ClientOrderIDs{Main: "filled-entry"},
			Main: &binance.OrderResponse{
				OrderID: 42, ClientOrderID: "filled-entry", Status: "FILLED",
			},
		},
		false,
		true,
	)

	require.NoError(t, err)
	assert.Equal(t, storage.LegStatusFilled, store.legUpdates["filled-entry"])
}

func (f *fakeBracketStore) Reserve(_ context.Context, rec storage.BracketRecord) (*storage.BracketRecord, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.reserveErr != nil {
		return nil, false, f.reserveErr
	}
	f.reserved = append(f.reserved, rec)
	if f.existingRecord != nil {
		return f.existingRecord, false, nil
	}
	stored := rec
	if stored.BracketID == uuid.Nil {
		stored.BracketID = uuid.New()
	}
	return &stored, true, nil
}

func (f *fakeBracketStore) UpdateBracketStatus(_ context.Context, _ uuid.UUID, status string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.bracketUpdates = append(f.bracketUpdates, status)
	if f.updateErr != nil {
		return f.updateErr
	}
	return nil
}

func (f *fakeBracketStore) UpdateBracketStatusIf(_ context.Context, _ uuid.UUID, _, status string) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.bracketUpdates = append(f.bracketUpdates, status)
	if f.updateErr != nil {
		return false, f.updateErr
	}
	return true, nil
}

func (f *fakeBracketStore) UpdateLegStatus(_ context.Context, _ uuid.UUID, clientOrderID, status string, _ int64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.legUpdates[clientOrderID] = status
	return nil
}

// bracketExchange serves the order endpoints, recording POSTed ids.
type bracketExchange struct {
	mu             sync.Mutex
	orderPath      string // defaults to /fapi/v1/order
	postedIDs      []string
	getStatus      int             // GET order: 200 live order, else -2013
	getOrderStatus string          // order status served on GET 200 (default NEW)
	getExecutedQty string          // executed qty served on GET 200 (default "0")
	postDupIDs     map[string]bool // POSTs of these ids are rejected as -4116 duplicates
	failPosts      bool            // all POSTs fail with a non-retryable -1102
	postStarted    chan struct{}
	releasePost    <-chan struct{}
	postStartOnce  sync.Once
}

func (f *bracketExchange) posted() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.postedIDs...)
}

func (f *bracketExchange) handler() http.HandlerFunc {
	orderPath := f.orderPath
	if orderPath == "" {
		orderPath = "/fapi/v1/order"
	}
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != orderPath {
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
			return
		}
		q := r.URL.Query()
		switch r.Method {
		case http.MethodPost:
			clientOrderID := q.Get("newClientOrderId")
			if f.postStarted != nil {
				f.postStartOnce.Do(func() { close(f.postStarted) })
			}
			if f.releasePost != nil {
				<-f.releasePost
			}
			if f.failPosts {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-1102,"msg":"Mandatory parameter was not sent."}`))
				return
			}
			if f.postDupIDs[clientOrderID] {
				f.mu.Lock()
				f.postedIDs = append(f.postedIDs, clientOrderID)
				f.mu.Unlock()
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-4116,"msg":"Duplicate order sent."}`))
				return
			}
			orDefault := func(v string) string {
				if v == "" {
					return "0"
				}
				return v
			}
			f.mu.Lock()
			f.postedIDs = append(f.postedIDs, clientOrderID)
			count := len(f.postedIDs)
			f.mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId": 1000 + count, "symbol": q.Get("symbol"), "status": "NEW",
				"clientOrderId": clientOrderID, "price": orDefault(q.Get("price")), "avgPrice": "0",
				"origQty": orDefault(q.Get("quantity")), "executedQty": "0", "cumQty": "0", "cumQuote": "0",
				"timeInForce": "GTC", "type": q.Get("type"), "reduceOnly": false,
				"closePosition": q.Get("closePosition") == "true", "side": q.Get("side"),
				"positionSide": "BOTH", "stopPrice": orDefault(q.Get("stopPrice")), "workingType": "CONTRACT_PRICE",
				"priceProtect": false, "origType": q.Get("type"), "updateTime": 1,
			})
		case http.MethodGet:
			if f.getStatus == http.StatusOK {
				orderStatus := f.getOrderStatus
				if orderStatus == "" {
					orderStatus = "NEW"
				}
				executedQty := f.getExecutedQty
				if executedQty == "" {
					executedQty = "0"
				}
				_ = json.NewEncoder(w).Encode(map[string]any{
					"orderId": 777, "symbol": q.Get("symbol"), "status": orderStatus,
					"clientOrderId": q.Get("origClientOrderId"), "price": "50000", "avgPrice": "0",
					"origQty": "0.02", "executedQty": executedQty, "cumQuote": "0",
					"timeInForce": "GTC", "type": "LIMIT", "side": "BUY",
					"stopPrice": "0", "updateTime": 1,
				})
				return
			}
			w.WriteHeader(http.StatusBadRequest)
			_, _ = w.Write([]byte(`{"code":-2013,"msg":"Order does not exist."}`))
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	}
}

type rwExecutionGate struct {
	mu       sync.RWMutex
	state    string
	acquired chan struct{}
	once     sync.Once
}

func (g *rwExecutionGate) AcquirePlacement(_ context.Context) (string, func() error, error) {
	g.mu.RLock()
	if g.acquired != nil {
		g.once.Do(func() { close(g.acquired) })
	}
	return g.state, func() error {
		g.mu.RUnlock()
		return nil
	}, nil
}

func (g *rwExecutionGate) AcquireEmergency(_ context.Context) (string, func() error, error) {
	g.mu.Lock()
	return g.state, func() error {
		g.mu.Unlock()
		return nil
	}, nil
}

func (g *rwExecutionGate) halt() {
	g.mu.Lock()
	g.state = storage.ExecutionStateHalted
	g.mu.Unlock()
}

func newStoreFixture(t *testing.T, fake *bracketExchange, store *fakeBracketStore) *Manager {
	t.Helper()
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	require.NoError(t, err)

	manager := NewManager(nil, futuresClient, nil, logger)
	if store != nil {
		manager.SetBracketStore(store)
	}
	return manager
}

func storeBracketRequest() *PlaceBracketRequest {
	return &PlaceBracketRequest{
		IdempotencyKey:   "engine-decision-9",
		Symbol:           "BTCUSDT",
		Side:             "BUY",
		Quantity:         decimal.RequireFromString("0.02"),
		EntryPrice:       decimal.RequireFromString("50000"),
		TakeProfitPrices: []decimal.Decimal{decimal.RequireFromString("51000")},
		StopLossPrice:    decimal.RequireFromString("49000"),
		IsFutures:        true,
		ClientOrderIDs: &ClientOrderIDs{
			Main:        "engine-main-9",
			TakeProfits: []string{"engine-tp-9"},
			StopLoss:    "engine-sl-9",
		},
	}
}

func TestPlaceBracketOrder_ReservesAndPersistsOutcome(t *testing.T) {
	store := newFakeBracketStore()
	manager := newStoreFixture(t, &bracketExchange{}, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	require.Len(t, store.reserved, 1)
	reserved := store.reserved[0]
	assert.Equal(t, storage.BracketStatusReserved, reserved.Status)
	roles := map[string]string{}
	for _, leg := range reserved.Legs {
		roles[leg.ClientOrderID] = leg.Role + ":" + leg.Status
	}
	assert.Equal(t, map[string]string{
		"engine-main-9": "ENTRY:PLANNED",
		"engine-tp-9":   "TP:PLANNED",
		"engine-sl-9":   "SL:PLANNED",
	}, roles)

	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
	assert.Equal(t, map[string]string{
		"engine-main-9": storage.LegStatusPlaced,
		"engine-tp-9":   storage.LegStatusPlaced,
		"engine-sl-9":   storage.LegStatusPlaced,
	}, store.legUpdates)
	assert.Equal(t, "engine-main-9", resp.ClientOrderIDs.Main)
}

func TestLostResponseReplayPlacesEntryOnce(t *testing.T) {
	existingID := uuid.New()
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          existingID,
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusEntryPlaced,
	}
	fake := &bracketExchange{getStatus: http.StatusOK}
	manager := newStoreFixture(t, fake, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.NotContains(t, fake.posted(), "engine-main-9",
		"replay must adopt the live entry, never re-POST it")
	assert.ElementsMatch(t, []string{"engine-tp-9", "engine-sl-9"}, fake.posted())
	assert.Equal(t, existingID.String(), resp.BracketOrderID)
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestPlaceBracketOrder_ReplayPlacesFreshWhenEntryInvisible(t *testing.T) {
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          uuid.New(),
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusReserved,
	}
	fake := &bracketExchange{getStatus: http.StatusBadRequest}
	manager := newStoreFixture(t, fake, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.ElementsMatch(t,
		[]string{"engine-main-9", "engine-tp-9", "engine-sl-9"}, fake.posted())
	assert.Equal(t, "engine-main-9", resp.ClientOrderIDs.Main)
}

func TestPlaceBracketOrder_CriticalFailurePersistsFailedStatus(t *testing.T) {
	store := newFakeBracketStore()
	manager := newStoreFixture(t, &bracketExchange{failPosts: true}, store)

	_, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.Equal(t, []string{storage.BracketStatusFailed}, store.bracketUpdates)
}

func TestPlaceBracketOrder_ReplayWithAllLegsLiveAdoptsEverything(t *testing.T) {
	existingID := uuid.New()
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          existingID,
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusLegsPlaced,
		Legs: []storage.BracketLegRecord{
			{Role: "ENTRY", ClientOrderID: "engine-main-9", Status: storage.LegStatusPlaced},
			{Role: "TP", TPIndex: 1, ClientOrderID: "engine-tp-9", Status: storage.LegStatusPlaced},
			{Role: "SL", ClientOrderID: "engine-sl-9", Status: storage.LegStatusPlaced},
		},
	}
	fake := &bracketExchange{
		getStatus:  http.StatusOK,
		postDupIDs: map[string]bool{"engine-tp-9": true, "engine-sl-9": true},
	}
	manager := newStoreFixture(t, fake, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.False(t, resp.PartialFailure)
	assert.NotContains(t, fake.posted(), "engine-main-9")
	assert.Equal(t, map[string]string{
		"engine-main-9": storage.LegStatusPlaced,
		"engine-tp-9":   storage.LegStatusPlaced,
		"engine-sl-9":   storage.LegStatusPlaced,
	}, store.legUpdates)
}

func TestPlaceBracketOrder_ReplayDivergentLegIDsFailsClosed(t *testing.T) {
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          uuid.New(),
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusEntryPlaced,
		Legs: []storage.BracketLegRecord{
			{Role: "ENTRY", ClientOrderID: "engine-main-9"},
			{Role: "TP", TPIndex: 1, ClientOrderID: "old-tp-id"},
			{Role: "SL", ClientOrderID: "old-sl-id"},
		},
	}
	fake := &bracketExchange{getStatus: http.StatusOK}
	manager := newStoreFixture(t, fake, store)

	_, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.Contains(t, err.Error(), "diverges from reservation")
	assert.Empty(t, fake.posted(), "divergent replay must not touch the exchange")
}

func TestReservationFailureDoesNotCallExchange(t *testing.T) {
	store := newFakeBracketStore()
	store.reserveErr = assert.AnError
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.Nil(t, resp)
	assert.Empty(t, fake.posted())
	assert.Empty(t, store.bracketUpdates, "no reservation id, so no status writes")
}

func TestActiveExecutionRequiresDurableStore(t *testing.T) {
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, nil)
	manager.RequireDurableStore()

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.ErrorIs(t, err, ErrExecutionDurabilityUnavailable)
	assert.Nil(t, resp)
	assert.Empty(t, fake.posted())
}

func TestActiveExecutionRequiresDurableExecutionControl(t *testing.T) {
	store := newFakeBracketStore()
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, store)
	manager.RequireDurableStore()

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.ErrorIs(t, err, ErrExecutionDurabilityUnavailable)
	assert.Nil(t, resp)
	assert.Empty(t, fake.posted())
}

func TestPlacementOutcomePersistenceFailureIsAmbiguous(t *testing.T) {
	store := newFakeBracketStore()
	store.updateErr = assert.AnError
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, store)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.Error(t, err)
	assert.ErrorIs(t, err, ErrExecutionDurabilityUnavailable)
	require.NotNil(t, resp)
	assert.Len(t, fake.posted(), 3)
	assert.Empty(t, manager.orders, "unacknowledged placement must not enter success state")
}

func TestPlacementWhileHaltedDoesNotCallExchange(t *testing.T) {
	store := newFakeBracketStore()
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, store)
	manager.SetExecutionGate(&rwExecutionGate{state: storage.ExecutionStateHalted})

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	assert.ErrorIs(t, err, ErrExecutionHalted)
	assert.Nil(t, resp)
	assert.Empty(t, fake.posted())
}

func TestHaltRacingPlacementDrainsBeforeAck(t *testing.T) {
	releasePost := make(chan struct{})
	fake := &bracketExchange{
		postStarted: make(chan struct{}),
		releasePost: releasePost,
	}
	manager := newStoreFixture(t, fake, newFakeBracketStore())
	gate := &rwExecutionGate{
		state:    storage.ExecutionStateRunning,
		acquired: make(chan struct{}),
	}
	manager.SetExecutionGate(gate)

	placementDone := make(chan error, 1)
	go func() {
		_, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())
		placementDone <- err
	}()
	<-fake.postStarted

	haltAck := make(chan struct{})
	go func() {
		gate.halt()
		close(haltAck)
	}()
	select {
	case <-haltAck:
		t.Fatal("halt acknowledged before in-flight placement drained")
	case <-time.After(20 * time.Millisecond):
	}

	close(releasePost)
	require.NoError(t, <-placementDone)
	select {
	case <-haltAck:
	case <-time.After(time.Second):
		t.Fatal("halt did not acknowledge after placement drained")
	}
}

func TestPlaceBracketOrder_LegsOnFillDefersExitLegs(t *testing.T) {
	store := newFakeBracketStore()
	fake := &bracketExchange{}
	manager := newStoreFixture(t, fake, store)
	manager.SetLegsOnFill(true)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.Equal(t, []string{"engine-main-9"}, fake.posted(),
		"only the entry may be POSTed before it fills")
	assert.True(t, resp.LegsPendingTrigger)
	assert.Equal(t, ClientOrderIDs{
		Main:        "engine-main-9",
		TakeProfits: []string{"engine-tp-9"},
		StopLoss:    "engine-sl-9",
	}, resp.ClientOrderIDs, "reserved exit-leg ids must still be reported")
	require.Len(t, store.reserved, 1)
	assert.True(t, store.reserved[0].LegsOnFill)
	assert.Equal(t, []string{storage.BracketStatusEntryPlaced}, store.bracketUpdates)
	assert.Equal(t, map[string]string{"engine-main-9": storage.LegStatusPlaced}, store.legUpdates,
		"exit legs must stay PLANNED for the armer")
}

func TestPlaceBracketOrder_LegsOnFillWithoutStoreStaysSynchronous(t *testing.T) {
	fake := &bracketExchange{}
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(nil, futuresClient, nil, zerolog.Nop())
	manager.SetLegsOnFill(true) // no bracket store installed

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.Len(t, fake.posted(), 3, "without durable legs, deferral would lose them on crash")
	assert.False(t, resp.LegsPendingTrigger)
}

func TestPlaceBracketOrder_ReplayAdoptedFilledEntryPlacesLegsSynchronously(t *testing.T) {
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          uuid.New(),
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusEntryPlaced,
		LegsOnFill:         true,
	}
	fake := &bracketExchange{
		getStatus:      http.StatusOK,
		getOrderStatus: "FILLED",
		getExecutedQty: "0.02",
	}
	manager := newStoreFixture(t, fake, store)
	manager.SetLegsOnFill(true)

	resp, err := manager.PlaceBracketOrder(context.Background(), storeBracketRequest())

	require.NoError(t, err)
	assert.ElementsMatch(t, []string{"engine-tp-9", "engine-sl-9"}, fake.posted(),
		"the fill event is gone forever; legs must place now, not wait for it")
	assert.False(t, resp.LegsPendingTrigger)
}

func TestPlaceBracketOrder_SpotReplayAdoptedFilledEntryKeepsLegsDeferred(t *testing.T) {
	store := newFakeBracketStore()
	store.existingRecord = &storage.BracketRecord{
		BracketID:          uuid.New(),
		Venue:              "SPOT",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		EntryClientOrderID: "engine-main-9",
		Status:             storage.BracketStatusEntryPlaced,
		LegsOnFill:         true,
	}
	fake := &bracketExchange{
		orderPath:      "/api/v3/order",
		getStatus:      http.StatusOK,
		getOrderStatus: "FILLED",
		getExecutedQty: "0.02",
	}
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	spotRest := rest.NewClient(server.URL, signer)
	spotClient, err := binance.NewSpotClient(server.URL, signer, spotRest, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(spotClient, nil, nil, zerolog.Nop())
	manager.SetBracketStore(store)
	manager.SetSpotLegsOnFill(true)

	req := storeBracketRequest()
	req.IsFutures = false

	resp, err := manager.PlaceBracketOrder(context.Background(), req)

	require.NoError(t, err)
	assert.Empty(t, fake.posted(),
		"a spot replay must neither re-POST the entry nor fall back to the synchronous exit path")
	assert.True(t, resp.LegsPendingTrigger,
		"the entry-fill watcher owns spot exits even when the adopted entry is already filled")
}

func TestPlaceBracketOrder_SpotLegsOnFillDefersExitsForOCO(t *testing.T) {
	store := newFakeBracketStore()
	fake := &bracketExchange{orderPath: "/api/v3/order"}
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)
	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	spotRest := rest.NewClient(server.URL, signer)
	spotClient, err := binance.NewSpotClient(server.URL, signer, spotRest, zerolog.Nop())
	require.NoError(t, err)
	manager := NewManager(spotClient, nil, nil, zerolog.Nop())
	manager.SetBracketStore(store)
	manager.SetSpotLegsOnFill(true)

	req := storeBracketRequest()
	req.IsFutures = false

	resp, err := manager.PlaceBracketOrder(context.Background(), req)

	require.NoError(t, err)
	assert.Equal(t, []string{"engine-main-9"}, fake.posted(),
		"spot exits must wait for the watcher's OCO placement")
	assert.True(t, resp.LegsPendingTrigger)
	require.Len(t, store.reserved, 1)
	assert.True(t, store.reserved[0].LegsOnFill)
	assert.Equal(t, []string{storage.BracketStatusEntryPlaced}, store.bracketUpdates)
}
