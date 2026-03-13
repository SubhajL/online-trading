package execution

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"router/internal/orders"
	"router/internal/pnl"
	"router/internal/storage"
)

type SpotTradeProcessor struct {
	pool      *pgxpool.Pool
	orders    *storage.OrderRepo
	fills     *storage.FillRepo
	positions *storage.PositionRepo
}

func NewSpotTradeProcessor(
	pool *pgxpool.Pool,
	ordersRepo *storage.OrderRepo,
	fillsRepo *storage.FillRepo,
	positionsRepo *storage.PositionRepo,
) (*SpotTradeProcessor, error) {
	if pool == nil {
		return nil, fmt.Errorf("pool is required")
	}
	if ordersRepo == nil || fillsRepo == nil || positionsRepo == nil {
		return nil, fmt.Errorf("repos are required")
	}
	return &SpotTradeProcessor{
		pool:      pool,
		orders:    ordersRepo,
		fills:     fillsRepo,
		positions: positionsRepo,
	}, nil
}

func (p *SpotTradeProcessor) PersistSpotExecution(
	ctx context.Context,
	snapshot orders.SpotExecutionSnapshot,
) error {
	return storage.RunInTx(ctx, p.pool, func(tx pgx.Tx) error {
		return p.persistSpotExecutionTx(ctx, tx, snapshot)
	})
}

func (p *SpotTradeProcessor) persistSpotExecutionTx(
	ctx context.Context,
	tx pgx.Tx,
	snapshot orders.SpotExecutionSnapshot,
) error {
	if snapshot.ClientOrderID == "" {
		return fmt.Errorf("client_order_id is required")
	}
	if snapshot.Symbol == "" {
		return fmt.Errorf("symbol is required")
	}
	if snapshot.Side != "BUY" && snapshot.Side != "SELL" {
		return fmt.Errorf("invalid side: %s", snapshot.Side)
	}
	if snapshot.Status == "" {
		return fmt.Errorf("status is required")
	}

	orderRec, found, err := p.orders.GetByClientOrderID(ctx, tx, "SPOT", snapshot.ClientOrderID)
	if err != nil {
		return err
	}
	if !found || orderRec == nil {
		return nil
	}

	updateTime := snapshot.UpdateTime.UTC()
	if updateTime.IsZero() {
		updateTime = time.Now().UTC()
	}

	averageFillPrice, totalFilledQty := spotAverageFillPrice(snapshot)
	if snapshot.ExecutedQty.IsZero() {
		snapshot.ExecutedQty = totalFilledQty
	}

	var (
		insertedTrades  []orders.SpotExecutionTrade
		commissionDelta decimal.Decimal
		slippageDelta   decimal.Decimal
		commissionAsset string
		exchangeOrderID string
	)
	if snapshot.OrderID > 0 {
		exchangeOrderID = strconv.FormatInt(snapshot.OrderID, 10)
	}

	for _, trade := range snapshot.Trades {
		tradeTime := trade.Time.UTC()
		if tradeTime.IsZero() {
			tradeTime = updateTime
		}
		trade.Time = tradeTime

		slippage, err := storage.ComputeSignedSlippage(
			orderRec.Side,
			orderRec.RequestedPrice,
			trade.Price,
			trade.Quantity,
		)
		if err != nil {
			return err
		}

		inserted, err := p.fills.InsertFillIfNew(ctx, tx, storage.FillRecord{
			Venue:           "SPOT",
			Symbol:          snapshot.Symbol,
			TradeID:         trade.TradeID,
			ClientOrderID:   snapshot.ClientOrderID,
			Side:            snapshot.Side,
			Price:           trade.Price,
			Quantity:        trade.Quantity,
			Commission:      trade.Commission,
			CommissionAsset: trade.CommissionAsset,
			RealizedPnL:     decimal.Zero,
			Slippage:        slippage,
		})
		if err != nil {
			return err
		}
		if !inserted {
			continue
		}

		insertedTrades = append(insertedTrades, trade)
		commissionDelta = commissionDelta.Add(trade.Commission)
		slippageDelta = slippageDelta.Add(slippage)
		if trade.CommissionAsset != "" {
			commissionAsset = trade.CommissionAsset
		}
	}

	orderRec, _, err = p.orders.ApplyFillUpdate(ctx, tx, "SPOT", snapshot.ClientOrderID, storage.OrderFillUpdate{
		Status:           snapshot.Status,
		FilledQuantity:   snapshot.ExecutedQty,
		AverageFillPrice: averageFillPrice,
		ExchangeOrderID:  exchangeOrderID,
		LastUpdateTime:   updateTime,
		CommissionDelta:  commissionDelta,
		CommissionAsset:  commissionAsset,
		SlippageDelta:    slippageDelta,
	})
	if err != nil {
		return err
	}

	if len(insertedTrades) == 0 {
		return nil
	}

	active, activeFound, err := p.positions.GetActive(ctx, tx, "SPOT", snapshot.Symbol)
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

	totalRealized := decimal.Zero
	for _, trade := range insertedTrades {
		next, realizedDelta, err := pnl.ApplyFillToPosition(current, pnl.Fill{
			Side:     snapshot.Side,
			Quantity: trade.Quantity,
			Price:    trade.Price,
		})
		if err != nil {
			return err
		}
		current = next
		totalRealized = totalRealized.Add(realizedDelta)
	}

	if current == nil {
		return p.positions.CloseActive(ctx, tx, "SPOT", snapshot.Symbol, storage.PositionClose{
			ClosedAt:       updateTime,
			CurrentPrice:   insertedTrades[len(insertedTrades)-1].Price,
			RealizedPnL:    totalRealized,
			CommissionPaid: commissionDelta,
			FundingPaid:    decimal.Zero,
			SlippagePaid:   slippageDelta,
		})
	}

	openedAt := updateTime
	totalCommission := commissionDelta
	totalSlippage := slippageDelta
	entryOrderID := ""
	if orderRec != nil {
		entryOrderID = orderRec.OrderID.String()
	}
	if activeFound && active != nil && active.Side == current.Side {
		openedAt = active.OpenedAt
		totalRealized = active.RealizedPnL.Add(totalRealized)
		totalCommission = active.CommissionPaid.Add(commissionDelta)
		totalSlippage = active.SlippagePaid.Add(slippageDelta)
		if active.EntryOrderID != "" {
			entryOrderID = active.EntryOrderID
		}
	}

	return p.positions.UpsertActive(ctx, tx, storage.ActivePositionUpsert{
		Venue:          "SPOT",
		Symbol:         snapshot.Symbol,
		Side:           current.Side,
		Size:           current.Quantity,
		EntryPrice:     current.EntryPrice,
		EntryOrderID:   entryOrderID,
		CurrentPrice:   insertedTrades[len(insertedTrades)-1].Price,
		RealizedPnL:    totalRealized,
		CommissionPaid: totalCommission,
		FundingPaid:    decimal.Zero,
		SlippagePaid:   totalSlippage,
		OpenedAt:       openedAt,
		UpdatedAt:      updateTime,
	})
}

func spotAverageFillPrice(snapshot orders.SpotExecutionSnapshot) (decimal.Decimal, decimal.Decimal) {
	totalQty := decimal.Zero
	totalQuote := decimal.Zero
	for _, trade := range snapshot.Trades {
		totalQty = totalQty.Add(trade.Quantity)
		totalQuote = totalQuote.Add(trade.Price.Mul(trade.Quantity))
	}
	if totalQty.IsZero() {
		return decimal.Zero, decimal.Zero
	}
	return totalQuote.Div(totalQty), totalQty
}
