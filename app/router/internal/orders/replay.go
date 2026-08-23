package orders

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"maps"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

// bracketRecordFromRequest builds the durable reservation for a request that
// carries caller-supplied client order ids (the engine contract).
func bracketRecordFromRequest(req *PlaceBracketRequest, legsOnFill bool) storage.BracketRecord {
	venue := "SPOT"
	if req.IsFutures {
		venue = "USD_M"
	}

	legs := make([]storage.BracketLegRecord, 0, len(req.ClientOrderIDs.TakeProfits)+2)
	legs = append(legs, storage.BracketLegRecord{
		Role:          "ENTRY",
		ClientOrderID: req.ClientOrderIDs.Main,
		Price:         req.EntryPrice,
		Quantity:      req.Quantity,
		Status:        storage.LegStatusPlanned,
	})
	for i, tpID := range req.ClientOrderIDs.TakeProfits {
		price := tpPriceAt(req.TakeProfitPrices, i)
		legs = append(legs, storage.BracketLegRecord{
			Role:          "TP",
			TPIndex:       i + 1,
			ClientOrderID: tpID,
			Price:         price,
			Quantity:      req.Quantity,
			Status:        storage.LegStatusPlanned,
		})
	}
	legs = append(legs, storage.BracketLegRecord{
		Role:          "SL",
		ClientOrderID: req.ClientOrderIDs.StopLoss,
		StopPrice:     req.StopLossPrice,
		Quantity:      req.Quantity,
		Status:        storage.LegStatusPlanned,
	})

	requestHash, _ := canonicalBracketRequestHash(req)
	return storage.BracketRecord{
		Venue:              venue,
		IdempotencyKey:     req.IdempotencyKey,
		RequestHash:        requestHash,
		Symbol:             req.Symbol,
		Side:               req.Side,
		Quantity:           req.Quantity,
		EntryPrice:         req.EntryPrice,
		StopLossPrice:      req.StopLossPrice,
		EntryClientOrderID: req.ClientOrderIDs.Main,
		Status:             storage.BracketStatusReserved,
		LegsOnFill:         legsOnFill,
		Legs:               legs,
	}
}

type canonicalBracketRequest struct {
	Venue              string   `json:"venue"`
	Symbol             string   `json:"symbol"`
	Side               string   `json:"side"`
	Quantity           string   `json:"quantity"`
	EntryPrice         string   `json:"entry_price"`
	TakeProfitPrices   []string `json:"take_profit_prices"`
	StopLossPrice      string   `json:"stop_loss_price"`
	OrderType          string   `json:"order_type"`
	EntryClientOrderID string   `json:"entry_client_order_id"`
	TPClientOrderIDs   []string `json:"tp_client_order_ids"`
	SLClientOrderID    string   `json:"sl_client_order_id"`
}

func canonicalBracketRequestHash(req *PlaceBracketRequest) (string, error) {
	if req == nil || req.ClientOrderIDs == nil {
		return "", fmt.Errorf("idempotency identity is incomplete")
	}
	venue := "SPOT"
	if req.IsFutures {
		venue = "USD_M"
	}
	orderType := strings.ToUpper(strings.TrimSpace(req.OrderType))
	if orderType == "" {
		orderType = "LIMIT"
		if req.EntryPrice.IsZero() {
			orderType = "MARKET"
		}
	}
	tpPrices := make([]string, len(req.TakeProfitPrices))
	for index, price := range req.TakeProfitPrices {
		tpPrices[index] = price.String()
	}
	tpIDs := append([]string(nil), req.ClientOrderIDs.TakeProfits...)
	payload, err := json.Marshal(canonicalBracketRequest{
		Venue:              venue,
		Symbol:             strings.ToUpper(strings.TrimSpace(req.Symbol)),
		Side:               strings.ToUpper(strings.TrimSpace(req.Side)),
		Quantity:           req.Quantity.String(),
		EntryPrice:         req.EntryPrice.String(),
		TakeProfitPrices:   tpPrices,
		StopLossPrice:      req.StopLossPrice.String(),
		OrderType:          orderType,
		EntryClientOrderID: req.ClientOrderIDs.Main,
		TPClientOrderIDs:   tpIDs,
		SLClientOrderID:    req.ClientOrderIDs.StopLoss,
	})
	if err != nil {
		return "", fmt.Errorf("marshal canonical bracket request: %w", err)
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func tpPriceAt(prices []decimal.Decimal, i int) decimal.Decimal {
	if i < len(prices) {
		return prices[i]
	}
	return decimal.Zero
}

// validateReplayMatchesReservation fails closed when a retried request
// diverges from its durable reservation: with regenerated exit-leg ids the
// pre-crash legs would stay live while new-id legs place cleanly beside them.
func validateReplayMatchesReservation(rec *storage.BracketRecord, req *PlaceBracketRequest) error {
	requestHash, err := canonicalBracketRequestHash(req)
	if err != nil {
		return err
	}
	if rec.IdempotencyKey != "" && rec.IdempotencyKey != req.IdempotencyKey {
		return &IdempotencyConflictError{IdempotencyKey: req.IdempotencyKey}
	}
	if rec.RequestHash != "" && rec.RequestHash != requestHash {
		return &IdempotencyConflictError{IdempotencyKey: req.IdempotencyKey}
	}
	if rec.Symbol != req.Symbol || rec.Side != req.Side {
		return fmt.Errorf(
			"replayed request diverges from reservation %s: got %s/%s, reserved %s/%s",
			rec.EntryClientOrderID, req.Symbol, req.Side, rec.Symbol, rec.Side,
		)
	}
	if len(rec.Legs) == 0 {
		return nil
	}

	want := map[string]bool{
		req.ClientOrderIDs.Main:     true,
		req.ClientOrderIDs.StopLoss: true,
	}
	for _, tpID := range req.ClientOrderIDs.TakeProfits {
		want[tpID] = true
	}
	got := make(map[string]bool, len(rec.Legs))
	for _, leg := range rec.Legs {
		got[leg.ClientOrderID] = true
	}
	if !maps.Equal(want, got) {
		return fmt.Errorf(
			"replayed request diverges from reservation %s: leg client order ids differ",
			rec.EntryClientOrderID,
		)
	}
	return nil
}

type bracketLegExecutionUpdater interface {
	UpdateLegExecution(
		ctx context.Context,
		bracketID uuid.UUID,
		clientOrderID, status string,
		exchangeOrderID int64,
		averageFillPrice decimal.Decimal,
	) error
}

// replayEntryState checks the exchange for the reserved entry before a
// replayed placement: a live entry must be adopted, never re-POSTed (a
// filled-and-closed entry frees its client id and a blind re-POST would
// double-execute). Returns nil when the entry is confirmed not visible or
// is terminal with zero fills — placement may proceed reusing the same ids.
func (m *Manager) replayEntryState(
	ctx context.Context,
	client *binance.Client,
	symbol, entryClientOrderID string,
) (*binance.OrderResponse, error) {
	existing, err := queryWithRepoll(ctx, client, symbol, entryClientOrderID)
	if err != nil {
		if rest.IsOrderNotFound(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("replay: cannot verify entry %s: %w", entryClientOrderID, err)
	}

	switch existing.Status {
	case "CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH":
		if !existing.ExecutedQty.IsPositive() {
			m.logger.Warn().
				Str("symbol", symbol).
				Str("client_order_id", entryClientOrderID).
				Str("status", existing.Status).
				Msg("Replayed bracket's prior entry is dead; placing fresh")
			return nil, nil
		}
	}

	m.logger.Warn().
		Str("symbol", symbol).
		Str("client_order_id", entryClientOrderID).
		Str("status", existing.Status).
		Msg("Replayed bracket adopted live entry from exchange")
	return existing, nil
}

// persistPlacementOutcome records leg-level results after a placement pass.
func (m *Manager) persistPlacementOutcome(
	ctx context.Context,
	bracketID uuid.UUID,
	placement *bracketPlacementResult,
	critical bool,
	legsDeferred bool,
) error {
	if m.bracketStore == nil || bracketID == uuid.Nil {
		return nil
	}
	// Bookkeeping must survive a caller cancel/disconnect after the POSTs.
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()

	status := storage.BracketStatusFailed
	if !critical {
		status = storage.BracketStatusLegsPlaced
	}
	if !critical && legsDeferred {
		// Exit legs stay PLANNED; the armer places them on fill. A MARKET
		// entry can fill — and the armer can advance the bracket — before
		// this bookkeeping runs, so never downgrade past RESERVED.
		if _, err := m.bracketStore.UpdateBracketStatusIf(
			ctx, bracketID, storage.BracketStatusReserved, storage.BracketStatusEntryPlaced,
		); err != nil {
			return fmt.Errorf("persist bracket status: %w", err)
		}
	} else if err := m.bracketStore.UpdateBracketStatus(ctx, bracketID, status); err != nil {
		return fmt.Errorf("persist bracket status: %w", err)
	}
	if placement == nil {
		return nil
	}

	update := func(clientOrderID string, resp *binance.OrderResponse) error {
		if clientOrderID == "" {
			return nil
		}
		legStatus := storage.LegStatusFailed
		var exchangeID int64
		if resp != nil {
			switch normalizeOrderStatus(resp.Status) {
			case "FILLED":
				legStatus = storage.LegStatusFilled
			case "CANCELED", "CANCELLED":
				legStatus = storage.LegStatusCanceled
			case "EXPIRED", "EXPIRED_IN_MATCH":
				legStatus = storage.LegStatusExpired
			case "REJECTED":
				legStatus = storage.LegStatusFailed
			default:
				legStatus = storage.LegStatusPlaced
			}
			exchangeID = resp.OrderID
		}
		if resp != nil && (normalizeOrderStatus(resp.Status) == "PARTIALLY_FILLED" ||
			normalizeOrderStatus(resp.Status) == "FILLED" || resp.ExecutedQty.IsPositive()) {
			if updater, ok := m.bracketStore.(bracketLegExecutionProgressUpdater); ok {
				progressStatus := legStatus
				if normalizeOrderStatus(resp.Status) == "PARTIALLY_FILLED" {
					progressStatus = "PARTIALLY_FILLED"
				}
				if err := updater.UpdateLegExecutionProgress(
					ctx,
					bracketID,
					clientOrderID,
					progressStatus,
					exchangeID,
					resp.ExecutedQty,
					resp.AverageFillPrice,
					exchangeObservationTime(resp.TransactTime),
				); err != nil {
					return fmt.Errorf("persist bracket leg %s: %w", clientOrderID, err)
				}
				return nil
			}
			if normalizeOrderStatus(resp.Status) == "FILLED" {
				if updater, ok := m.bracketStore.(bracketLegExecutionUpdater); ok {
					if err := updater.UpdateLegExecution(
						ctx,
						bracketID,
						clientOrderID,
						legStatus,
						exchangeID,
						resp.AverageFillPrice,
					); err != nil {
						return fmt.Errorf("persist bracket leg %s: %w", clientOrderID, err)
					}
					return nil
				}
			}
		}
		if err := m.bracketStore.UpdateLegStatus(ctx, bracketID, clientOrderID, legStatus, exchangeID); err != nil {
			return fmt.Errorf("persist bracket leg %s: %w", clientOrderID, err)
		}
		return nil
	}

	if err := update(placement.IDs.Main, placement.Main); err != nil {
		return err
	}
	if legsDeferred {
		return nil
	}
	for i, tpID := range placement.IDs.TakeProfits {
		var resp *binance.OrderResponse
		if i < len(placement.TakeProfits) {
			resp = placement.TakeProfits[i]
		}
		if err := update(tpID, resp); err != nil {
			return err
		}
	}
	if err := update(placement.IDs.StopLoss, placement.StopLoss); err != nil {
		return err
	}
	return nil
}
