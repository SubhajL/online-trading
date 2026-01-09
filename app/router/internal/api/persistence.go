package api

import (
	"context"
	"fmt"
	"time"

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

	prov := extractProvenance(req.Metadata)

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
		SignalID:       prov.signalID,
		Timeframe:      prov.timeframe,
		Zone:           prov.zone,
		DecisionTs:     prov.decisionTs,
		ExpectedPrice:  prov.expectedPrice,
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
				SignalID:       prov.signalID,
				Timeframe:      prov.timeframe,
				Zone:           prov.zone,
				DecisionTs:     prov.decisionTs,
				ExpectedPrice:  tpPrice, // TP uses its own price as expected
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
		SignalID:       prov.signalID,
		Timeframe:      prov.timeframe,
		Zone:           prov.zone,
		DecisionTs:     prov.decisionTs,
		ExpectedPrice:  req.StopLossPrice, // SL uses its own price as expected
	})

	return intents, nil
}

func oppositeSide(side string) string {
	if side == "BUY" {
		return "SELL"
	}
	return "BUY"
}

type provenanceData struct {
	signalID      string
	timeframe     string
	zone          map[string]any
	decisionTs    *time.Time
	expectedPrice decimal.Decimal
}

func extractProvenance(metadata map[string]any) provenanceData {
	if metadata == nil {
		return provenanceData{}
	}

	var result provenanceData
	result.signalID, _ = metadata["signal_id"].(string)
	result.timeframe, _ = metadata["timeframe"].(string)

	if rawZone, ok := metadata["zone"].(map[string]any); ok {
		result.zone = rawZone
	}

	// Extract decision_ts for execution quality tracking
	if decisionTsStr, ok := metadata["decision_ts"].(string); ok && decisionTsStr != "" {
		if ts, err := time.Parse(time.RFC3339, decisionTsStr); err == nil {
			result.decisionTs = &ts
		}
	}

	// Extract expected_price for slippage calculation
	if priceStr, ok := metadata["expected_price"].(string); ok && priceStr != "" {
		if d, err := decimal.NewFromString(priceStr); err == nil {
			result.expectedPrice = d
		}
	}

	return result
}
