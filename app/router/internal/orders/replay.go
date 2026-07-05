package orders

import (
	"context"
	"fmt"
	"maps"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"router/internal/binance"
	"router/internal/rest"
	"router/internal/storage"
)

// bracketRecordFromRequest builds the durable reservation for a request that
// carries caller-supplied client order ids (the engine contract).
func bracketRecordFromRequest(req *PlaceBracketRequest) storage.BracketRecord {
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

	return storage.BracketRecord{
		Venue:              venue,
		Symbol:             req.Symbol,
		Side:               req.Side,
		Quantity:           req.Quantity,
		EntryPrice:         req.EntryPrice,
		StopLossPrice:      req.StopLossPrice,
		EntryClientOrderID: req.ClientOrderIDs.Main,
		Status:             storage.BracketStatusReserved,
		Legs:               legs,
	}
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

// persistPlacementOutcome records leg-level results after a placement pass;
// best-effort — trading must not block on bookkeeping.
func (m *Manager) persistPlacementOutcome(
	ctx context.Context,
	bracketID uuid.UUID,
	placement *bracketPlacementResult,
	critical bool,
) {
	if m.bracketStore == nil || bracketID == uuid.Nil {
		return
	}
	// Bookkeeping must survive a caller cancel/disconnect after the POSTs.
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
	defer cancel()

	status := storage.BracketStatusFailed
	if !critical {
		status = storage.BracketStatusLegsPlaced
	}
	if err := m.bracketStore.UpdateBracketStatus(ctx, bracketID, status); err != nil {
		m.logger.Warn().Err(err).Str("bracket_id", bracketID.String()).
			Msg("Failed to persist bracket status")
	}
	if placement == nil {
		return
	}

	update := func(clientOrderID string, resp *binance.OrderResponse) {
		if clientOrderID == "" {
			return
		}
		legStatus := storage.LegStatusFailed
		var exchangeID int64
		if resp != nil {
			legStatus = storage.LegStatusPlaced
			exchangeID = resp.OrderID
		}
		if err := m.bracketStore.UpdateLegStatus(ctx, bracketID, clientOrderID, legStatus, exchangeID); err != nil {
			m.logger.Warn().Err(err).Str("client_order_id", clientOrderID).
				Msg("Failed to persist bracket leg status")
		}
	}

	update(placement.IDs.Main, placement.Main)
	for i, tpID := range placement.IDs.TakeProfits {
		var resp *binance.OrderResponse
		if i < len(placement.TakeProfits) {
			resp = placement.TakeProfits[i]
		}
		update(tpID, resp)
	}
	update(placement.IDs.StopLoss, placement.StopLoss)
}
