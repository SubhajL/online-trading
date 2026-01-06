package api

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/shopspring/decimal"

	"router/internal/orders"
	"router/internal/storage"
)

type IntentPersister interface {
	PersistBracketIntent(
		ctx context.Context,
		req orders.PlaceBracketRequest,
		resp orders.PlaceBracketResponse,
	) error
}

type PostgresIntentPersister struct {
	pool   *pgxpool.Pool
	orders *storage.OrderRepo
	logger zerolog.Logger
}

func NewPostgresIntentPersister(pool *pgxpool.Pool, logger zerolog.Logger) *PostgresIntentPersister {
	return &PostgresIntentPersister{
		pool:   pool,
		orders: storage.NewOrderRepo(),
		logger: logger,
	}
}

func (p *PostgresIntentPersister) PersistBracketIntent(
	ctx context.Context,
	req orders.PlaceBracketRequest,
	resp orders.PlaceBracketResponse,
) error {
	if p.pool == nil {
		return fmt.Errorf("pool is required")
	}

	intents, err := buildBracketOrderIntents(req, resp)
	if err != nil {
		return err
	}

	return storage.RunInTx(ctx, p.pool, func(tx pgx.Tx) error {
		for _, intent := range intents {
			_, err := p.orders.UpsertOrderIntent(ctx, tx, intent)
			if err != nil {
				return err
			}
		}
		return nil
	})
}

func buildBracketOrderIntents(
	req orders.PlaceBracketRequest,
	resp orders.PlaceBracketResponse,
) ([]storage.OrderIntent, error) {
	venue := "spot"
	if req.IsFutures {
		venue = "futures"
	}

	signalID, timeframe, zone := extractProvenance(req.Metadata)

	if resp.ClientOrderIDs.Main == "" || resp.ClientOrderIDs.StopLoss == "" {
		return nil, fmt.Errorf("missing client order ids in response")
	}
	if len(resp.ClientOrderIDs.TakeProfits) != len(req.TakeProfitPrices) {
		return nil, fmt.Errorf("tp count mismatch")
	}

	timeInForce := "GTC"
	entryType := req.OrderType
	if entryType == "" {
		if req.EntryPrice.IsZero() {
			entryType = "MARKET"
		} else {
			entryType = "LIMIT"
		}
	}

	intents := make([]storage.OrderIntent, 0, 2+len(req.TakeProfitPrices))
	intents = append(intents, storage.OrderIntent{
		Venue:          venue,
		Symbol:         req.Symbol,
		ClientOrderID:  resp.ClientOrderIDs.Main,
		Side:           req.Side,
		Type:           entryType,
		TimeInForce:    timeInForce,
		Quantity:       req.Quantity,
		Price:          req.EntryPrice,
		StopPrice:      decimal.Zero,
		ReduceOnly:     false,
		ClosePosition:  false,
		RequestedPrice: req.EntryPrice,
		SignalID:       signalID,
		Timeframe:      timeframe,
		Zone:           zone,
	})

	tpCount := len(req.TakeProfitPrices)
	if tpCount > 0 {
		perTP := req.Quantity.Div(decimal.NewFromInt(int64(tpCount)))
		for i, tpPrice := range req.TakeProfitPrices {
			intents = append(intents, storage.OrderIntent{
				Venue:          venue,
				Symbol:         req.Symbol,
				ClientOrderID:  resp.ClientOrderIDs.TakeProfits[i],
				Side:           oppositeSide(req.Side),
				Type:           "LIMIT",
				TimeInForce:    timeInForce,
				Quantity:       perTP,
				Price:          tpPrice,
				StopPrice:      decimal.Zero,
				ReduceOnly:     req.IsFutures,
				ClosePosition:  false,
				RequestedPrice: tpPrice,
				SignalID:       signalID,
				Timeframe:      timeframe,
				Zone:           zone,
			})
		}
	}

	slType := "STOP_LOSS_LIMIT"
	slPrice := req.StopLossPrice
	slStop := req.StopLossPrice
	reduceOnly := false
	closePosition := false
	if req.IsFutures {
		slType = "STOP_MARKET"
		slPrice = decimal.Zero
		reduceOnly = true
		closePosition = true
	}

	intents = append(intents, storage.OrderIntent{
		Venue:          venue,
		Symbol:         req.Symbol,
		ClientOrderID:  resp.ClientOrderIDs.StopLoss,
		Side:           oppositeSide(req.Side),
		Type:           slType,
		TimeInForce:    timeInForce,
		Quantity:       req.Quantity,
		Price:          slPrice,
		StopPrice:      slStop,
		ReduceOnly:     reduceOnly,
		ClosePosition:  closePosition,
		RequestedPrice: req.StopLossPrice,
		SignalID:       signalID,
		Timeframe:      timeframe,
		Zone:           zone,
	})

	return intents, nil
}

func oppositeSide(side string) string {
	if side == "BUY" {
		return "SELL"
	}
	return "BUY"
}

func extractProvenance(metadata map[string]any) (string, string, map[string]any) {
	if metadata == nil {
		return "", "", nil
	}

	signalID, _ := metadata["signal_id"].(string)
	timeframe, _ := metadata["timeframe"].(string)

	var zone map[string]any
	if rawZone, ok := metadata["zone"].(map[string]any); ok {
		zone = rawZone
	}

	return signalID, timeframe, zone
}
