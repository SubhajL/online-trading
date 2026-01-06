package execution

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"router/internal/pnl"
	"router/internal/storage"
	"router/internal/websocket"
)

func shouldProcessOrderTradeUpdate(event *websocket.FuturesOrderTradeUpdateEvent) bool {
	if event == nil {
		return false
	}
	if event.EventType != "ORDER_TRADE_UPDATE" {
		return false
	}

	data := event.OrderTradeUpdate
	if data.ExecutionType != "TRADE" {
		return false
	}
	if data.TradeID <= 0 {
		return false
	}
	if data.LastExecutedQuantity.LessThanOrEqual(decimal.Zero) {
		return false
	}
	return true
}

func futuresEventTimeUTC(millis int64) time.Time {
	return time.UnixMilli(millis).UTC()
}

type TradeProcessor struct {
	pool      *pgxpool.Pool
	orders    *storage.OrderRepo
	fills     *storage.FillRepo
	positions *storage.PositionRepo
	venue     string
}

func NewTradeProcessor(
	pool *pgxpool.Pool,
	ordersRepo *storage.OrderRepo,
	fillsRepo *storage.FillRepo,
	positionsRepo *storage.PositionRepo,
	venue string,
) (*TradeProcessor, error) {
	if pool == nil {
		return nil, fmt.Errorf("pool is required")
	}
	if ordersRepo == nil || fillsRepo == nil || positionsRepo == nil {
		return nil, fmt.Errorf("repos are required")
	}
	if venue == "" {
		return nil, fmt.Errorf("venue is required")
	}
	return &TradeProcessor{
		pool:      pool,
		orders:    ordersRepo,
		fills:     fillsRepo,
		positions: positionsRepo,
		venue:     venue,
	}, nil
}

func (p *TradeProcessor) HandleFuturesOrderTradeUpdate(
	ctx context.Context,
	event *websocket.FuturesOrderTradeUpdateEvent,
) error {
	if !shouldProcessOrderTradeUpdate(event) {
		return nil
	}

	return storage.RunInTx(ctx, p.pool, func(tx pgx.Tx) error {
		return p.handleFuturesOrderTradeUpdateTx(ctx, tx, event)
	})
}

func (p *TradeProcessor) handleFuturesOrderTradeUpdateTx(
	ctx context.Context,
	tx pgx.Tx,
	event *websocket.FuturesOrderTradeUpdateEvent,
) error {
	if !shouldProcessOrderTradeUpdate(event) {
		return nil
	}

	data := event.OrderTradeUpdate

	orderRec, found, err := p.orders.GetByClientOrderID(ctx, tx, p.venue, data.ClientOrderID)
	if err != nil {
		return err
	}
	if !found || orderRec == nil {
		return nil
	}

	slippage, err := storage.ComputeSignedSlippage(
		data.Side,
		orderRec.RequestedPrice,
		data.LastExecutedPrice,
		data.LastExecutedQuantity,
	)
	if err != nil {
		return err
	}

	fill := storage.FillRecord{
		Venue:           p.venue,
		Symbol:          data.Symbol,
		TradeID:         data.TradeID,
		ClientOrderID:   data.ClientOrderID,
		Side:            data.Side,
		Price:           data.LastExecutedPrice,
		Quantity:        data.LastExecutedQuantity,
		Commission:      data.CommissionAmount,
		CommissionAsset: data.CommissionAsset,
		RealizedPnL:     data.RealizedProfit,
		Slippage:        slippage,
	}

	inserted, err := p.fills.InsertFillIfNew(ctx, tx, fill)
	if err != nil {
		return err
	}
	if !inserted {
		return nil
	}

	updateTime := futuresEventTimeUTC(event.TransactionTime)
	_, _, err = p.orders.ApplyFillUpdate(ctx, tx, p.venue, data.ClientOrderID, storage.OrderFillUpdate{
		Status:           data.OrderStatus,
		FilledQuantity:   data.CumulativeFilledQty,
		AverageFillPrice: data.AvgPrice,
		ExchangeOrderID:  fmt.Sprintf("%d", data.OrderID),
		LastUpdateTime:   updateTime,
		CommissionDelta:  data.CommissionAmount,
		CommissionAsset:  data.CommissionAsset,
		SlippageDelta:    slippage,
	})
	if err != nil {
		return err
	}

	active, activeFound, err := p.positions.GetActive(ctx, tx, p.venue, data.Symbol)
	if err != nil {
		return err
	}

	var current *pnl.Position
	if activeFound && active != nil && !active.Size.IsZero() {
		current = &pnl.Position{
			Side:       active.Side,
			Quantity:   active.Size,
			EntryPrice: active.EntryPrice,
		}
	}

	next, realizedDelta, err := pnl.ApplyFillToPosition(current, pnl.Fill{
		Side:     data.Side,
		Quantity: data.LastExecutedQuantity,
		Price:    data.LastExecutedPrice,
	})
	if err != nil {
		return err
	}

	commissionDelta := data.CommissionAmount
	slippageDelta := slippage
	if next == nil {
		return p.positions.CloseActive(ctx, tx, p.venue, data.Symbol, storage.PositionClose{
			ClosedAt:       updateTime,
			CurrentPrice:   data.LastExecutedPrice,
			RealizedPnL:    realizedDelta,
			CommissionPaid: commissionDelta,
			SlippagePaid:   slippageDelta,
		})
	}

	openedAt := updateTime
	totalRealized := realizedDelta
	totalCommission := commissionDelta
	totalSlippage := slippageDelta
	totalFunding := decimal.Zero
	if activeFound && active != nil {
		openedAt = active.OpenedAt
		totalRealized = active.RealizedPnL.Add(realizedDelta)
		totalCommission = active.CommissionPaid.Add(commissionDelta)
		totalSlippage = active.SlippagePaid.Add(slippageDelta)
		totalFunding = active.FundingPaid
	}

	return p.positions.UpsertActive(ctx, tx, storage.ActivePositionUpsert{
		Venue:          p.venue,
		Symbol:         data.Symbol,
		Side:           next.Side,
		Size:           next.Quantity,
		EntryPrice:     next.EntryPrice,
		CurrentPrice:   data.LastExecutedPrice,
		RealizedPnL:    totalRealized,
		CommissionPaid: totalCommission,
		FundingPaid:    totalFunding,
		SlippagePaid:   totalSlippage,
		OpenedAt:       openedAt,
		UpdatedAt:      updateTime,
	})
}
