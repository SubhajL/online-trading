package execution

import (
	"time"

	"github.com/shopspring/decimal"

	"router/internal/pnl"
	"router/internal/storage"
)

type positionPersistence struct {
	close  *storage.PositionClose
	upsert *storage.ActivePositionUpsert
}

func applyFillsToActivePosition(
	activeFound bool,
	active *storage.ActivePosition,
	fills []pnl.Fill,
) (*pnl.Position, decimal.Decimal, error) {
	var current *pnl.Position
	if activeFound && active != nil && !active.Size.IsZero() {
		current = &pnl.Position{
			Side:       active.Side,
			Quantity:   active.Size,
			EntryPrice: active.EntryPrice,
		}
	}

	totalRealized := decimal.Zero
	for _, fill := range fills {
		next, realizedDelta, err := pnl.ApplyFillToPosition(current, fill)
		if err != nil {
			return nil, decimal.Zero, err
		}
		current = next
		totalRealized = totalRealized.Add(realizedDelta)
	}

	return current, totalRealized, nil
}

func buildPositionPersistence(
	venue string,
	symbol string,
	current *pnl.Position,
	activeFound bool,
	active *storage.ActivePosition,
	entryOrderID string,
	currentPrice decimal.Decimal,
	realizedDelta decimal.Decimal,
	commissionDelta decimal.Decimal,
	fundingDelta decimal.Decimal,
	slippageDelta decimal.Decimal,
	updateTime time.Time,
) positionPersistence {
	if current == nil {
		return positionPersistence{
			close: &storage.PositionClose{
				ClosedAt:       updateTime,
				CurrentPrice:   currentPrice,
				RealizedPnL:    realizedDelta,
				CommissionPaid: commissionDelta,
				FundingPaid:    fundingDelta,
				SlippagePaid:   slippageDelta,
			},
		}
	}

	openedAt := updateTime
	totalRealized := realizedDelta
	totalCommission := commissionDelta
	totalFunding := fundingDelta
	totalSlippage := slippageDelta
	if activeFound && active != nil && active.Side == current.Side {
		openedAt = active.OpenedAt
		totalRealized = active.RealizedPnL.Add(realizedDelta)
		totalCommission = active.CommissionPaid.Add(commissionDelta)
		totalFunding = active.FundingPaid.Add(fundingDelta)
		totalSlippage = active.SlippagePaid.Add(slippageDelta)
		if active.EntryOrderID != "" {
			entryOrderID = active.EntryOrderID
		}
	}

	return positionPersistence{
		upsert: &storage.ActivePositionUpsert{
			Venue:          venue,
			Symbol:         symbol,
			Side:           current.Side,
			Size:           current.Quantity,
			EntryPrice:     current.EntryPrice,
			EntryOrderID:   entryOrderID,
			CurrentPrice:   currentPrice,
			RealizedPnL:    totalRealized,
			CommissionPaid: totalCommission,
			FundingPaid:    totalFunding,
			SlippagePaid:   totalSlippage,
			OpenedAt:       openedAt,
			UpdatedAt:      updateTime,
		},
	}
}
