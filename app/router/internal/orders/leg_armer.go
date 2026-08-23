package orders

import (
	"context"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"

	"router/internal/binance"
	"router/internal/storage"
	"router/internal/websocket"
)

// armerStore is the slice of the bracket store the leg armers need.
type armerStore interface {
	GetByEntryClientOrderID(ctx context.Context, venue, entryClientOrderID string) (*storage.BracketRecord, error)
	GetByLegClientOrderID(ctx context.Context, venue, clientOrderID string) (*storage.BracketRecord, error)
	TryMarkLegPlacing(ctx context.Context, bracketID uuid.UUID, clientOrderID string) (bool, error)
	UpdateLegStatus(ctx context.Context, bracketID uuid.UUID, clientOrderID, status string, exchangeOrderID int64) error
	UpdateLegStatusIf(ctx context.Context, bracketID uuid.UUID, clientOrderID, expected, status string, exchangeOrderID int64) (bool, error)
	UpdateBracketStatus(ctx context.Context, bracketID uuid.UUID, status string) error
	AdvanceBracketStatus(ctx context.Context, bracketID uuid.UUID, status string) (bool, error)
	InsertLeg(ctx context.Context, leg storage.BracketLegRecord) error
}

func persistLegExecution(
	ctx context.Context,
	store armerStore,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
	averageFillPrice decimal.Decimal,
) error {
	if averageFillPrice.IsPositive() {
		if updater, ok := store.(bracketLegExecutionUpdater); ok {
			return updater.UpdateLegExecution(
				ctx,
				bracketID,
				clientOrderID,
				status,
				exchangeOrderID,
				averageFillPrice,
			)
		}
	}
	return store.UpdateLegStatus(ctx, bracketID, clientOrderID, status, exchangeOrderID)
}

// LegArmer places protective TP/SL legs when a deferred bracket's entry
// fills, and enforces OCO semantics across the placed legs. It consumes the
// serialized futures user-data stream, so events arrive in exchange order.
type LegArmer struct {
	store   armerStore
	client  *binance.Client
	emitter EventEmitter
	logger  zerolog.Logger
}

func NewLegArmer(
	store armerStore,
	futuresClient *binance.Client,
	emitter EventEmitter,
	logger zerolog.Logger,
) *LegArmer {
	return &LegArmer{
		store:   store,
		client:  futuresClient,
		emitter: emitter,
		logger:  logger,
	}
}

// OnOrderTradeUpdate routes a futures user-data event to entry arming or
// exit-leg OCO handling. Errors are logged, never propagated: the stream
// consumer must not stall, and the startup reconciler is the backstop.
func (a *LegArmer) OnOrderTradeUpdate(ctx context.Context, event *websocket.FuturesOrderTradeUpdateEvent) {
	if event == nil {
		return
	}
	data := event.OrderTradeUpdate

	record, err := a.store.GetByEntryClientOrderID(ctx, "USD_M", data.ClientOrderID)
	if err != nil {
		a.logger.Error().Err(err).Str("client_order_id", data.ClientOrderID).
			Msg("leg armer: entry lookup failed")
		return
	}
	if record != nil {
		if record.LegsOnFill {
			a.handleEntryUpdate(ctx, record, data, event.TransactionTime)
		}
		return
	}

	record, err = a.store.GetByLegClientOrderID(ctx, "USD_M", data.ClientOrderID)
	if err != nil {
		a.logger.Error().Err(err).Str("client_order_id", data.ClientOrderID).
			Msg("leg armer: exit leg lookup failed")
		return
	}
	if record != nil && record.LegsOnFill {
		a.handleExitUpdate(ctx, record, data)
	}
}

func (a *LegArmer) handleEntryUpdate(
	ctx context.Context,
	record *storage.BracketRecord,
	data websocket.FuturesOrderTradeData,
	transactionTime int64,
) {
	if record.Status == storage.BracketStatusClosed || record.Status == storage.BracketStatusFailed {
		// A late duplicate must not resurrect a settled bracket
		return
	}
	switch data.OrderStatus {
	case "PARTIALLY_FILLED":
		observed := &binance.OrderResponse{
			Symbol:           data.Symbol,
			ClientOrderID:    data.ClientOrderID,
			OrderID:          data.OrderID,
			OrigQty:          data.Quantity,
			ExecutedQty:      data.CumulativeFilledQty,
			AverageFillPrice: data.AvgPrice,
			TransactTime:     transactionTime,
			Status:           data.OrderStatus,
			Type:             data.OrderType,
			Side:             data.Side,
		}
		finalizePartialEntry(ctx, a.store, a.client, record, observed, a.logger,
			func(ctx context.Context, record *storage.BracketRecord, entry *binance.OrderResponse) {
				a.armLegs(ctx, record, entry.ExecutedQty)
			})
	case "FILLED":
		if !a.persistEntryUpdate(ctx, record, data, transactionTime) {
			return
		}
		quantity := data.CumulativeFilledQty
		if quantity.IsZero() {
			quantity = record.Quantity
		}
		a.armLegs(ctx, record, quantity)
	case "CANCELED", "EXPIRED":
		if data.CumulativeFilledQty.IsPositive() {
			// A partial position exists and must still be protected.
			if !a.persistEntryUpdate(ctx, record, data, transactionTime) {
				return
			}
			a.armLegs(ctx, record, data.CumulativeFilledQty)
			return
		}
		a.markLegsForDeadEntry(ctx, record)
	}
}

// armLegs places all still-PLANNED protective legs for the executed
// quantity. The PLANNED→PLACING claim makes duplicate events harmless, and
// #193's submit resolution makes any raced POST adopt instead of double.
func (a *LegArmer) armLegs(ctx context.Context, record *storage.BracketRecord, executedQty decimal.Decimal) {
	if !executedQty.IsPositive() {
		return
	}

	exitSide := getOppositeSide(record.Side)
	tpLegs := legsByRole(record, "TP")
	tpQuantities := a.takeProfitQuantities(ctx, record.Symbol, executedQty, len(tpLegs))
	slLegs := legsByRole(record, "SL")
	slQuantities := splitTakeProfitQuantities(executedQty, len(slLegs), decimal.Zero)
	coverageReady := true
	for i, leg := range tpLegs {
		if err := updateLegQuantity(ctx, a.store, record.BracketID, leg.ClientOrderID, tpQuantities[i]); err != nil {
			a.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
				Msg("leg armer: failed to persist TP coverage")
			coverageReady = false
			continue
		}
		setRecordLegQuantity(record, leg.ClientOrderID, tpQuantities[i])
	}
	for i, leg := range slLegs {
		quantity := executedQty
		if i < len(slQuantities) {
			quantity = slQuantities[i]
		}
		if err := updateLegQuantity(ctx, a.store, record.BracketID, leg.ClientOrderID, quantity); err != nil {
			a.logger.Warn().Err(err).Str("client_order_id", leg.ClientOrderID).
				Msg("leg armer: failed to persist SL coverage")
			coverageReady = false
			continue
		}
		setRecordLegQuantity(record, leg.ClientOrderID, quantity)
	}
	if !coverageReady {
		return
	}
	allPlaced := true

	// Defensive re-rounding: records written before rounding preceded the
	// reservation hold raw prices, and Binance rejects off-tick legs with
	// -4014 at the exact moment the position opens.
	tpDir, slDir := binance.RoundUp, binance.RoundDown
	if record.Side == "SELL" {
		tpDir, slDir = binance.RoundDown, binance.RoundUp
	}

	for i, leg := range tpLegs {
		price := leg.Price
		if rounded, err := a.client.RoundPriceDirection(ctx, record.Symbol, price, tpDir); err == nil {
			price = rounded
		}
		if !a.armSingleLeg(ctx, record, leg, binance.FuturesOrderRequest{
			Symbol:           record.Symbol,
			Side:             exitSide,
			Type:             "LIMIT",
			Quantity:         tpQuantities[i],
			Price:            price,
			TimeInForce:      "GTC",
			NewClientOrderID: leg.ClientOrderID,
			ReduceOnly:       true,
		}) {
			allPlaced = false
		}
	}

	for _, leg := range slLegs {
		stopPrice := record.StopLossPrice
		if rounded, err := a.client.RoundPriceDirection(ctx, record.Symbol, stopPrice, slDir); err == nil {
			stopPrice = rounded
		}
		if !a.armSingleLeg(ctx, record, leg, binance.FuturesOrderRequest{
			Symbol:           record.Symbol,
			Side:             exitSide,
			Type:             "STOP_MARKET",
			Quantity:         decimal.Zero,
			StopPrice:        stopPrice,
			TimeInForce:      "GTC",
			NewClientOrderID: leg.ClientOrderID,
			// closePosition and reduceOnly are mutually exclusive on USD-M
			ClosePosition: true,
		}) {
			allPlaced = false
		}
	}

	status := storage.BracketStatusEntryFilled
	if allPlaced {
		status = storage.BracketStatusLegsPlaced
	}
	if _, err := a.store.AdvanceBracketStatus(ctx, record.BracketID, status); err != nil {
		a.logger.Warn().Err(err).Str("bracket_id", record.BracketID.String()).
			Msg("leg armer: failed to persist bracket status")
	}
}

// armSingleLeg claims and places one leg; returns true when the leg is
// known-placed (including already placed by a prior event).
func (a *LegArmer) armSingleLeg(
	ctx context.Context,
	record *storage.BracketRecord,
	leg storage.BracketLegRecord,
	order binance.FuturesOrderRequest,
) bool {
	if leg.Status != storage.LegStatusPlanned && leg.Status != storage.LegStatusFailed {
		return leg.Status == storage.LegStatusPlaced || leg.Status == storage.LegStatusFilled
	}

	claimed, err := a.store.TryMarkLegPlacing(ctx, record.BracketID, leg.ClientOrderID)
	if err != nil {
		a.logger.Error().Err(err).Str("client_order_id", leg.ClientOrderID).
			Msg("leg armer: failed to claim leg")
		return false
	}
	if !claimed {
		return false // durable placement is unknown; the reconciler will retry
	}

	resp, err := submitResolvingAmbiguity(
		ctx, a.logger, a.client, record.Symbol, leg.ClientOrderID, true,
		func(ctx context.Context) (*binance.OrderResponse, error) {
			return a.client.PlaceFuturesOrder(ctx, order)
		})
	if err != nil {
		a.logger.Error().Err(err).
			Str("client_order_id", leg.ClientOrderID).
			Str("symbol", record.Symbol).
			Msg("leg armer: protective leg placement FAILED — position may be unprotected")
		a.updateLegStatus(ctx, record.BracketID, leg.ClientOrderID, storage.LegStatusFailed, 0)
		return false
	}

	status, _ := legStatusFromOrder(resp.Status)
	a.updateLegStatus(ctx, record.BracketID, leg.ClientOrderID, status, resp.OrderID)
	return true
}

func (a *LegArmer) handleExitUpdate(
	ctx context.Context,
	record *storage.BracketRecord,
	data websocket.FuturesOrderTradeData,
) {
	leg := legByClientOrderID(record, data.ClientOrderID)
	if leg == nil {
		return
	}

	switch data.OrderStatus {
	case "FILLED":
		if err := persistLegExecution(ctx, a.store, record.BracketID, leg.ClientOrderID,
			storage.LegStatusFilled, data.OrderID, data.AvgPrice); err != nil {
			a.logger.Warn().Err(err).
				Str("client_order_id", leg.ClientOrderID).
				Msg("leg armer: failed to persist filled execution")
			return
		}
		leg.Status = storage.LegStatusFilled
		if leg.Role == "SL" {
			a.cancelLegs(ctx, record, "TP")
			a.closeBracket(ctx, record)
			return
		}
		if allLegsFilled(record, "TP") {
			a.cancelLegs(ctx, record, "SL")
			a.closeBracket(ctx, record)
		}
	case "CANCELED", "EXPIRED":
		status := storage.LegStatusCanceled
		if data.OrderStatus == "EXPIRED" {
			status = storage.LegStatusExpired
		}
		a.updateLegStatus(ctx, record.BracketID, leg.ClientOrderID, status, data.OrderID)
	}
}

func (a *LegArmer) persistEntryUpdate(
	ctx context.Context,
	record *storage.BracketRecord,
	data websocket.FuturesOrderTradeData,
	transactionTime int64,
) bool {
	status, _ := legStatusFromOrder(data.OrderStatus)
	quantity := data.CumulativeFilledQty
	if normalizeOrderStatus(data.OrderStatus) == "FILLED" && quantity.IsZero() {
		quantity = record.Quantity
	}
	if err := persistLegExecutionProgress(ctx, a.store, record.BracketID, record.EntryClientOrderID,
		status, data.OrderID, quantity, data.AvgPrice,
		exchangeObservationTime(transactionTime)); err != nil {
		a.logger.Warn().Err(err).
			Str("client_order_id", record.EntryClientOrderID).
			Msg("leg armer: failed to persist entry execution")
		return false
	}
	return true
}

func setRecordLegQuantity(record *storage.BracketRecord, clientOrderID string, quantity decimal.Decimal) {
	for i := range record.Legs {
		if record.Legs[i].ClientOrderID == clientOrderID {
			record.Legs[i].Quantity = quantity
		}
	}
}

// cancelLegs explicitly cancels placed legs of a role — belt-and-braces
// rather than trusting exchange-side auto-cancel behavior.
func (a *LegArmer) cancelLegs(ctx context.Context, record *storage.BracketRecord, role string) {
	for _, leg := range legsByRole(record, role) {
		if leg.Status != storage.LegStatusPlaced || leg.ExchangeOrderID == 0 {
			continue
		}
		if _, err := a.client.CancelOrder(ctx, record.Symbol, leg.ExchangeOrderID); err != nil {
			a.logger.Warn().Err(err).
				Str("client_order_id", leg.ClientOrderID).
				Msg("leg armer: sibling cancel failed; reconciler will retry")
			continue
		}
		a.updateLegStatus(ctx, record.BracketID, leg.ClientOrderID, storage.LegStatusCanceled, leg.ExchangeOrderID)
	}
}

func (a *LegArmer) closeBracket(ctx context.Context, record *storage.BracketRecord) {
	if err := a.store.UpdateBracketStatus(ctx, record.BracketID, storage.BracketStatusClosed); err != nil {
		a.logger.Warn().Err(err).Str("bracket_id", record.BracketID.String()).
			Msg("leg armer: failed to close bracket")
	}
}

// markLegsForDeadEntry releases the legs when the entry died unfilled.
func (a *LegArmer) markLegsForDeadEntry(ctx context.Context, record *storage.BracketRecord) {
	for _, leg := range record.Legs {
		if leg.Role == "ENTRY" || leg.Status == storage.LegStatusPlanned {
			a.updateLegStatus(ctx, record.BracketID, leg.ClientOrderID, storage.LegStatusCanceled, 0)
		}
	}
	a.closeBracket(ctx, record)
}

func (a *LegArmer) takeProfitQuantities(
	ctx context.Context,
	symbol string,
	executedQty decimal.Decimal,
	count int,
) []decimal.Decimal {
	// Unlike the synchronous path (which aborts on StepSize errors before
	// any order exists), a position is already open here: attempting
	// protection with an unstepped split beats aborting.
	step := decimal.Zero
	if s, err := a.client.StepSize(ctx, symbol); err == nil {
		step = s
	}
	return splitTakeProfitQuantities(executedQty, count, step)
}

func (a *LegArmer) updateLegStatus(
	ctx context.Context,
	bracketID uuid.UUID,
	clientOrderID, status string,
	exchangeOrderID int64,
) {
	if err := a.store.UpdateLegStatus(ctx, bracketID, clientOrderID, status, exchangeOrderID); err != nil {
		a.logger.Warn().Err(err).
			Str("client_order_id", clientOrderID).
			Str("status", status).
			Msg("leg armer: failed to persist leg status")
	}
}

func legsByRole(record *storage.BracketRecord, role string) []storage.BracketLegRecord {
	var legs []storage.BracketLegRecord
	for _, leg := range record.Legs {
		if leg.Role == role {
			legs = append(legs, leg)
		}
	}
	return legs
}

func legByClientOrderID(record *storage.BracketRecord, clientOrderID string) *storage.BracketLegRecord {
	for i := range record.Legs {
		if record.Legs[i].ClientOrderID == clientOrderID {
			return &record.Legs[i]
		}
	}
	return nil
}

func allLegsFilled(record *storage.BracketRecord, role string) bool {
	for _, leg := range record.Legs {
		if leg.Role == role && leg.Status != storage.LegStatusFilled {
			return false
		}
	}
	return true
}
