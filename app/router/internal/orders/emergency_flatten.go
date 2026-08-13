package orders

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/shopspring/decimal"
	"router/internal/binance"
	"router/internal/rest"
)

type EmergencyConfig struct {
	SpotQuoteAssets []string
	ProtectedAssets []string
	DustMaxUSDT     decimal.Decimal
	FillTimeout     time.Duration
	MaxPasses       int
}

func defaultEmergencyConfig() EmergencyConfig {
	return EmergencyConfig{
		SpotQuoteAssets: []string{"USDT"},
		ProtectedAssets: []string{"USDT", "USDC", "FDUSD", "BUSD"},
		DustMaxUSDT:     decimal.NewFromInt(1),
		FillTimeout:     30 * time.Second,
		MaxPasses:       3,
	}
}

func (m *Manager) SetEmergencyConfig(config EmergencyConfig) {
	if config.MaxPasses <= 0 {
		config.MaxPasses = 3
	}
	if config.FillTimeout <= 0 {
		config.FillTimeout = 30 * time.Second
	}
	m.emergencyConfig = config
}

func (m *Manager) EmergencyFlatten(
	ctx context.Context,
	request *EmergencyFlattenRequest,
) (*EmergencyFlattenResponse, error) {
	if request == nil {
		return nil, fmt.Errorf("request is required")
	}
	if request.Scope != EmergencyScopeAll && request.Scope != EmergencyScopeSpot && request.Scope != EmergencyScopeFutures {
		return nil, fmt.Errorf("invalid scope: %s", request.Scope)
	}
	if strings.TrimSpace(request.IdempotencyKey) == "" {
		return nil, fmt.Errorf("idempotency_key is required")
	}
	if m.executionGate == nil {
		return nil, &ExecutionDurabilityError{Cause: fmt.Errorf("execution control is not configured")}
	}
	state, release, err := m.executionGate.AcquireEmergency(ctx)
	if err != nil {
		return nil, &ExecutionDurabilityError{Cause: fmt.Errorf("acquire emergency control fence: %w", err)}
	}
	if release == nil {
		return nil, &ExecutionDurabilityError{Cause: fmt.Errorf("emergency control fence has no release")}
	}
	if state != "HALTED" {
		if releaseErr := release(); releaseErr != nil {
			return nil, &ExecutionDurabilityError{Cause: fmt.Errorf("release emergency control fence: %w", releaseErr)}
		}
		return nil, ErrExecutionNotHalted
	}
	if (request.Scope == EmergencyScopeAll || request.Scope == EmergencyScopeSpot) && m.spotClient == nil {
		_ = release()
		return nil, fmt.Errorf("spot exchange client is not configured for emergency scope %s", request.Scope)
	}
	if (request.Scope == EmergencyScopeAll || request.Scope == EmergencyScopeFutures) && m.futuresClient == nil {
		_ = release()
		return nil, fmt.Errorf("futures exchange client is not configured for emergency scope %s", request.Scope)
	}

	response := &EmergencyFlattenResponse{
		Scope: request.Scope, IdempotencyKey: request.IdempotencyKey,
	}
	response.Starting = m.captureEmergencyState(ctx, request.Scope)
	response.Errors = append(response.Errors, response.Starting.Errors...)

	for pass := 1; pass <= m.emergencyConfig.MaxPasses; pass++ {
		response.Passes = pass
		state := m.captureEmergencyState(ctx, request.Scope)
		response.Errors = append(response.Errors, state.Errors...)
		if len(state.Errors) > 0 {
			break
		}

		for _, order := range state.OpenOrders {
			if order.Kind == "EXIT" {
				continue
			}
			if err := m.cancelEmergencyOrder(ctx, order); err != nil {
				response.Errors = append(response.Errors, err.Error())
				continue
			}
			response.CanceledOrders++
		}

		if request.Scope == EmergencyScopeAll || request.Scope == EmergencyScopeFutures {
			if m.futuresClient != nil {
				account, err := m.futuresAccount(ctx)
				if err != nil {
					response.Errors = append(response.Errors, err.Error())
					continue
				}
				for _, position := range account {
					side := "SELL"
					if position.Quantity.IsNegative() {
						side = "BUY"
					}
					positionSide := strings.ToUpper(position.PositionSide)
					reduceOnly := positionSide == "" || positionSide == "BOTH"
					placementCtx, cancel := context.WithTimeout(ctx, m.emergencyConfig.FillTimeout)
					clientOrderID := emergencyClientOrderID(
						request.IdempotencyKey, "fut", position.Symbol+":"+positionSide,
					)
					placed, placeErr := m.futuresClient.PlaceFuturesOrder(placementCtx, binance.FuturesOrderRequest{
						Symbol: position.Symbol, Side: side, Type: "MARKET",
						Quantity: position.Quantity.Abs(), ReduceOnly: reduceOnly,
						PositionSide:     positionSide,
						NewClientOrderID: clientOrderID,
					})
					cancel()
					resolutionCtx, resolutionCancel := context.WithTimeout(ctx, m.emergencyConfig.FillTimeout)
					placeErr = resolveEmergencyPlacement(
						resolutionCtx, m.futuresClient, position.Symbol, clientOrderID, placed, placeErr,
					)
					resolutionCancel()
					if placeErr != nil {
						response.Errors = append(response.Errors, fmt.Sprintf("%s: close futures position: %v", position.Symbol, placeErr))
						continue
					}
					response.ClosedFuturesPositions++
				}
			}
		}

		if request.Scope == EmergencyScopeAll || request.Scope == EmergencyScopeSpot {
			spotState := m.captureSpotState(ctx)
			response.Errors = append(response.Errors, spotState.Errors...)
			for _, balance := range spotState.SpotBalances {
				if balance.Dust || balance.Symbol == "" {
					continue
				}
				currentOrders, listErr := m.spotClient.GetAllOpenOrders(ctx)
				if listErr != nil {
					response.Errors = append(response.Errors, fmt.Sprintf("%s: list protective orders: %v", balance.Asset, listErr))
					continue
				}
				protectiveGroups := groupSpotProtectiveOrders(currentOrders, balance.Symbol)
				canceledProtection, canceledCount, cancelErr := m.cancelSpotProtection(
					ctx, protectiveGroups,
				)
				response.CanceledOrders += canceledCount
				if cancelErr != nil {
					response.Errors = append(response.Errors, fmt.Sprintf("%s: unlock protected balance: %v", balance.Asset, cancelErr))
					response.Errors = append(response.Errors, m.restoreSpotProtection(
						ctx, request.IdempotencyKey, balance, canceledProtection,
					)...)
					continue
				}
				fresh, freshErr := m.spotClient.GetAccountInfoFresh(ctx)
				if freshErr != nil {
					response.Errors = append(response.Errors, fmt.Sprintf("%s: refresh balance: %v", balance.Asset, freshErr))
					response.Errors = append(response.Errors, m.restoreSpotProtection(
						ctx, request.IdempotencyKey, balance, canceledProtection,
					)...)
					continue
				}
				quantity := availableAssetQuantity(fresh, balance.Asset)
				rounded, roundErr := m.spotClient.RoundQuantity(ctx, balance.Symbol, quantity)
				if roundErr != nil || rounded.IsZero() {
					response.Errors = append(response.Errors, fmt.Sprintf("%s: round emergency quantity: %v", balance.Asset, roundErr))
					response.Errors = append(response.Errors, m.restoreSpotProtection(
						ctx, request.IdempotencyKey, balance, canceledProtection,
					)...)
					continue
				}
				placementCtx, cancel := context.WithTimeout(ctx, m.emergencyConfig.FillTimeout)
				clientOrderID := emergencyClientOrderID(request.IdempotencyKey, "spot", balance.Asset)
				placed, placeErr := m.spotClient.PlaceSpotOrder(placementCtx, binance.SpotOrderRequest{
					Symbol: balance.Symbol, Side: "SELL", Type: "MARKET", Quantity: rounded,
					NewClientOrderID: clientOrderID,
				})
				cancel()
				resolutionCtx, resolutionCancel := context.WithTimeout(ctx, m.emergencyConfig.FillTimeout)
				placeErr = resolveEmergencyPlacement(
					resolutionCtx, m.spotClient, balance.Symbol, clientOrderID, placed, placeErr,
				)
				resolutionCancel()
				if placeErr != nil {
					response.Errors = append(response.Errors, fmt.Sprintf("%s: flatten spot balance: %v", balance.Asset, placeErr))
					response.Errors = append(response.Errors, m.restoreSpotProtection(
						ctx, request.IdempotencyKey, balance, canceledProtection,
					)...)
					continue
				}
				response.FlattenedSpotAssets++
			}
		}

		remaining := m.captureEmergencyState(ctx, request.Scope)
		response.Errors = append(response.Errors, remaining.Errors...)
		for _, order := range remaining.OpenOrders {
			if order.Kind == "EXIT" && emergencyStateHasExposure(remaining, order) {
				continue
			}
			if err := m.cancelEmergencyOrder(ctx, order); err != nil {
				response.Errors = append(response.Errors, err.Error())
				continue
			}
			response.CanceledOrders++
		}

		response.Final = m.captureEmergencyState(ctx, request.Scope)
		if emergencyStateIsFlat(response.Final) {
			break
		}
	}

	response.Final = m.captureEmergencyState(ctx, request.Scope)
	response.Residuals = append(response.Residuals, response.Final.SpotBalances...)
	response.Errors = append(response.Errors, response.Final.Errors...)
	response.FullyFlattened = emergencyStateIsFlat(response.Final)
	if releaseErr := release(); releaseErr != nil {
		return response, &ExecutionDurabilityError{Cause: fmt.Errorf("release emergency control fence: %w", releaseErr)}
	}
	return response, nil
}

func emergencyStateHasExposure(state EmergencyExchangeState, order EmergencyOpenOrder) bool {
	if order.Venue == "USD_M" {
		for _, position := range state.FuturesPositions {
			if position.Symbol != order.Symbol || position.Quantity.IsZero() {
				continue
			}
			orderPositionSide := strings.ToUpper(order.PositionSide)
			if orderPositionSide == "" || orderPositionSide == "BOTH" ||
				strings.EqualFold(position.PositionSide, orderPositionSide) {
				return true
			}
		}
		return false
	}
	for _, balance := range state.SpotBalances {
		if balance.Symbol == order.Symbol && !balance.Dust {
			return true
		}
	}
	return false
}

func groupSpotProtectiveOrders(orders []*binance.Order, symbol string) [][]*binance.Order {
	groups := make([][]*binance.Order, 0)
	listIndexes := make(map[int64]int)
	for _, order := range orders {
		if order.Symbol != symbol || emergencyOrderKind("SPOT", order, nil) != "EXIT" {
			continue
		}
		if order.OrderListID > 0 {
			if index, ok := listIndexes[order.OrderListID]; ok {
				groups[index] = append(groups[index], order)
				continue
			}
			listIndexes[order.OrderListID] = len(groups)
		}
		groups = append(groups, []*binance.Order{order})
	}
	return groups
}

func (m *Manager) cancelSpotProtection(
	ctx context.Context,
	groups [][]*binance.Order,
) (canceled [][]*binance.Order, canceledCount int, err error) {
	for _, group := range groups {
		if len(group) == 0 {
			continue
		}
		order := group[0]
		if _, cancelErr := m.spotClient.CancelOrder(ctx, order.Symbol, order.OrderID); cancelErr != nil {
			openOrders, queryErr := m.spotClient.GetAllOpenOrders(ctx)
			if queryErr != nil {
				canceled = append(canceled, group)
				return canceled, canceledCount, fmt.Errorf(
					"cancel protective order %d: %w; resolve cancellation: %v",
					order.OrderID, cancelErr, queryErr,
				)
			}
			stillOpen := false
			for _, candidate := range openOrders {
				for _, member := range group {
					if candidate.OrderID == member.OrderID ||
						(candidate.ClientOrderID != "" && candidate.ClientOrderID == member.ClientOrderID) {
						stillOpen = true
						break
					}
				}
				if stillOpen {
					break
				}
			}
			if stillOpen {
				return canceled, canceledCount, fmt.Errorf("cancel protective order %d: %w", order.OrderID, cancelErr)
			}
		}
		canceled = append(canceled, group)
		canceledCount += len(group)
	}
	return canceled, canceledCount, nil
}

func (m *Manager) restoreSpotProtection(
	ctx context.Context,
	idempotencyKey string,
	balance EmergencySpotBalance,
	groups [][]*binance.Order,
) []string {
	if len(groups) == 0 {
		return nil
	}
	account, err := m.spotClient.GetAccountInfoFresh(ctx)
	if err != nil {
		return []string{fmt.Sprintf("%s: refresh balance before restoring protection: %v", balance.Asset, err)}
	}
	remaining := availableAssetQuantity(account, balance.Asset)
	errorsFound := make([]string, 0)
	for _, group := range groups {
		if !remaining.IsPositive() || len(group) == 0 {
			break
		}
		quantity := group[0].OrigQty.Sub(group[0].ExecutedQty)
		if quantity.GreaterThan(remaining) {
			quantity = remaining
		}
		quantity, err = m.spotClient.RoundQuantity(ctx, balance.Symbol, quantity)
		if err != nil || !quantity.IsPositive() {
			errorsFound = append(errorsFound, fmt.Sprintf("%s: round restored protection: %v", balance.Asset, err))
			continue
		}
		groupKey := fmt.Sprintf("%s:%d", balance.Symbol, group[0].OrderID)
		if group[0].OrderListID > 0 {
			groupKey = fmt.Sprintf("%s:list:%d", balance.Symbol, group[0].OrderListID)
		}
		if restoreErr := m.restoreSpotProtectionGroup(
			ctx, idempotencyKey, groupKey, group, quantity,
		); restoreErr != nil {
			errorsFound = append(errorsFound, fmt.Sprintf("%s: restore protection: %v", balance.Asset, restoreErr))
			continue
		}
		remaining = remaining.Sub(quantity)
	}
	return errorsFound
}

func (m *Manager) restoreSpotProtectionGroup(
	ctx context.Context,
	idempotencyKey string,
	groupKey string,
	group []*binance.Order,
	quantity decimal.Decimal,
) error {
	if len(group) > 1 && group[0].OrderListID > 0 {
		var takeProfit, stop *binance.Order
		for _, order := range group {
			if strings.Contains(strings.ToUpper(order.Type), "STOP_LOSS") {
				stop = order
			} else {
				takeProfit = order
			}
		}
		if takeProfit == nil || stop == nil {
			return fmt.Errorf("OCO protection is missing a take-profit or stop leg")
		}
		price := takeProfit.Price
		priceLimit := decimal.Zero
		if strings.Contains(strings.ToUpper(takeProfit.Type), "TAKE_PROFIT") {
			price = takeProfit.StopPrice
			priceLimit = takeProfit.Price
		}
		listID := emergencyClientOrderID(idempotencyKey, "restore-list", groupKey)
		restoreCtx, cancel := context.WithTimeout(ctx, m.emergencyConfig.FillTimeout)
		defer cancel()
		response, placeErr := m.spotClient.PlaceSpotOCO(restoreCtx, rest.OCORequest{
			Symbol: group[0].Symbol, Side: group[0].Side, Quantity: quantity,
			Price: price, PriceLimit: priceLimit, StopPrice: stop.StopPrice,
			StopLimitPrice: stop.Price, ListClientOrderID: listID,
			LimitClientOrderID: emergencyClientOrderID(idempotencyKey, "restore-tp", groupKey),
			StopClientOrderID:  emergencyClientOrderID(idempotencyKey, "restore-sl", groupKey),
		})
		if placeErr != nil && isEmergencyPlacementAmbiguous(placeErr) {
			response, placeErr = m.spotClient.GetOCOByListClientOrderID(restoreCtx, listID)
		}
		if placeErr != nil {
			return placeErr
		}
		if response == nil {
			return fmt.Errorf("restored OCO response is unavailable")
		}
		for _, report := range response.OrderReports {
			if isWorkingOrderStatus(report.Status) {
				return nil
			}
		}
		return fmt.Errorf("restored OCO has no working leg")
	}

	original := group[0]
	clientOrderID := emergencyClientOrderID(idempotencyKey, "restore", groupKey)
	response, err := submitResolvingAmbiguity(
		ctx, m.logger, m.spotClient, original.Symbol, clientOrderID, false,
		func(ctx context.Context) (*binance.OrderResponse, error) {
			return m.spotClient.PlaceSpotOrder(ctx, binance.SpotOrderRequest{
				Symbol: original.Symbol, Side: original.Side, Type: original.Type,
				Quantity: quantity, Price: original.Price, StopPrice: original.StopPrice,
				TimeInForce: original.TimeInForce, NewClientOrderID: clientOrderID,
			})
		},
	)
	if err != nil {
		return err
	}
	if response == nil {
		return fmt.Errorf("restored order response is unavailable")
	}
	if !isWorkingOrderStatus(response.Status) {
		return fmt.Errorf("restored order ended in %s", response.Status)
	}
	return nil
}

func isWorkingOrderStatus(status string) bool {
	switch strings.ToUpper(status) {
	case "NEW", "PARTIALLY_FILLED", "PENDING_NEW":
		return true
	default:
		return false
	}
}

func (m *Manager) captureEmergencyState(ctx context.Context, scope EmergencyScope) EmergencyExchangeState {
	state := EmergencyExchangeState{}
	if scope == EmergencyScopeAll || scope == EmergencyScopeSpot {
		spot := m.captureSpotState(ctx)
		state.SpotBalances = spot.SpotBalances
		state.Errors = append(state.Errors, spot.Errors...)
		if m.spotClient != nil {
			orders, err := m.spotClient.GetAllOpenOrders(ctx)
			if err != nil {
				state.Errors = append(state.Errors, fmt.Sprintf("list all spot orders: %v", err))
			} else {
				state.OpenOrders = appendEmergencyOrders(state.OpenOrders, "SPOT", orders, nil)
			}
		}
	}
	if scope == EmergencyScopeAll || scope == EmergencyScopeFutures {
		if m.futuresClient != nil {
			if positions, err := m.futuresAccount(ctx); err != nil {
				state.Errors = append(state.Errors, err.Error())
			} else {
				state.FuturesPositions = positions
			}
			if orders, err := m.futuresClient.GetAllOpenOrders(ctx); err != nil {
				state.Errors = append(state.Errors, fmt.Sprintf("list all futures orders: %v", err))
			} else {
				state.OpenOrders = appendEmergencyOrders(state.OpenOrders, "USD_M", orders, state.FuturesPositions)
			}
		}
	}
	return state
}

func (m *Manager) captureSpotState(ctx context.Context) EmergencyExchangeState {
	state := EmergencyExchangeState{}
	if m.spotClient == nil {
		return state
	}
	account, err := m.spotClient.GetAccountInfoFresh(ctx)
	if err != nil {
		state.Errors = append(state.Errors, fmt.Sprintf("get fresh spot balances: %v", err))
		return state
	}
	symbols, err := m.spotClient.GetSpotSymbolsFresh(ctx)
	if err != nil {
		state.Errors = append(state.Errors, fmt.Sprintf("get fresh spot symbols: %v", err))
		return state
	}
	prices, err := m.spotClient.GetTickerPrices(ctx)
	if err != nil {
		state.Errors = append(state.Errors, fmt.Sprintf("get fresh spot prices: %v", err))
		return state
	}
	protected := stringSet(m.emergencyConfig.ProtectedAssets)
	quotes := stringSet(m.emergencyConfig.SpotQuoteAssets)
	for _, balance := range account.Balances {
		quantity := balance.Free.Add(balance.Locked)
		if quantity.LessThanOrEqual(decimal.Zero) || protected[balance.Asset] || quotes[balance.Asset] {
			continue
		}
		spotBalance := EmergencySpotBalance{Asset: balance.Asset, Quantity: quantity}
		for _, symbol := range symbols {
			if symbol.BaseAsset != balance.Asset || !quotes[symbol.QuoteAsset] {
				continue
			}
			price, ok := prices[symbol.Symbol]
			if !ok {
				continue
			}
			spotBalance.Symbol = symbol.Symbol
			spotBalance.NotionalUSDT = quantity.Mul(price)
			break
		}
		spotBalance.Dust = spotBalance.Symbol != "" && spotBalance.NotionalUSDT.LessThanOrEqual(m.emergencyConfig.DustMaxUSDT)
		state.SpotBalances = append(state.SpotBalances, spotBalance)
	}
	return state
}

func (m *Manager) futuresAccount(ctx context.Context) ([]EmergencyFuturesPosition, error) {
	if m.futuresClient == nil {
		return nil, fmt.Errorf("futures client not configured")
	}
	account, err := m.futuresClient.GetFuturesAccountInfo(ctx)
	if err != nil {
		return nil, fmt.Errorf("get fresh futures positions: %w", err)
	}
	positions := make([]EmergencyFuturesPosition, 0)
	for _, position := range account.Positions {
		if !position.PositionAmt.IsZero() {
			positions = append(positions, EmergencyFuturesPosition{
				Symbol: position.Symbol, Quantity: position.PositionAmt, PositionSide: position.PositionSide,
			})
		}
	}
	return positions, nil
}

func (m *Manager) cancelEmergencyOrder(ctx context.Context, order EmergencyOpenOrder) error {
	client := m.spotClient
	if order.Venue == "USD_M" {
		client = m.futuresClient
	}
	if client == nil {
		return fmt.Errorf("%s %s: client not configured", order.Venue, order.Symbol)
	}
	if _, err := client.CancelOrder(ctx, order.Symbol, order.OrderID); err != nil {
		return fmt.Errorf("%s %s order %d: cancel: %w", order.Venue, order.Symbol, order.OrderID, err)
	}
	return nil
}

func appendEmergencyOrders(
	target []EmergencyOpenOrder,
	venue string,
	orders []*binance.Order,
	positions []EmergencyFuturesPosition,
) []EmergencyOpenOrder {
	for _, order := range orders {
		target = append(target, EmergencyOpenOrder{
			Venue: venue, Symbol: order.Symbol, OrderID: order.OrderID,
			ClientOrderID: order.ClientOrderID, PositionSide: order.PositionSide,
			Kind: emergencyOrderKind(venue, order, positions),
		})
	}
	return target
}

func emergencyOrderKind(venue string, order *binance.Order, positions []EmergencyFuturesPosition) string {
	if venue == "SPOT" {
		if strings.EqualFold(order.Side, "SELL") {
			return "EXIT"
		}
		return "ENTRY"
	}
	if order.ReduceOnly || order.ClosePosition {
		return "EXIT"
	}
	for _, position := range positions {
		if position.Symbol != order.Symbol || position.Quantity.IsZero() {
			continue
		}
		positionSide := strings.ToUpper(position.PositionSide)
		orderPositionSide := strings.ToUpper(order.PositionSide)
		if orderPositionSide != "" && orderPositionSide != "BOTH" && positionSide != orderPositionSide {
			continue
		}
		side := strings.ToUpper(order.Side)
		if (positionSide == "LONG" && side == "SELL") ||
			(positionSide == "SHORT" && side == "BUY") ||
			((positionSide == "" || positionSide == "BOTH") &&
				((position.Quantity.IsPositive() && side == "SELL") ||
					(position.Quantity.IsNegative() && side == "BUY"))) {
			return "EXIT"
		}
	}
	return "ENTRY"
}

func emergencyStateIsFlat(state EmergencyExchangeState) bool {
	if len(state.Errors) > 0 || len(state.OpenOrders) > 0 || len(state.FuturesPositions) > 0 {
		return false
	}
	for _, balance := range state.SpotBalances {
		if !balance.Dust {
			return false
		}
	}
	return true
}

func waitForEmergencyFill(
	ctx context.Context,
	client *binance.Client,
	order *binance.OrderResponse,
) error {
	if client == nil || order == nil {
		return fmt.Errorf("emergency order response is unavailable")
	}
	for {
		switch strings.ToUpper(order.Status) {
		case "FILLED":
			return nil
		case "CANCELED", "CANCELLED", "REJECTED", "EXPIRED":
			return fmt.Errorf("emergency order %s ended in %s", order.ClientOrderID, order.Status)
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("wait for emergency order %s fill: %w", order.ClientOrderID, ctx.Err())
		case <-time.After(100 * time.Millisecond):
		}
		current, err := client.GetOrderByClientID(ctx, order.Symbol, order.ClientOrderID)
		if err != nil {
			if ctx.Err() != nil {
				return fmt.Errorf("wait for emergency order %s fill: %w", order.ClientOrderID, ctx.Err())
			}
			continue
		}
		order = current
	}
}

func resolveEmergencyPlacement(
	ctx context.Context,
	client *binance.Client,
	symbol string,
	clientOrderID string,
	order *binance.OrderResponse,
	placeErr error,
) error {
	if placeErr != nil {
		if !isEmergencyPlacementAmbiguous(placeErr) {
			return placeErr
		}
		var resolveErr error
		for {
			resolved, err := client.GetOrderByClientID(ctx, symbol, clientOrderID)
			if err == nil {
				order = resolved
				break
			}
			resolveErr = err
			select {
			case <-ctx.Done():
				return fmt.Errorf(
					"submission outcome unknown for %s: place=%v query=%v: %w",
					clientOrderID, placeErr, resolveErr, ctx.Err(),
				)
			case <-time.After(25 * time.Millisecond):
			}
		}
	}
	return waitForEmergencyFill(ctx, client, order)
}

func isEmergencyPlacementAmbiguous(err error) bool {
	if errors.Is(err, rest.ErrAmbiguousSubmit) || rest.IsDuplicateClientOrderID(err) {
		return true
	}
	var binanceErr *rest.BinanceError
	return errors.As(err, &binanceErr) && (binanceErr.Code == -1006 || binanceErr.Code == -1007)
}

func availableAssetQuantity(account *binance.AccountResponse, asset string) decimal.Decimal {
	for _, balance := range account.Balances {
		if balance.Asset == asset {
			return balance.Free
		}
	}
	return decimal.Zero
}

func emergencyClientOrderID(key, kind, symbol string) string {
	digest := sha256.Sum256([]byte(fmt.Sprintf("%s\x00%s\x00%s", key, kind, symbol)))
	return "emg_" + hex.EncodeToString(digest[:])[:24]
}

func stringSet(values []string) map[string]bool {
	set := make(map[string]bool, len(values))
	for _, value := range values {
		set[strings.ToUpper(strings.TrimSpace(value))] = true
	}
	return set
}
