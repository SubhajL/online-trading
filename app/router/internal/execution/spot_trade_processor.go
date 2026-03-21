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

	fills := make([]pnl.Fill, 0, len(insertedTrades))
	for _, trade := range insertedTrades {
		fills = append(fills, pnl.Fill{
			Side:     snapshot.Side,
			Quantity: trade.Quantity,
			Price:    trade.Price,
		})
	}
	current, totalRealized, err := applyFillsToActivePosition(activeFound, active, fills)
	if err != nil {
		return err
	}

	entryOrderID := ""
	if orderRec != nil {
		entryOrderID = orderRec.OrderID.String()
	}
	persistence := buildPositionPersistence(
		"SPOT",
		snapshot.Symbol,
		current,
		activeFound,
		active,
		entryOrderID,
		insertedTrades[len(insertedTrades)-1].Price,
		totalRealized,
		commissionDelta,
		decimal.Zero,
		slippageDelta,
		updateTime,
	)
	if persistence.close != nil {
		return p.positions.CloseActive(ctx, tx, "SPOT", snapshot.Symbol, *persistence.close)
	}
	return p.positions.UpsertActive(ctx, tx, *persistence.upsert)
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
