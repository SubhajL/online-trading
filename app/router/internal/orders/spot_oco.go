package orders

import (
	"context"
	"errors"
	"fmt"
	"hash/fnv"
	"sort"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"

	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

const maxClientOrderIDLength = 36

// Repoll knobs bridging the exchange's post-accept visibility lag when an
// OCO placement outcome must be resolved by query (test-overridable).
var (
	ocoRepollDelay    = 500 * time.Millisecond
	ocoRepollAttempts = 2
)

// sliceOutcome is what became of one OCO slice during an arm pass.
type sliceOutcome int

const (
	slicePlaced  sliceOutcome = iota // OCO live on the exchange (or adopted)
	sliceClosed                      // slice settled: closed at market or nothing left to protect
	sliceFailed                      // placement failed; FAILED legs are re-claimed next poll
	slicePending                     // outcome unknown; resolved against the exchange next poll
)

// spotOCOSlice pairs one take-profit slice with its share of the stop.
type spotOCOSlice struct {
	index  int
	tpLeg  storage.BracketLegRecord
	stopID string // reserved SL id for the first slice, derived beyond that
	req    rest.OCORequest
}

// SpotLegArmer places OCO exit pairs for deferred spot brackets once their
// entry fills. Spot has no production user-data stream, so the entry-fill
// watcher drives it by polling; the exchange sibling-cancels each pair, so
// no router-side exit-event handling is needed.
type SpotLegArmer struct {
	store   armerStore
	client  *binance.Client
	emitter EventEmitter
	logger  zerolog.Logger
}

func NewSpotLegArmer(
	store armerStore,
	spotClient *binance.Client,
	emitter EventEmitter,
	logger zerolog.Logger,
) *SpotLegArmer {
	return &SpotLegArmer{
		store:   store,
		client:  spotClient,
		emitter: emitter,
		logger:  logger,
	}
}

// Arm places OCO exits for the entry's executed quantity. Idempotent through
// the per-leg PLANNED|FAILED→PLACING claim, exchange-resolved recovery of
// PLACING legs, and duplicate-list adoption; the watcher's polling loop is
// the retry mechanism for anything left FAILED or unresolved.
func (a *SpotLegArmer) Arm(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
	if entry == nil || !entry.ExecutedQty.IsPositive() {
		return
	}
	if record.Status == storage.BracketStatusClosed || record.Status == storage.BracketStatusFailed {
		return
	}

	step := decimal.Zero
	if s, err := a.client.StepSize(ctx, record.Symbol); err == nil {
		step = s
	}
	qty := a.protectableQuantity(ctx, record.Symbol, entry, step)
	if !qty.IsPositive() {
		a.logger.Error().
			Str("bracket_id", record.BracketID.String()).
			Str("symbol", record.Symbol).
			Str("executed_qty", entry.ExecutedQty.String()).
			Msg("spot armer: fill nets to unsellable dust after fees; closing bracket")
		a.releaseUnarmedLegs(ctx, record)
		return
	}

	slices := a.buildSpotExitOCOs(ctx, record, qty)
	if len(slices) == 0 {
		a.logger.Error().
			Str("bracket_id", record.BracketID.String()).
			Str("symbol", record.Symbol).
			Msg("spot armer: no reserved TP/SL legs; cannot protect position")
		a.updateBracketStatus(ctx, record, storage.BracketStatusEntryFilled)
		return
	}

	var placed, failed, pending int
	for _, slice := range slices {
		if !slice.req.Quantity.IsPositive() {
			// Dust slice: the remainder rides in the last slice, so no
			// stop coverage is lost by cancelling this pair.
			a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, storage.LegStatusCanceled, 0, decimal.Zero, slice.index+1)
			a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusCanceled, 0, decimal.Zero, slice.index+1)
			continue
		}
		switch a.armSlice(ctx, record, slice) {
		case slicePlaced:
			placed++
		case sliceFailed:
			failed++
		case slicePending:
			pending++
		}
	}

	status := storage.BracketStatusEntryFilled // keeps the watcher retrying
	switch {
	case failed == 0 && pending == 0 && placed > 0:
		status = storage.BracketStatusLegsPlaced
	case failed == 0 && pending == 0:
		status = storage.BracketStatusClosed // every slice settled without a resting exit
	}
	a.updateBracketStatus(ctx, record, status)
}

// protectableQuantity nets base-asset entry commissions out of the executed
// quantity (spot BUY fees are deducted from the received asset, so the gross
// fill overstates what can be sold) and floors to the lot step so every
// derived slice stays step-aligned.
func (a *SpotLegArmer) protectableQuantity(
	ctx context.Context,
	symbol string,
	entry *binance.OrderResponse,
	step decimal.Decimal,
) decimal.Decimal {
	qty := entry.ExecutedQty
	if entry.OrderID > 0 {
		info, infoErr := a.client.GetSymbolInfo(ctx, symbol)
		if infoErr == nil && info != nil && info.BaseAsset != "" {
			if trades, err := a.client.GetMyTrades(ctx, symbol, entry.OrderID); err == nil {
				for _, trade := range trades {
					if trade.CommissionAsset == info.BaseAsset {
						qty = qty.Sub(trade.Commission)
					}
				}
			} else {
				a.logger.Warn().Err(err).Str("symbol", symbol).
					Msg("spot armer: trade lookup failed; using gross fill quantity")
			}
		}
	}
	if step.IsPositive() {
		qty = qty.Div(step).Floor().Mul(step)
	}
	return qty
}

// buildSpotExitOCOs pairs every take-profit slice with a stop slice of the
// same quantity at the shared stop price, so total stop coverage always
// equals the protected position.
func (a *SpotLegArmer) buildSpotExitOCOs(
	ctx context.Context,
	record *storage.BracketRecord,
	executedQty decimal.Decimal,
) []spotOCOSlice {
	tpLegs := legsByRole(record, "TP")
	slLegs := legsByRole(record, "SL")
	if len(tpLegs) == 0 || len(slLegs) == 0 {
		return nil
	}
	// Slice index ↔ leg pairing must be stable across restarts: derived
	// stop ids are keyed by position, and leg load order is not guaranteed.
	// Arm-time SL-role inserts carry tp_index >= 1, so the reservation's SL
	// always sorts first.
	sort.SliceStable(tpLegs, func(i, j int) bool { return tpLegs[i].TPIndex < tpLegs[j].TPIndex })
	sort.SliceStable(slLegs, func(i, j int) bool { return slLegs[i].TPIndex < slLegs[j].TPIndex })
	reservedStopID := slLegs[0].ClientOrderID

	exitSide := getOppositeSide(record.Side)
	step := decimal.Zero
	tickSize := decimal.Zero
	if s, err := a.client.StepSize(ctx, record.Symbol); err == nil {
		step = s
	}
	if info, err := a.client.GetSymbolInfo(ctx, record.Symbol); err == nil && info != nil {
		tickSize = info.TickSize
	}
	quantities := splitTakeProfitQuantities(executedQty, len(tpLegs), step)

	stopPrice := record.StopLossPrice
	tpDir, slDir := binance.RoundUp, binance.RoundDown
	if record.Side == "SELL" {
		tpDir, slDir = binance.RoundDown, binance.RoundUp
	}
	if rounded, err := a.client.RoundPriceDirection(ctx, record.Symbol, stopPrice, slDir); err == nil {
		stopPrice = rounded
	}
	stopLimitPrice := stopLossLimitPriceForSpotBracket(stopPrice, record.Side, tickSize)

	slices := make([]spotOCOSlice, 0, len(tpLegs))
	for i, tpLeg := range tpLegs {
		tpPrice := tpLeg.Price
		if rounded, err := a.client.RoundPriceDirection(ctx, record.Symbol, tpPrice, tpDir); err == nil {
			tpPrice = rounded
		}
		stopID := reservedStopID
		if i > 0 {
			// A single SL was reserved; extra slices need their own stop ids
			stopID = deriveSliceID(reservedStopID, i)
		}
		tpPriceLimit := decimal.Zero
		if record.Side == "SELL" {
			// BUY exits are TAKE_PROFIT_LIMITs: activation cancels the OCO
			// sibling, so the limit sits marketably above the trigger to
			// convert a touch into a fill instead of a stop-less rest.
			tpPriceLimit = stopLossLimitPriceForSpotBracket(tpPrice, "SELL", tickSize)
		}
		slices = append(slices, spotOCOSlice{
			index:  i,
			tpLeg:  tpLeg,
			stopID: stopID,
			req: rest.OCORequest{
				Symbol:             record.Symbol,
				Side:               exitSide,
				Quantity:           quantities[i],
				Price:              tpPrice,
				PriceLimit:         tpPriceLimit,
				StopPrice:          stopPrice,
				StopLimitPrice:     stopLimitPrice,
				ListClientOrderID:  deriveSliceID(record.EntryClientOrderID+"-oco", i),
				LimitClientOrderID: tpLeg.ClientOrderID,
				StopClientOrderID:  stopID,
			},
		})
	}
	return slices
}

// armSlice claims and places one OCO pair. The claim is on the TP leg id
// (unique per slice); statuses left by prior lives are resolved against the
// exchange, never guessed at.
func (a *SpotLegArmer) armSlice(ctx context.Context, record *storage.BracketRecord, slice spotOCOSlice) sliceOutcome {
	leg := slice.tpLeg
	switch leg.Status {
	case storage.LegStatusPlaced, storage.LegStatusFilled:
		return slicePlaced
	case storage.LegStatusCanceled, storage.LegStatusExpired:
		return sliceClosed
	case storage.LegStatusPlacing:
		// A previous life crashed mid-placement; only the exchange knows
		// whether the list landed.
		return a.resolveStalePlacing(ctx, record, slice)
	case storage.LegStatusPlanned, storage.LegStatusFailed:
	default:
		return sliceFailed
	}

	claimed, err := a.store.TryMarkLegPlacing(ctx, record.BracketID, leg.ClientOrderID)
	if err != nil {
		a.logger.Error().Err(err).Str("client_order_id", leg.ClientOrderID).
			Msg("spot armer: failed to claim leg")
		return sliceFailed
	}
	if !claimed {
		// The record is stale versus the store; re-read next poll
		return slicePending
	}

	resp, err := a.client.PlaceSpotOCO(ctx, slice.req)
	if err == nil {
		return a.persistSliceOutcome(ctx, record, slice, resp)
	}

	switch {
	case rest.IsDuplicateClientOrderID(err) || errors.Is(err, rest.ErrAmbiguousSubmit):
		return a.resolveAfterUnknownOutcome(ctx, record, slice, err)
	case rest.IsPriceRelationRejection(err):
		// Price gapped past the exit levels while the slice was unprotected;
		// the same OCO can never be accepted, so fail closed at market.
		a.logger.Error().Err(err).
			Str("client_order_id", leg.ClientOrderID).
			Str("symbol", record.Symbol).
			Msg("spot armer: OCO prices already breached; closing slice at market")
		return a.emergencyCloseSlice(ctx, record, slice)
	default:
		a.logger.Error().Err(err).
			Str("client_order_id", leg.ClientOrderID).
			Str("symbol", record.Symbol).
			Msg("spot armer: OCO placement FAILED — position may be unprotected")
		a.updateLegStatus(ctx, record, leg.ClientOrderID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		return sliceFailed
	}
}

// resolveAfterUnknownOutcome settles a POST whose result is unknown
// (transport ambiguity) or asserted-duplicate. #193 discipline: never blind
// re-POST — the previous attempt may be live, and a re-accepted list would
// double-sell the position.
func (a *SpotLegArmer) resolveAfterUnknownOutcome(
	ctx context.Context,
	record *storage.BracketRecord,
	slice spotOCOSlice,
	postErr error,
) sliceOutcome {
	duplicate := rest.IsDuplicateClientOrderID(postErr)
	adopted, err := a.getOCOWithRepoll(ctx, slice.req.ListClientOrderID)
	if err == nil {
		a.logger.Warn().Str("list_client_order_id", slice.req.ListClientOrderID).
			Msg("spot armer: adopted existing OCO list")
		return a.persistSliceOutcome(ctx, record, slice, adopted)
	}
	if rest.IsOrderNotFound(err) && !duplicate {
		// Confirmed absent: the ambiguous POST never landed; safe to retry
		a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		return sliceFailed
	}
	// Duplicate-but-invisible, or the query itself failed: unresolved. The
	// leg stays PLACING so the next poll re-checks the exchange instead of
	// re-POSTing.
	a.logger.Error().Err(postErr).
		Str("list_client_order_id", slice.req.ListClientOrderID).
		AnErr("query_error", err).
		Msg("spot armer: OCO outcome unresolved; re-checking next poll")
	return slicePending
}

// resolveStalePlacing recovers a leg a previous process life left PLACING:
// adopt the list if it landed, release the claim to FAILED if the exchange
// confirms it never did.
func (a *SpotLegArmer) resolveStalePlacing(
	ctx context.Context,
	record *storage.BracketRecord,
	slice spotOCOSlice,
) sliceOutcome {
	adopted, err := a.getOCOWithRepoll(ctx, slice.req.ListClientOrderID)
	if err == nil {
		a.logger.Warn().Str("list_client_order_id", slice.req.ListClientOrderID).
			Msg("spot armer: adopted OCO list left PLACING by a previous run")
		return a.persistSliceOutcome(ctx, record, slice, adopted)
	}
	if rest.IsOrderNotFound(err) {
		a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		return sliceFailed
	}
	a.logger.Warn().Err(err).Str("list_client_order_id", slice.req.ListClientOrderID).
		Msg("spot armer: PLACING leg unresolved; re-checking next poll")
	return slicePending
}

// getOCOWithRepoll queries an order list by its list client id, re-polling
// on -2013 to bridge the exchange's post-accept visibility lag (#193).
func (a *SpotLegArmer) getOCOWithRepoll(ctx context.Context, listClientOrderID string) (*rest.OCOResponse, error) {
	resp, err := a.client.GetOCOByListClientOrderID(ctx, listClientOrderID)
	for attempt := 0; attempt < ocoRepollAttempts && err != nil && rest.IsOrderNotFound(err); attempt++ {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(ocoRepollDelay):
		}
		resp, err = a.client.GetOCOByListClientOrderID(ctx, listClientOrderID)
	}
	return resp, err
}

// emergencyCloseSlice market-closes one slice's quantity when its OCO can
// never be accepted (price already through the exit levels). The derived
// close id keeps the close idempotent across retries and restarts.
func (a *SpotLegArmer) emergencyCloseSlice(
	ctx context.Context,
	record *storage.BracketRecord,
	slice spotOCOSlice,
) sliceOutcome {
	closeID := deriveSliceID(record.EntryClientOrderID+"-mc", slice.index)
	resp, err := submitResolvingAmbiguity(
		ctx, a.logger, a.client, record.Symbol, closeID, false,
		func(ctx context.Context) (*binance.OrderResponse, error) {
			return a.client.PlaceSpotOrder(ctx, binance.SpotOrderRequest{
				Symbol:           record.Symbol,
				Side:             slice.req.Side,
				Type:             "MARKET",
				Quantity:         slice.req.Quantity,
				NewClientOrderID: closeID,
			})
		})
	if err != nil {
		a.logger.Error().Err(err).
			Str("client_order_id", closeID).
			Str("symbol", record.Symbol).
			Msg("spot armer: emergency market close FAILED — position unprotected")
		a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusFailed, 0, slice.req.Quantity, slice.index+1)
		return sliceFailed
	}

	a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, storage.LegStatusCanceled, 0, decimal.Zero, slice.index+1)
	a.updateLegStatus(ctx, record, slice.stopID, storage.LegStatusCanceled, 0, decimal.Zero, slice.index+1)
	status, _ := legStatusFromOrder(resp.Status)
	a.updateLegStatus(ctx, record, closeID, status, resp.OrderID, slice.req.Quantity, slice.index+1)
	return sliceClosed
}

func (a *SpotLegArmer) persistSliceOutcome(
	ctx context.Context,
	record *storage.BracketRecord,
	slice spotOCOSlice,
	resp *rest.OCOResponse,
) sliceOutcome {
	exchangeIDs := make(map[string]int64, len(resp.Orders))
	for _, order := range resp.Orders {
		exchangeIDs[order.ClientOrderID] = order.OrderID
	}
	reportStatuses := make(map[string]string, len(resp.OrderReports))
	for _, report := range resp.OrderReports {
		reportStatuses[report.ClientOrderID] = report.Status
		if report.OrderID != 0 {
			exchangeIDs[report.ClientOrderID] = report.OrderID
		}
	}
	tpStatus, tpWorking := legStatusFromOrder(reportStatuses[slice.tpLeg.ClientOrderID])
	stopStatus, stopWorking := legStatusFromOrder(reportStatuses[slice.stopID])
	if _, ok := reportStatuses[slice.tpLeg.ClientOrderID]; !ok {
		tpStatus, tpWorking = storage.LegStatusPlaced, true
	}
	if _, ok := reportStatuses[slice.stopID]; !ok {
		stopStatus, stopWorking = storage.LegStatusPlaced, true
	}
	a.updateLegStatus(ctx, record, slice.tpLeg.ClientOrderID, tpStatus,
		exchangeIDs[slice.tpLeg.ClientOrderID], slice.req.Quantity, slice.index+1)
	a.updateLegStatus(ctx, record, slice.stopID, stopStatus,
		exchangeIDs[slice.stopID], slice.req.Quantity, slice.index+1)
	if tpWorking || stopWorking {
		return slicePlaced
	}
	return sliceClosed
}

// updateLegStatus persists a leg outcome; ids without a reserved row (stop
// slices and emergency closes derived at arm time) get one inserted. The
// insert's tpIndex must be >= 1 so the reservation's SL keeps sorting first
// and reservedStopID stays stable across arm passes.
func (a *SpotLegArmer) updateLegStatus(
	ctx context.Context,
	record *storage.BracketRecord,
	clientOrderID, status string,
	exchangeOrderID int64,
	quantity decimal.Decimal,
	tpIndex int,
) {
	if legByClientOrderID(record, clientOrderID) == nil {
		if err := a.store.InsertLeg(ctx, storage.BracketLegRecord{
			BracketID:       record.BracketID,
			Role:            "SL",
			TPIndex:         tpIndex,
			ClientOrderID:   clientOrderID,
			StopPrice:       record.StopLossPrice,
			Quantity:        quantity,
			Status:          status,
			ExchangeOrderID: exchangeOrderID,
		}); err != nil {
			a.logger.Warn().Err(err).Str("client_order_id", clientOrderID).
				Msg("spot armer: failed to insert derived leg")
		}
		return
	}
	if err := a.store.UpdateLegStatus(ctx, record.BracketID, clientOrderID, status, exchangeOrderID); err != nil {
		a.logger.Warn().Err(err).
			Str("client_order_id", clientOrderID).
			Str("status", status).
			Msg("spot armer: failed to persist leg status")
	}
}

func (a *SpotLegArmer) updateBracketStatus(ctx context.Context, record *storage.BracketRecord, status string) {
	if err := a.store.UpdateBracketStatus(ctx, record.BracketID, status); err != nil {
		a.logger.Warn().Err(err).Str("bracket_id", record.BracketID.String()).
			Msg("spot armer: failed to persist bracket status")
	}
}

// releaseUnarmedLegs cancels every leg that never reached the exchange and
// closes the bracket — used when there is nothing protectable to arm.
func (a *SpotLegArmer) releaseUnarmedLegs(ctx context.Context, record *storage.BracketRecord) {
	for _, leg := range record.Legs {
		if leg.Status == storage.LegStatusPlanned || leg.Status == storage.LegStatusFailed {
			a.updateLegStatus(ctx, record, leg.ClientOrderID, storage.LegStatusCanceled, leg.ExchangeOrderID, decimal.Zero, leg.TPIndex)
		}
	}
	a.updateBracketStatus(ctx, record, storage.BracketStatusClosed)
}

// deriveSliceID appends a slice suffix while respecting Binance's 36-char
// client order id limit. When truncation is needed, part of the tail is
// replaced with a hash of the full base so ids that differ only in their
// final characters cannot collide.
func deriveSliceID(base string, index int) string {
	suffix := fmt.Sprintf("-%d", index)
	if len(base)+len(suffix) <= maxClientOrderIDLength {
		return base + suffix
	}
	h := fnv.New32a()
	_, _ = h.Write([]byte(base))
	tag := fmt.Sprintf("-%08x", h.Sum32())
	keep := maxClientOrderIDLength - len(suffix) - len(tag)
	return base[:keep] + tag + suffix
}
