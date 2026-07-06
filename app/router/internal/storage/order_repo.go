package storage

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/shopspring/decimal"
)

type OrderIntent struct {
	Venue         string
	Symbol        string
	ClientOrderID string
	Side          string
	Type          string
	TimeInForce   string
	Quantity      decimal.Decimal
	Price         decimal.Decimal
	StopPrice     decimal.Decimal
	ReduceOnly    bool
	ClosePosition bool

	RequestedPrice decimal.Decimal
	SignalID       string
	Timeframe      string
	Zone           map[string]any

	// Execution quality timing fields
	DecisionTs    *time.Time      // Timestamp when trading decision was made
	ExpectedPrice decimal.Decimal // Expected fill price from decision
}

type OrderRecord struct {
	OrderID       uuid.UUID
	Venue         string
	Symbol        string
	ClientOrderID string
	Side          string

	ReduceOnly    bool
	ClosePosition bool

	RequestedPrice  decimal.Decimal
	TotalCommission decimal.Decimal
	TotalSlippage   decimal.Decimal
}

type OrderRepo struct{}

func NewOrderRepo() *OrderRepo {
	return &OrderRepo{}
}

const upsertOrderIntentSQL = `INSERT INTO orders (
			client_order_id, venue, symbol, side, type, quantity, price, stop_price, time_in_force,
			status, filled_quantity, created_at, reduce_only, close_position,
			requested_price, signal_id, timeframe, zone,
			decision_ts, expected_price, router_received_ts
		) VALUES (
			$1,$2,$3,$4,$5,$6, NULLIF($7::numeric,0::numeric), NULLIF($8::numeric,0::numeric), $9,
			'NEW', 0, now(), $10, $11,
			NULLIF($12::numeric,0::numeric), NULLIF($13,''), NULLIF($14,''), NULLIF($15,'')::jsonb,
			$16, NULLIF($17::numeric,0::numeric), $18
		)
		ON CONFLICT (venue, client_order_id)
		DO UPDATE SET
			symbol = EXCLUDED.symbol,
			side = EXCLUDED.side,
			type = EXCLUDED.type,
			quantity = EXCLUDED.quantity,
			price = EXCLUDED.price,
			stop_price = EXCLUDED.stop_price,
			time_in_force = EXCLUDED.time_in_force,
			reduce_only = EXCLUDED.reduce_only,
			close_position = EXCLUDED.close_position,
			requested_price = EXCLUDED.requested_price,
			signal_id = EXCLUDED.signal_id,
			timeframe = EXCLUDED.timeframe,
			zone = EXCLUDED.zone,
			decision_ts = COALESCE(orders.decision_ts, EXCLUDED.decision_ts),
			expected_price = COALESCE(orders.expected_price, EXCLUDED.expected_price),
			router_received_ts = COALESCE(orders.router_received_ts, EXCLUDED.router_received_ts)
		RETURNING order_id`

func (r *OrderRepo) UpsertOrderIntent(ctx context.Context, tx pgx.Tx, intent OrderIntent) (uuid.UUID, error) {
	if intent.Venue == "" {
		return uuid.Nil, fmt.Errorf("venue is required")
	}
	if intent.Symbol == "" {
		return uuid.Nil, fmt.Errorf("symbol is required")
	}
	if intent.ClientOrderID == "" {
		return uuid.Nil, fmt.Errorf("client_order_id is required")
	}
	if intent.Side != "BUY" && intent.Side != "SELL" {
		return uuid.Nil, fmt.Errorf("invalid side: %s", intent.Side)
	}
	if intent.Type == "" {
		return uuid.Nil, fmt.Errorf("type is required")
	}
	if intent.Quantity.LessThanOrEqual(decimal.Zero) {
		return uuid.Nil, fmt.Errorf("quantity must be positive")
	}

	var zoneJSON []byte
	if intent.Zone != nil {
		raw, err := json.Marshal(intent.Zone)
		if err != nil {
			return uuid.Nil, fmt.Errorf("marshal zone: %w", err)
		}
		zoneJSON = raw
	}

	if intent.RequestedPrice.IsZero() {
		intent.RequestedPrice = intent.Price
	}

	zoneValue := ""
	if zoneJSON != nil {
		zoneValue = string(zoneJSON)
	}

	// Set router_received_ts to now() for execution quality tracking
	routerReceivedTs := time.Now()

	row := tx.QueryRow(
		ctx,
		upsertOrderIntentSQL,
		intent.ClientOrderID,
		intent.Venue,
		intent.Symbol,
		intent.Side,
		intent.Type,
		intent.Quantity,
		intent.Price,
		intent.StopPrice,
		intent.TimeInForce,
		intent.ReduceOnly,
		intent.ClosePosition,
		intent.RequestedPrice,
		intent.SignalID,
		intent.Timeframe,
		zoneValue,
		intent.DecisionTs,
		intent.ExpectedPrice,
		routerReceivedTs,
	)

	var orderID uuid.UUID
	if err := row.Scan(&orderID); err != nil {
		return uuid.Nil, fmt.Errorf("upsert order intent: %w", err)
	}

	return orderID, nil
}

func (r *OrderRepo) GetByClientOrderID(
	ctx context.Context,
	tx pgx.Tx,
	venue string,
	clientOrderID string,
) (*OrderRecord, bool, error) {
	if venue == "" {
		return nil, false, fmt.Errorf("venue is required")
	}
	if clientOrderID == "" {
		return nil, false, fmt.Errorf("client_order_id is required")
	}

	row := tx.QueryRow(
		ctx,
		`SELECT order_id, venue, symbol, client_order_id, side, reduce_only, close_position,
		        COALESCE(requested_price, 0), COALESCE(total_commission, 0), COALESCE(total_slippage, 0)
		   FROM orders
		  WHERE venue = $1 AND client_order_id = $2`,
		venue,
		clientOrderID,
	)

	var rec OrderRecord
	if err := row.Scan(
		&rec.OrderID,
		&rec.Venue,
		&rec.Symbol,
		&rec.ClientOrderID,
		&rec.Side,
		&rec.ReduceOnly,
		&rec.ClosePosition,
		&rec.RequestedPrice,
		&rec.TotalCommission,
		&rec.TotalSlippage,
	); err != nil {
		if err == pgx.ErrNoRows {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("select order: %w", err)
	}

	return &rec, true, nil
}

type OrderFillUpdate struct {
	Status           string
	FilledQuantity   decimal.Decimal
	AverageFillPrice decimal.Decimal
	ExchangeOrderID  string
	LastUpdateTime   time.Time
	CommissionDelta  decimal.Decimal
	CommissionAsset  string
	SlippageDelta    decimal.Decimal
}

func (r *OrderRepo) ApplyFillUpdate(
	ctx context.Context,
	tx pgx.Tx,
	venue string,
	clientOrderID string,
	update OrderFillUpdate,
) (*OrderRecord, bool, error) {
	if venue == "" {
		return nil, false, fmt.Errorf("venue is required")
	}
	if clientOrderID == "" {
		return nil, false, fmt.Errorf("client_order_id is required")
	}
	if update.Status == "" {
		return nil, false, fmt.Errorf("status is required")
	}
	if update.FilledQuantity.LessThan(decimal.Zero) {
		return nil, false, fmt.Errorf("filled_quantity must be non-negative")
	}

	row := tx.QueryRow(
		ctx,
		`UPDATE orders
		    SET status = $1,
		        filled_quantity = $2,
		        average_fill_price = NULLIF($3::numeric, 0::numeric),
		        exchange_order_id = NULLIF($4::text, ''),
		        last_update_time = $5,
		        total_commission = COALESCE(total_commission, 0) + $6,
		        commission = COALESCE(total_commission, 0) + $6,
		        commission_asset = NULLIF($7::text, ''),
		        total_slippage = COALESCE(total_slippage, 0) + $8
		  WHERE venue = $9 AND client_order_id = $10
		  RETURNING order_id, venue, symbol, client_order_id, side, reduce_only, close_position,
		            COALESCE(requested_price, 0), COALESCE(total_commission, 0), COALESCE(total_slippage, 0)`,
		update.Status,
		update.FilledQuantity,
		update.AverageFillPrice,
		update.ExchangeOrderID,
		update.LastUpdateTime,
		update.CommissionDelta,
		update.CommissionAsset,
		update.SlippageDelta,
		venue,
		clientOrderID,
	)

	var rec OrderRecord
	if err := row.Scan(
		&rec.OrderID,
		&rec.Venue,
		&rec.Symbol,
		&rec.ClientOrderID,
		&rec.Side,
		&rec.ReduceOnly,
		&rec.ClosePosition,
		&rec.RequestedPrice,
		&rec.TotalCommission,
		&rec.TotalSlippage,
	); err != nil {
		if err == pgx.ErrNoRows {
			return nil, false, nil
		}
		return nil, false, fmt.Errorf("apply fill update: %w", err)
	}

	return &rec, true, nil
}

// OrderExecutionRow represents order data for execution quality analysis
type OrderExecutionRow struct {
	OrderID          uuid.UUID
	Venue            string
	Symbol           string
	Side             string
	Status           string
	ExpectedPrice    decimal.Decimal
	AverageFillPrice decimal.Decimal
	DecisionTs       *time.Time
	RouterReceivedTs *time.Time
	RouterSentTs     *time.Time
	ExchangeAckTs    *time.Time
	FirstFillTs      *time.Time
	FilledTs         *time.Time
}

// GetOrdersForExecutionQuality retrieves orders with timing data for execution quality analysis
func (r *OrderRepo) GetOrdersForExecutionQuality(
	ctx context.Context,
	tx pgx.Tx,
	venue string,
	startTime time.Time,
	endTime time.Time,
	limit int,
) ([]OrderExecutionRow, error) {
	if limit <= 0 {
		limit = 1000
	}

	query := `
		SELECT order_id, venue, symbol, side, status,
		       COALESCE(expected_price, 0), COALESCE(average_fill_price, 0),
		       decision_ts, router_received_ts, router_sent_ts,
		       exchange_ack_ts, first_fill_ts, filled_ts
		FROM orders
		WHERE ($1 = '' OR venue = $1)
		  AND router_received_ts >= $2
		  AND router_received_ts <= $3
		ORDER BY router_received_ts DESC
		LIMIT $4
	`

	rows, err := tx.Query(ctx, query, venue, startTime, endTime, limit)
	if err != nil {
		return nil, fmt.Errorf("query orders for execution quality: %w", err)
	}
	defer rows.Close()

	var result []OrderExecutionRow
	for rows.Next() {
		var rec OrderExecutionRow
		if err := rows.Scan(
			&rec.OrderID,
			&rec.Venue,
			&rec.Symbol,
			&rec.Side,
			&rec.Status,
			&rec.ExpectedPrice,
			&rec.AverageFillPrice,
			&rec.DecisionTs,
			&rec.RouterReceivedTs,
			&rec.RouterSentTs,
			&rec.ExchangeAckTs,
			&rec.FirstFillTs,
			&rec.FilledTs,
		); err != nil {
			return nil, fmt.Errorf("scan order row: %w", err)
		}
		result = append(result, rec)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate order rows: %w", err)
	}

	return result, nil
}
