package orders

import (
	"context"
	"time"

	"github.com/shopspring/decimal"
)

type SpotExecutionTrade struct {
	TradeID         int64
	Price           decimal.Decimal
	Quantity        decimal.Decimal
	Commission      decimal.Decimal
	CommissionAsset string
	Time            time.Time
}

type SpotExecutionSnapshot struct {
	Symbol        string
	OrderID       int64
	ClientOrderID string
	Side          string
	OrderType     string
	Price         decimal.Decimal
	Quantity      decimal.Decimal
	ExecutedQty   decimal.Decimal
	Status        string
	UpdateTime    time.Time
	Trades        []SpotExecutionTrade
}

type spotExecutionLedger interface {
	PersistSpotExecution(ctx context.Context, snapshot SpotExecutionSnapshot) error
}
