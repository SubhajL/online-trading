package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/auth"
	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

// spotOCOExchange serves the spot OCO endpoints, recording placements and
// enforcing the real /api/v3/orderList/oco contract (above/below parameters;
// the legacy order/oco parameter names are rejected).
type spotOCOExchange struct {
	mu          sync.Mutex
	ocoRequests []url.Values
	closeReqs   []url.Values
	getStatuses []string // per GET /api/v3/order: order status (default FILLED)
	getCount    int
	failOCO     bool   // OCO POSTs fail with -1102
	dupOCO      bool   // OCO POSTs fail with -2010 duplicate
	rejectMsg   string // OCO POSTs fail with -2010 and this message
	failClose   bool   // market close POSTs fail with -2010 insufficient balance
	hijackPosts int    // abort this many OCO POSTs mid-connection (ambiguous outcome)
	serveInfo   bool   // serve /api/v3/exchangeInfo (tick 0.01, step 0.00001)
	trades      string // JSON array served on GET /api/v3/myTrades
	knownLists  map[string]url.Values
	getOrderQty string
	nextOrderID int64
}

func (f *spotOCOExchange) requests() []url.Values {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]url.Values(nil), f.ocoRequests...)
}

func (f *spotOCOExchange) closes() []url.Values {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]url.Values(nil), f.closeReqs...)
}

func (f *spotOCOExchange) rememberList(q url.Values) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.knownLists == nil {
		f.knownLists = map[string]url.Values{}
	}
	f.knownLists[q.Get("listClientOrderId")] = q
}

// validateOCOContract enforces the orderList/oco parameter shape so tests
// fail loudly if the client regresses to the legacy order/oco names.
func validateOCOContract(q url.Values) (int, string) {
	for _, legacy := range []string{
		"price", "stopPrice", "stopLimitPrice", "stopLimitTimeInForce",
		"limitClientOrderId", "stopClientOrderId",
	} {
		if q.Get(legacy) != "" {
			return -1103, "An unknown parameter was sent: " + legacy
		}
	}
	for _, required := range []string{"symbol", "side", "quantity", "aboveType", "belowType"} {
		if q.Get(required) == "" {
			return -1102, "Mandatory parameter '" + required + "' was not sent."
		}
	}
	for _, half := range []string{"above", "below"} {
		switch q.Get(half + "Type") {
		case "LIMIT_MAKER":
			if q.Get(half+"Price") == "" {
				return -1102, "Mandatory parameter '" + half + "Price' was not sent."
			}
		case "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT":
			if q.Get(half+"Price") == "" || q.Get(half+"StopPrice") == "" || q.Get(half+"TimeInForce") == "" {
				return -1102, "Mandatory parameters for '" + half + "Type' were not sent."
			}
		default:
			return -1102, "Unsupported " + half + "Type: " + q.Get(half+"Type")
		}
	}
	return 0, ""
}

func (f *spotOCOExchange) ocoResponse(q url.Values, withReports bool) map[string]any {
	f.mu.Lock()
	f.nextOrderID += 2
	aboveID, belowID := f.nextOrderID-1, f.nextOrderID
	f.mu.Unlock()
	resp := map[string]any{
		"orderListId":       700,
		"listClientOrderId": q.Get("listClientOrderId"),
		"listOrderStatus":   "EXECUTING",
		"orders": []map[string]any{
			{"symbol": q.Get("symbol"), "orderId": aboveID, "clientOrderId": q.Get("aboveClientOrderId")},
			{"symbol": q.Get("symbol"), "orderId": belowID, "clientOrderId": q.Get("belowClientOrderId")},
		},
	}
	if withReports {
		resp["orderReports"] = []map[string]any{
			{"symbol": q.Get("symbol"), "orderId": aboveID, "clientOrderId": q.Get("aboveClientOrderId"),
				"type": q.Get("aboveType"), "status": "NEW", "price": q.Get("abovePrice"),
				"stopPrice": zeroIfEmpty(q.Get("aboveStopPrice")), "origQty": q.Get("quantity")},
			{"symbol": q.Get("symbol"), "orderId": belowID, "clientOrderId": q.Get("belowClientOrderId"),
				"type": q.Get("belowType"), "status": "NEW", "price": q.Get("belowPrice"),
				"stopPrice": zeroIfEmpty(q.Get("belowStopPrice")), "origQty": q.Get("quantity")},
		}
	}
	return resp
}

func zeroIfEmpty(v string) string {
	if v == "" {
		return "0"
	}
	return v
}

func (f *spotOCOExchange) handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/orderList/oco":
			if code, msg := validateOCOContract(q); code != 0 {
				w.WriteHeader(http.StatusBadRequest)
				_ = json.NewEncoder(w).Encode(map[string]any{"code": code, "msg": msg})
				return
			}
			f.mu.Lock()
			hijack := f.hijackPosts > 0
			if hijack {
				f.hijackPosts--
			}
			f.mu.Unlock()
			if hijack {
				if hj, ok := w.(http.Hijacker); ok {
					if conn, _, err := hj.Hijack(); err == nil {
						_ = conn.Close()
					}
				}
				return
			}
			if f.failOCO {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-1102,"msg":"Mandatory parameter was not sent."}`))
				return
			}
			if f.dupOCO {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"Duplicate order sent."}`))
				return
			}
			if f.rejectMsg != "" {
				w.WriteHeader(http.StatusBadRequest)
				_ = json.NewEncoder(w).Encode(map[string]any{"code": -2010, "msg": f.rejectMsg})
				return
			}
			f.mu.Lock()
			f.ocoRequests = append(f.ocoRequests, q)
			f.mu.Unlock()
			f.rememberList(q)
			_ = json.NewEncoder(w).Encode(f.ocoResponse(q, true))
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/orderList":
			f.mu.Lock()
			known, ok := f.knownLists[q.Get("origClientOrderId")]
			f.mu.Unlock()
			if !ok {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2013,"msg":"Order list does not exist."}`))
				return
			}
			// The production query endpoint returns no orderReports
			_ = json.NewEncoder(w).Encode(f.ocoResponse(known, false))
		case r.Method == http.MethodPost && r.URL.Path == "/api/v3/order":
			if f.failClose {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2010,"msg":"Account has insufficient balance for requested action."}`))
				return
			}
			f.mu.Lock()
			f.closeReqs = append(f.closeReqs, q)
			count := len(f.closeReqs)
			f.mu.Unlock()
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": q.Get("symbol"), "orderId": 9100 + count,
				"clientOrderId": q.Get("newClientOrderId"), "status": "FILLED",
				"executedQty": q.Get("quantity"), "origQty": q.Get("quantity"),
				"cummulativeQuoteQty": "975", "price": "0",
				"type": "MARKET", "side": q.Get("side"), "timeInForce": "GTC",
			})
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/myTrades":
			if f.trades == "" {
				w.WriteHeader(http.StatusNotFound)
				_, _ = w.Write([]byte(`{"error":"not found"}`))
				return
			}
			_, _ = w.Write([]byte(f.trades))
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/exchangeInfo":
			if !f.serveInfo {
				w.WriteHeader(http.StatusNotFound)
				_, _ = w.Write([]byte(`{"error":"not found"}`))
				return
			}
			writeSpotExchangeInfo(w)
		case r.Method == http.MethodGet && r.URL.Path == "/api/v3/order":
			f.mu.Lock()
			status := "FILLED"
			if f.getCount < len(f.getStatuses) {
				status = f.getStatuses[f.getCount]
			}
			f.getCount++
			qty := f.getOrderQty
			f.mu.Unlock()
			if status == "NOT_FOUND" {
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":-2013,"msg":"Order does not exist."}`))
				return
			}
			if qty == "" {
				qty = "0.02"
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"symbol": "BTCUSDT", "orderId": 321, "clientOrderId": q.Get("origClientOrderId"),
				"price": "50000", "origQty": "0.02", "executedQty": qty,
				"cummulativeQuoteQty": "1000", "status": status,
				"timeInForce": "GTC", "type": "LIMIT", "side": "BUY",
			})
		default:
			w.WriteHeader(http.StatusNotFound)
			_, _ = w.Write([]byte(`{"error":"not found"}`))
		}
	}
}

func newSpotArmerFixture(t *testing.T, fake *spotOCOExchange, store *fakeArmerStore) (*SpotLegArmer, *binance.Client) {
	t.Helper()
	server := httptest.NewServer(fake.handler())
	t.Cleanup(server.Close)

	signer := auth.NewSignerWithRecvWindow("key", "secret", 5000)
	logger := zerolog.Nop()
	spotRest := rest.NewClient(server.URL, signer)
	spotClient, err := binance.NewSpotClient(server.URL, signer, spotRest, logger)
	require.NoError(t, err)
	spotClient.SetExchangeInfoCache(
		binance.NewExchangeInfoCache(spotRest, nil, time.Hour, logger),
	)

	return NewSpotLegArmer(store, spotClient, nil, logger), spotClient
}

func spotArmerRecord() *storage.BracketRecord {
	rec := armerRecord()
	rec.Venue = "SPOT"
	return rec
}

// spotSellRecord models a SELL entry whose exit OCO is on the BUY side.
func spotSellRecord() *storage.BracketRecord {
	rec := spotArmerRecord()
	rec.Side = "SELL"
	rec.StopLossPrice = decimal.RequireFromString("51000")
	rec.Legs[1].Price = decimal.RequireFromString("49000")
	rec.Legs[2].StopPrice = decimal.RequireFromString("51000")
	return rec
}

func spotEntry(qty string) *binance.OrderResponse {
	return &binance.OrderResponse{
		OrderID:     321,
		Status:      "FILLED",
		ExecutedQty: decimal.RequireFromString(qty),
	}
}

// fastRepoll shrinks the resolution repoll so unresolved-outcome tests do
// not sleep.
func fastRepoll(t *testing.T) {
	t.Helper()
	prevDelay, prevAttempts := ocoRepollDelay, ocoRepollAttempts
	ocoRepollDelay, ocoRepollAttempts = time.Millisecond, 1
	t.Cleanup(func() { ocoRepollDelay, ocoRepollAttempts = prevDelay, prevAttempts })
}

// presetSellList registers an OCO list as already live on the exchange, as
// if a previous process life placed it.
func presetSellList(fake *spotOCOExchange, list, tpID, slID string) {
	fake.rememberList(url.Values{
		"symbol": {"BTCUSDT"}, "side": {"SELL"}, "quantity": {"0.02"},
		"listClientOrderId":  {list},
		"aboveType":          {"LIMIT_MAKER"},
		"aboveClientOrderId": {tpID},
		"abovePrice":         {"51000"},
		"belowType":          {"STOP_LOSS_LIMIT"},
		"belowClientOrderId": {slID},
		"belowPrice":         {"48755"},
		"belowStopPrice":     {"49000"},
		"belowTimeInForce":   {"GTC"},
	})
}

func TestSpotLegArmer_EntryFillPlacesOCOPairWithAboveBelowContract(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	requests := fake.requests()
	require.Len(t, requests, 1)
	q := requests[0]
	assert.Equal(t, map[string]string{
		"symbol":             "BTCUSDT",
		"side":               "SELL",
		"quantity":           "0.02",
		"listClientOrderId":  "arm-main-oco-0",
		"aboveType":          "LIMIT_MAKER",
		"aboveClientOrderId": "arm-tp1",
		"abovePrice":         "51000",
		"belowType":          "STOP_LOSS_LIMIT",
		"belowClientOrderId": "arm-sl",
		"belowPrice":         "48755",
		"belowStopPrice":     "49000",
		"belowTimeInForce":   "GTC",
	}, map[string]string{
		"symbol":             q.Get("symbol"),
		"side":               q.Get("side"),
		"quantity":           q.Get("quantity"),
		"listClientOrderId":  q.Get("listClientOrderId"),
		"aboveType":          q.Get("aboveType"),
		"aboveClientOrderId": q.Get("aboveClientOrderId"),
		"abovePrice":         q.Get("abovePrice"),
		"belowType":          q.Get("belowType"),
		"belowClientOrderId": q.Get("belowClientOrderId"),
		"belowPrice":         q.Get("belowPrice"),
		"belowStopPrice":     q.Get("belowStopPrice"),
		"belowTimeInForce":   q.Get("belowTimeInForce"),
	})
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_BuyExitUsesTakeProfitLimitBelow(t *testing.T) {
	store := &fakeArmerStore{record: spotSellRecord()}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	requests := fake.requests()
	require.Len(t, requests, 1)
	q := requests[0]
	assert.Equal(t, map[string]string{
		"side":               "BUY",
		"aboveType":          "STOP_LOSS_LIMIT",
		"aboveClientOrderId": "arm-sl",
		"abovePrice":         "51255",
		"aboveStopPrice":     "51000",
		"aboveTimeInForce":   "GTC",
		"belowType":          "TAKE_PROFIT_LIMIT",
		"belowClientOrderId": "arm-tp1",
		"belowPrice":         "49245", // marketably above the trigger: activation cancels the stop sibling
		"belowStopPrice":     "49000",
		"belowTimeInForce":   "GTC",
	}, map[string]string{
		"side":               q.Get("side"),
		"aboveType":          q.Get("aboveType"),
		"aboveClientOrderId": q.Get("aboveClientOrderId"),
		"abovePrice":         q.Get("abovePrice"),
		"aboveStopPrice":     q.Get("aboveStopPrice"),
		"aboveTimeInForce":   q.Get("aboveTimeInForce"),
		"belowType":          q.Get("belowType"),
		"belowClientOrderId": q.Get("belowClientOrderId"),
		"belowPrice":         q.Get("belowPrice"),
		"belowStopPrice":     q.Get("belowStopPrice"),
		"belowTimeInForce":   q.Get("belowTimeInForce"),
	})
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_DuplicateArmIsIdempotent(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))
	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Len(t, fake.requests(), 1, "duplicate arms must never double-place OCO pairs")
}

func TestSpotLegArmer_FailureLeavesLegsReclaimableForNextPoll(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{failOCO: true}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates)

	// The watcher polls again; the FAILED leg must be re-claimable
	fake.failOCO = false
	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Len(t, fake.requests(), 1)
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

func TestSpotLegArmer_DuplicateListAdoptsExchangeState(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{dupOCO: true}
	presetSellList(fake, "arm-main-oco-0", "arm-tp1", "arm-sl")
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_DuplicateButInvisibleStaysPendingNotRePosted(t *testing.T) {
	fastRepoll(t)
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{dupOCO: true} // duplicate asserted, list never visible
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Empty(t, fake.requests(), "an unresolved duplicate must never re-POST")
	assert.NotContains(t, store.legUpdates, "arm-tp1:FAILED",
		"unresolved outcomes stay PLACING for exchange-side resolution, not FAILED for blind retry")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates)
}

func TestSpotLegArmer_AmbiguousPostAdoptsLandedList(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{hijackPosts: 1}
	presetSellList(fake, "arm-main-oco-0", "arm-tp1", "arm-sl")
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Empty(t, fake.requests(), "the landed list must be adopted, never re-POSTed")
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_AmbiguousPostConfirmedAbsentFailsForRetry(t *testing.T) {
	fastRepoll(t)
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{hijackPosts: 1}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED")
	assert.Contains(t, store.legUpdates, "arm-sl:FAILED")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Len(t, fake.requests(), 1, "a confirmed-absent submit is safe to retry once")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

func TestSpotLegArmer_StalePlacingLegAdoptedFromExchange(t *testing.T) {
	record := spotArmerRecord()
	record.Legs[1].Status = storage.LegStatusPlacing // crashed mid-placement
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{}
	presetSellList(fake, "arm-main-oco-0", "arm-tp1", "arm-sl")
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Empty(t, fake.requests(), "an already-landed list must be adopted, not re-POSTed")
	assert.Contains(t, store.legUpdates, "arm-tp1:PLACED")
	assert.Contains(t, store.legUpdates, "arm-sl:PLACED")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_StalePlacingLegConfirmedAbsentBecomesFailed(t *testing.T) {
	fastRepoll(t)
	record := spotArmerRecord()
	record.Legs[1].Status = storage.LegStatusPlacing
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Empty(t, fake.requests())
	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED",
		"a PLACING leg the exchange has never seen must become re-claimable")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))
	assert.Len(t, fake.requests(), 1)
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

func TestSpotLegArmer_PriceGapFailsClosedAtMarket(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{rejectMsg: "The relationship of the prices for the orders is not correct."}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	closes := fake.closes()
	require.Len(t, closes, 1, "a gapped-through exit must fail closed at market")
	assert.Equal(t, [4]string{"MARKET", "SELL", "0.02", "arm-main-mc-0"}, [4]string{
		closes[0].Get("type"), closes[0].Get("side"),
		closes[0].Get("quantity"), closes[0].Get("newClientOrderId"),
	})
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.legUpdates, "arm-sl:CANCELED")
	assert.Contains(t, store.legUpdates, "arm-main-mc-0:PLACED",
		"the close must be recorded for provenance")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
}

func TestSpotLegArmer_EmergencyCloseFailureLeavesLegsRetryable(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{
		rejectMsg: "The relationship of the prices for the orders is not correct.",
		failClose: true,
	}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Contains(t, store.legUpdates, "arm-tp1:FAILED")
	assert.Contains(t, store.legUpdates, "arm-sl:FAILED")
	assert.Equal(t, []string{storage.BracketStatusEntryFilled}, store.bracketUpdates,
		"a failed emergency close must keep the bracket in the retry loop")
}

func TestSpotLegArmer_NetsBaseAssetCommissionFromQuantity(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{
		serveInfo: true,
		trades: `[
			{"symbol":"BTCUSDT","id":1,"orderId":321,"price":"50000","qty":"0.01","commission":"0.00001","commissionAsset":"BTC","time":1,"isBuyer":true},
			{"symbol":"BTCUSDT","id":2,"orderId":321,"price":"50000","qty":"0.01","commission":"0.00001","commissionAsset":"BTC","time":2,"isBuyer":true},
			{"symbol":"BTCUSDT","id":3,"orderId":321,"price":"50000","qty":"0","commission":"0.5","commissionAsset":"USDT","time":3,"isBuyer":true}
		]`,
	}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	requests := fake.requests()
	require.Len(t, requests, 1)
	assert.Equal(t, "0.01998", requests[0].Get("quantity"),
		"base-asset fees must be netted or the exit sell exceeds the free balance")
}

func TestSpotLegArmer_DustFillClosesBracketInsteadOfLoopingForever(t *testing.T) {
	store := &fakeArmerStore{record: spotArmerRecord()}
	fake := &spotOCOExchange{serveInfo: true}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.000005"))

	assert.Empty(t, fake.requests(), "an unsellable dust fill can never arm")
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.legUpdates, "arm-sl:CANCELED")
	assert.Equal(t, []string{storage.BracketStatusClosed}, store.bracketUpdates)
}

func TestSpotLegArmer_ZeroQuantitySliceSkippedWithoutBlockingArm(t *testing.T) {
	record := spotArmerRecord()
	record.Legs = []storage.BracketLegRecord{
		{Role: "ENTRY", ClientOrderID: "arm-main", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.02")},
		{Role: "TP", TPIndex: 1, ClientOrderID: "arm-tp1", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("51000")},
		{Role: "TP", TPIndex: 2, ClientOrderID: "arm-tp2", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("52000")},
		{Role: "SL", ClientOrderID: "arm-sl", Status: storage.LegStatusPlanned, StopPrice: decimal.RequireFromString("49000")},
	}
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{serveInfo: true}
	armer, _ := newSpotArmerFixture(t, fake, store)

	// One step of quantity across two TPs: the first slice floors to zero
	armer.Arm(context.Background(), store.record, spotEntry("0.00001"))

	requests := fake.requests()
	require.Len(t, requests, 1, "the dust slice must be skipped, not retried forever")
	assert.Equal(t, "0.00001", requests[0].Get("quantity"))
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.legUpdates, "arm-sl:CANCELED",
		"the dust slice's stop share is cancelled with it")
	assert.Equal(t, []string{storage.BracketStatusLegsPlaced}, store.bracketUpdates)
}

func TestSpotLegArmer_ReservedStopStaysStableDespiteInsertedSLLegs(t *testing.T) {
	record := spotArmerRecord()
	record.Legs = []storage.BracketLegRecord{
		{Role: "ENTRY", ClientOrderID: "arm-main", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.02")},
		// An emergency-close leg from a previous pass, loaded BEFORE the
		// reserved SL to simulate adverse tie-ordering
		{Role: "SL", TPIndex: 1, ClientOrderID: "arm-main-mc-0", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.01")},
		{Role: "TP", TPIndex: 1, ClientOrderID: "arm-tp1", Status: storage.LegStatusCanceled, Price: decimal.RequireFromString("51000")},
		{Role: "TP", TPIndex: 2, ClientOrderID: "arm-tp2", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("52000")},
		{Role: "SL", TPIndex: 0, ClientOrderID: "arm-sl", Status: storage.LegStatusPlanned, StopPrice: decimal.RequireFromString("49000")},
	}
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	requests := fake.requests()
	require.Len(t, requests, 1, "only the still-planned slice places")
	assert.Equal(t, "arm-sl-1", requests[0].Get("belowClientOrderId"),
		"derived stop ids must stay keyed to the reservation's SL, not arm-time inserts")
}

func TestSpotLegArmer_MultiTPSlicesShareStopWithDerivedIDs(t *testing.T) {
	record := spotArmerRecord()
	record.Legs = []storage.BracketLegRecord{
		{Role: "ENTRY", ClientOrderID: "arm-main", Status: storage.LegStatusPlaced, Quantity: decimal.RequireFromString("0.02")},
		{Role: "TP", TPIndex: 1, ClientOrderID: "arm-tp1", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("51000")},
		{Role: "TP", TPIndex: 2, ClientOrderID: "arm-tp2", Status: storage.LegStatusPlanned, Price: decimal.RequireFromString("52000")},
		{Role: "SL", ClientOrderID: "arm-sl", Status: storage.LegStatusPlanned, StopPrice: decimal.RequireFromString("49000")},
	}
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	requests := fake.requests()
	require.Len(t, requests, 2)
	assert.Equal(t, "arm-sl", requests[0].Get("belowClientOrderId"))
	assert.Equal(t, "arm-sl-1", requests[1].Get("belowClientOrderId"),
		"extra slices derive their own stop ids")
	assert.Contains(t, store.legUpdates, "arm-sl-1:PLACED",
		"derived stop legs must be recorded")
	total := decimal.RequireFromString(requests[0].Get("quantity")).
		Add(decimal.RequireFromString(requests[1].Get("quantity")))
	assert.True(t, decimal.RequireFromString("0.02").Equal(total),
		"stop coverage must equal the protected position")
}

func TestSpotLegArmer_SettledBracketIsIgnored(t *testing.T) {
	record := spotArmerRecord()
	record.Status = storage.BracketStatusClosed
	store := &fakeArmerStore{record: record}
	fake := &spotOCOExchange{}
	armer, _ := newSpotArmerFixture(t, fake, store)

	armer.Arm(context.Background(), store.record, spotEntry("0.02"))

	assert.Empty(t, fake.requests())
	assert.Empty(t, store.bracketUpdates)
}

func TestDeriveSliceID_TruncationCannotCollide(t *testing.T) {
	baseA := strings.Repeat("a", 35) + "x"
	baseB := strings.Repeat("a", 35) + "y"

	idA := deriveSliceID(baseA, 0)
	idB := deriveSliceID(baseB, 0)

	assert.NotEqual(t, idA, idB,
		"bases differing only in truncated tail characters must not collide")
	assert.LessOrEqual(t, len(idA), maxClientOrderIDLength)
	assert.Equal(t, idA, deriveSliceID(baseA, 0), "derived ids must be stable across calls")
	assert.Equal(t, "short-0", deriveSliceID("short", 0))
}
