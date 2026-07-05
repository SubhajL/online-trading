package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
	"router/internal/websocket"
)

// fakeArmerStore implements armerStore over a single mutable record.
type fakeArmerStore struct {
	mu             sync.Mutex
	record         *storage.BracketRecord
	bracketUpdates []string
	legUpdates     []string // "clientOrderID:status"
}

func (f *fakeArmerStore) get(clientOrderID string, entryOnly bool) *storage.BracketRecord {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.record == nil {
		return nil
	}
	if entryOnly {
		if f.record.EntryClientOrderID == clientOrderID {
			rec := *f.record
			rec.Legs = append([]storage.BracketLegRecord(nil), f.record.Legs...)
			return &rec
		}
		return nil
	}
	for _, leg := range f.record.Legs {
		if leg.ClientOrderID == clientOrderID && leg.Role != "ENTRY" {
			rec := *f.record
			rec.Legs = append([]storage.BracketLegRecord(nil), f.record.Legs...)
			return &rec
		}
	}
	return nil
}

func (f *fakeArmerStore) GetByEntryClientOrderID(_ context.Context, _, entryClientOrderID string) (*storage.BracketRecord, error) {
	return f.get(entryClientOrderID, true), nil
}

func (f *fakeArmerStore) GetByLegClientOrderID(_ context.Context, _, clientOrderID string) (*storage.BracketRecord, error) {
	return f.get(clientOrderID, false), nil
}

func (f *fakeArmerStore) TryMarkLegPlacing(_ context.Context, _ uuid.UUID, clientOrderID string) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	for i := range f.record.Legs {
		if f.record.Legs[i].ClientOrderID == clientOrderID &&
			(f.record.Legs[i].Status == storage.LegStatusPlanned ||
				f.record.Legs[i].Status == storage.LegStatusFailed) {
			f.record.Legs[i].Status = storage.LegStatusPlacing
			return true, nil
		}
	}
	return false, nil
}

func (f *fakeArmerStore) UpdateLegStatus(_ context.Context, _ uuid.UUID, clientOrderID, status string, exchangeOrderID int64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.legUpdates = append(f.legUpdates, clientOrderID+":"+status)
	for i := range f.record.Legs {
		if f.record.Legs[i].ClientOrderID == clientOrderID {
			f.record.Legs[i].Status = status
			if exchangeOrderID != 0 {
				f.record.Legs[i].ExchangeOrderID = exchangeOrderID
			}
		}
	}
	return nil
}

func (f *fakeArmerStore) UpdateBracketStatus(_ context.Context, _ uuid.UUID, status string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.bracketUpdates = append(f.bracketUpdates, status)
	f.record.Status = status
	return nil
}

// armerExchange records POSTed and canceled orders on the futures paths.
type armerExchange struct {
	mu          sync.Mutex
	postedIDs   []string
	postedQtys  map[string]string
	canceledIDs []int64
	failPosts   bool // all POSTs fail with a non-retryable -1102
}

func (f *armerExchange) posted() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]string(nil), f.postedIDs...)
}

func (f *armerExchange) canceled() []int64 {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]int64(nil), f.canceledIDs...)
}

func (f *armerExchange) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/fapi/v1/order" {
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
			return
		}
		q := r.URL.Query()
		orDefault := func(v string) string {
			if v == "" {
				return "0"
			}
			return v
		}
		switch r.Method {
		case http.MethodPost:
			clientOrderID := q.Get("newClientOrderId")
			if f.failPosts {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-1102,"msg":"Mandatory parameter was not sent."}`))
				return
			}
			f.mu.Lock()
			f.postedIDs = append(f.postedIDs, clientOrderID)
			if f.postedQtys == nil {
				f.postedQtys = make(map[string]string)
			}
			f.postedQtys[clientOrderID] = orDefault(q.Get("quantity"))
			count := len(f.postedIDs)
			f.mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{
				"orderId": 5000 + count, "symbol": q.Get("symbol"), "status": "NEW",
				"clientOrderId": clientOrderID, "price": orDefault(q.Get("price")), "avgPrice": "0",
				"origQty": orDefault(q.Get("quantity")), "executedQty": "0", "cumQty": "0", "cumQuote": "0",
				"timeInForce": "GTC", "type": q.Get("type"), "reduceOnly": q.Get("reduceOnly") == "true",
				"closePosition": q.Get("closePosition") == "true", "side": q.Get("side"),
				"positionSide": "BOTH", "stopPrice": orDefault(q.Get("stopPrice")),
				"workingType": "CONTRACT_PRICE", "priceProtect": false,
				"origType": q.Get("type"), "updateTime": 1,
			})
		case http.MethodDelete:
			orderID, _ := json.Number(orDefault(q.Get("orderId"))).Int64()
			f.mu.Lock()
			f.canceledIDs = append(f.canceledIDs, orderID)
			f.mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{"orderId": orderID, "status": "CANCELED"})
		default:
			w.WriteHeader(http.StatusMethodNotAllowed)
		}
	}
}

func newArmerFixture(t *testing.T, store *fakeArmerStore) (*LegArmer, *armerExchange) {
	t.Helper()
	fake := &armerExchange{}
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	futuresRest := rest.NewClient(server.URL, signer)
	futuresClient, err := binance.NewFuturesClient(server.URL, signer, futuresRest, logger)
	require.NoError(t, err)

	return NewLegArmer(store, futuresClient, nil, logger), fake
}

func armerRecord() *storage.BracketRecord {
	return &storage.BracketRecord{
		BracketID:          uuid.New(),
		Venue:              "USD_M",
		Symbol:             "BTCUSDT",
		Side:               "BUY",
		Quantity:           decimal.RequireFromString("0.02"),
		StopLossPrice:      decimal.RequireFromString("49000"),
		EntryClientOrderID: "arm-main",
		Status:             storage.BracketStatusEntryPlaced,
		LegsOnFill:         true,
		Legs: []storage.BracketLegRecord{
			{Role: "ENTRY", ClientOrderID: "arm-main", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.02")},
			{Role: "TP", TPIndex: 1, ClientOrderID: "arm-tp1", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("51000"), Quantity: decimal.RequireFromString("0.02")},
			{Role: "SL", ClientOrderID: "arm-sl", Status: storage.LegStatusPlanned, StopPrice: decimal.RequireFromString("49000")},
		},
	}
}

func entryFillEvent(clientOrderID, status, cumQty string) *websocket.FuturesOrderTradeUpdateEvent {
	return &websocket.FuturesOrderTradeUpdateEvent{
		OrderTradeUpdate: websocket.FuturesOrderTradeData{
			Symbol:              "BTCUSDT",
			ClientOrderID:       clientOrderID,
			OrderStatus:         status,
			CumulativeFilledQty: decimal.RequireFromString(cumQty),
			OrderID:             42,
		},
	}
}

func TestLegArmer_EntryFillArmsProtectiveLegs(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Equal(t, []string{"arm-tp1", "arm-sl"}, fake.posted())
	assert.Equal(t, "0.02", fake.postedQtys["arm-tp1"], "TP sized by executed quantity")
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestLegArmer_DuplicateFillEventIsIdempotent(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))
	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Equal(t, []string{"arm-tp1", "arm-sl"}, fake.posted(),
		"duplicate events must never double-place protective legs")
}

func TestLegArmer_PreFillStatusesPlaceNothing(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "NEW", "0"))
	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "PARTIALLY_FILLED", "0.01"))

	assert.Empty(t, fake.posted())
}

func TestLegArmer_CanceledEntryWithPartialFillStillArms(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "CANCELED", "0.01"))

	assert.Equal(t, []string{"arm-tp1", "arm-sl"}, fake.posted())
	assert.Equal(t, "0.01", fake.postedQtys["arm-tp1"],
		"partial position must be protected with the executed quantity")
}

func TestLegArmer_CanceledEntryWithZeroFillClosesBracket(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "CANCELED", "0"))

	assert.Empty(t, fake.posted())
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.legUpdates, "arm-sl:CANCELED")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
}

func TestLegArmer_StopLossFillCancelsTakeProfits(t *testing.T) {
	record := armerRecord()
	record.Legs[1].Status = storage.LegStatusPlaced
	record.Legs[1].ExchangeOrderID = 7101
	record.Legs[2].Status = storage.LegStatusPlaced
	record.Legs[2].ExchangeOrderID = 7102
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-sl", "FILLED", "0.02"))

	assert.Equal(t, []int64{7101}, fake.canceled(), "SL fill must cancel resting TPs")
	assert.Contains(t, store.legUpdates, "arm-sl:FILLED")
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusClosed)
}

func TestLegArmer_FinalTakeProfitFillCancelsStopLoss(t *testing.T) {
	record := armerRecord()
	record.Legs[1].Status = storage.LegStatusPlaced
	record.Legs[1].ExchangeOrderID = 7101
	record.Legs[2].Status = storage.LegStatusPlaced
	record.Legs[2].ExchangeOrderID = 7102
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-tp1", "FILLED", "0.02"))

	assert.Equal(t, []int64{7102}, fake.canceled(), "final TP fill must cancel the SL")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusClosed)
}

func TestLegArmer_UnknownClientOrderIDIsIgnored(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("someone-else", "FILLED", "1"))

	assert.Empty(t, fake.posted())
	assert.Empty(t, store.bracketUpdates)
}

func TestLegArmer_SynchronousBracketsAreIgnored(t *testing.T) {
	record := armerRecord()
	record.LegsOnFill = false
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Empty(t, fake.posted())
}

func TestLegArmer_PlacementFailureMarksLegFailedAndBracketEntryFilled(t *testing.T) {
	store := &fakeArmerStore{record: armerRecord()}
	armer, fake := newArmerFixture(t, store)
	fake.failPosts = true

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED")
	assert.Contains(t, store.legUpdates, "arm-sl:FAILED")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates,
		"unarmed bracket must stay visible as reconciler work")
}

func TestLegArmer_FailedLegsAreReclaimedOnNextEvent(t *testing.T) {
	record := armerRecord()
	record.Legs[1].Status = storage.LegStatusFailed
	record.Legs[2].Status = storage.LegStatusFailed
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Equal(t, []string{"arm-tp1", "arm-sl"}, fake.posted(),
		"a transient failure must not permanently strand the position unprotected")
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
}

func TestLegArmer_ClosedBracketIgnoresLateDuplicateEntryEvent(t *testing.T) {
	record := armerRecord()
	record.Status = storage.BracketStatusClosed
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-main", "FILLED", "0.02"))

	assert.Empty(t, fake.posted())
	assert.Empty(t, store.bracketUpdates, "a settled bracket must never be resurrected")
}

func TestLegArmer_MultiTPOnlyFinalFillCancelsStopLoss(t *testing.T) {
	record := armerRecord()
	record.Legs = []storage.BracketLegRecord{
		{Role: "ENTRY", ClientOrderID: "arm-main", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.02")},
		{Role: "TP", TPIndex: 1, ClientOrderID: "arm-tp1", Status: storage.LegStatusPlaced, ExchangeOrderID: 7101, Price: decimal.RequireFromString("51000")},
		{Role: "TP", TPIndex: 2, ClientOrderID: "arm-tp2", Status: storage.LegStatusPlaced, ExchangeOrderID: 7102, Price: decimal.RequireFromString("52000")},
		{Role: "SL", ClientOrderID: "arm-sl", Status: storage.LegStatusPlaced, ExchangeOrderID: 7103, StopPrice: decimal.RequireFromString("49000")},
	}
	store := &fakeArmerStore{record: record}
	armer, fake := newArmerFixture(t, store)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-tp1", "FILLED", "0.01"))

	assert.Empty(t, fake.canceled(), "SL must survive while TP2 still rests")
	assert.Empty(t, store.bracketUpdates)

	armer.OnOrderTradeUpdate(context.Background(), entryFillEvent("arm-tp2", "FILLED", "0.01"))

	assert.Equal(t, []int64{7103}, fake.canceled())
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusClosed)
}
