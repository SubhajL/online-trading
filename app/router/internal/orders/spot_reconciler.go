package orders

import (
	"context"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"
	"router/internal/binance"
)

type spotOrderTracker interface {
	Track(req SpotReconcileRequest)
}

type SpotReconcileRequest struct {
	Symbol        string
	OrderID       int64
	ClientOrderID string
	Side          string
	OrderType     string
	Quantity      decimal.Decimal
	Price         decimal.Decimal
	InitialStatus string
	ExecutedQty   decimal.Decimal
}

type SpotReconcilerOption func(*SpotReconciler)

func WithSpotReconcilerPollInterval(interval time.Duration) SpotReconcilerOption {
	return func(r *SpotReconciler) {
		if interval > 0 {
			r.pollInterval = interval
		}
	}
}

func WithSpotReconcilerMaxAttempts(maxAttempts int) SpotReconcilerOption {
	return func(r *SpotReconciler) {
		if maxAttempts > 0 {
			r.maxAttempts = maxAttempts
		}
	}
}

func WithSpotReconcilerLedger(ledger spotExecutionLedger) SpotReconcilerOption {
	return func(r *SpotReconciler) {
		r.ledger = ledger
	}
}

type SpotReconciler struct {
	client       *binance.Client
	eventEmitter EventEmitter
	logger       zerolog.Logger
	ledger       spotExecutionLedger
	pollInterval time.Duration
	maxAttempts  int
	mu           sync.Mutex
	ctx          context.Context
	cancel       context.CancelFunc
	wg           sync.WaitGroup
	started      bool
}

func NewSpotReconciler(
	client *binance.Client,
	eventEmitter EventEmitter,
	logger zerolog.Logger,
	opts ...SpotReconcilerOption,
) *SpotReconciler {
	reconciler := &SpotReconciler{
		client:       client,
		eventEmitter: eventEmitter,
		logger:       logger,
		pollInterval: 3 * time.Second,
		maxAttempts:  10,
	}

	for _, opt := range opts {
		opt(reconciler)
	}

	return reconciler
}

func (r *SpotReconciler) Start(parent context.Context) {
	if r == nil {
		return
	}
	if parent == nil {
		parent = context.Background()
	}

	r.mu.Lock()
	defer r.mu.Unlock()
	if r.started {
		return
	}

	r.ctx, r.cancel = context.WithCancel(parent)
	r.started = true
}

func (r *SpotReconciler) Stop() {
	if r == nil {
		return
	}

	r.mu.Lock()
	if !r.started {
		r.mu.Unlock()
		return
	}
	cancel := r.cancel
	r.cancel = nil
	r.ctx = nil
	r.started = false
	r.mu.Unlock()

	if cancel != nil {
		cancel()
	}
	r.wg.Wait()
}

func (r *SpotReconciler) Track(req SpotReconcileRequest) {
	if r == nil || r.client == nil || r.eventEmitter == nil {
		return
	}
	if req.Symbol == "" || req.OrderID <= 0 || req.ClientOrderID == "" {
		return
	}

	r.mu.Lock()
	if !r.started || r.ctx == nil {
		r.mu.Unlock()
		return
	}
	ctx := r.ctx
	r.wg.Add(1)
	r.mu.Unlock()

	go func() {
		defer r.wg.Done()
		r.reconcile(ctx, req)
	}()
}

func (r *SpotReconciler) reconcile(ctx context.Context, req SpotReconcileRequest) {
	lastStatus := normalizeOrderStatus(req.InitialStatus)
	lastExecutedQty := req.ExecutedQty
	pendingTerminalPersistence := false

	for attempt := 0; attempt < r.maxAttempts; attempt++ {
		if ctx.Err() != nil {
			return
		}

		order, err := r.client.GetOrder(ctx, req.Symbol, req.OrderID)
		if err != nil {
			r.logger.Warn().
				Err(err).
				Str("symbol", req.Symbol).
				Int64("order_id", req.OrderID).
				Int("attempt", attempt+1).
				Msg("Spot reconciliation lookup failed")
		} else {
			status := normalizeOrderStatus(order.Status)
			statusChanged := status != lastStatus || !order.ExecutedQty.Equal(lastExecutedQty)
			shouldRetryPersistence := pendingTerminalPersistence && isTerminalOrderStatus(status)
			stateApplied := true
			if statusChanged || shouldRetryPersistence {
				update := &OrderUpdate{
					EventType:     "order_update.v1",
					Venue:         "SPOT",
					Symbol:        order.Symbol,
					OrderID:       order.OrderID,
					ClientOrderID: order.ClientOrderID,
					Status:        status,
					Side:          order.Side,
					OrderType:     order.Type,
					Price:         order.Price,
					Quantity:      order.OrigQty,
					ExecutedQty:   order.ExecutedQty,
					UpdateTime:    orderUpdateTimeFromMillis(order.UpdateTime),
				}
				stateApplied = r.persistExecutionSnapshot(ctx, order, update)
				if statusChanged {
					r.emit(update)
					lastStatus = status
					lastExecutedQty = order.ExecutedQty
				}
				if isTerminalOrderStatus(status) {
					pendingTerminalPersistence = !stateApplied
				} else if stateApplied {
					pendingTerminalPersistence = false
				}
				if stateApplied && shouldRetryPersistence {
					r.emit(update)
				}
			}

			if stateApplied && isTerminalOrderStatus(status) {
				return
			}
		}

		if attempt < r.maxAttempts-1 {
			timer := time.NewTimer(r.pollInterval)
			select {
			case <-ctx.Done():
				if !timer.Stop() {
					<-timer.C
				}
				return
			case <-timer.C:
			}
		}
	}

	r.logger.Warn().
		Str("symbol", req.Symbol).
		Int64("order_id", req.OrderID).
		Str("client_order_id", req.ClientOrderID).
		Msg("Spot reconciliation exhausted without terminal status")
}

func (r *SpotReconciler) persistExecutionSnapshot(
	ctx context.Context,
	order *binance.Order,
	update *OrderUpdate,
) bool {
	if r.ledger == nil {
		return true
	}
	if order == nil || update == nil {
		return false
	}

	snapshot := SpotExecutionSnapshot{
		Symbol:        order.Symbol,
		OrderID:       order.OrderID,
		ClientOrderID: order.ClientOrderID,
		Side:          order.Side,
		OrderType:     order.Type,
		Price:         order.Price,
		Quantity:      order.OrigQty,
		ExecutedQty:   order.ExecutedQty,
		Status:        update.Status,
		UpdateTime:    update.UpdateTime,
	}

	if order.ExecutedQty.GreaterThan(decimal.Zero) {
		trades, err := r.client.GetMyTrades(ctx, order.Symbol, order.OrderID)
		if err != nil {
			r.logger.Error().
				Err(err).
				Str("symbol", order.Symbol).
				Int64("order_id", order.OrderID).
				Msg("Failed to load spot trades for reconciliation")
			return false
		}
		if len(trades) == 0 {
			r.logger.Warn().
				Str("symbol", order.Symbol).
				Int64("order_id", order.OrderID).
				Str("client_order_id", order.ClientOrderID).
				Str("status", update.Status).
				Str("executed_qty", order.ExecutedQty.String()).
				Msg("Spot reconciliation waiting for trade rows")
			return false
		}
		snapshot.Trades = make([]SpotExecutionTrade, 0, len(trades))
		totalQty := decimal.Zero
		totalQuote := decimal.Zero
		for _, trade := range trades {
			snapshot.Trades = append(snapshot.Trades, SpotExecutionTrade{
				TradeID:         trade.TradeID,
				Price:           trade.Price,
				Quantity:        trade.Qty,
				Commission:      trade.Commission,
				CommissionAsset: trade.CommissionAsset,
				Time:            trade.Time,
			})
			totalQty = totalQty.Add(trade.Qty)
			totalQuote = totalQuote.Add(trade.Price.Mul(trade.Qty))
		}
		if !totalQty.IsZero() {
			averageFillPrice := totalQuote.Div(totalQty)
			snapshot.Price = averageFillPrice
			update.Price = averageFillPrice
		}
	}

	if err := r.ledger.PersistSpotExecution(ctx, snapshot); err != nil {
		r.logger.Error().
			Err(err).
			Str("symbol", snapshot.Symbol).
			Str("client_order_id", snapshot.ClientOrderID).
			Str("status", snapshot.Status).
			Msg("Failed to persist reconciled spot execution snapshot")
		return false
	}
	return true
}

func (r *SpotReconciler) emit(update *OrderUpdate) {
	if update == nil || r.eventEmitter == nil {
		return
	}

	r.mu.Lock()
	emitCtx := r.ctx
	started := r.started
	r.mu.Unlock()
	if !started || emitCtx == nil || emitCtx.Err() != nil {
		return
	}

	if err := r.eventEmitter.EmitOrderUpdate(emitCtx, update); err != nil {
		r.logger.Error().
			Err(err).
			Str("symbol", update.Symbol).
			Str("client_order_id", update.ClientOrderID).
			Str("status", update.Status).
			Msg("Failed to emit reconciled spot order update")
	}
}

func normalizeOrderStatus(status string) string {
	return strings.ToUpper(strings.TrimSpace(status))
}

func isTerminalOrderStatus(status string) bool {
	switch normalizeOrderStatus(status) {
	case "FILLED", "CANCELED", "REJECTED", "EXPIRED":
		return true
	default:
		return false
	}
}

func orderUpdateTimeFromMillis(value int64) time.Time {
	if value <= 0 {
		return time.Now()
	}
	return time.UnixMilli(value)
}
