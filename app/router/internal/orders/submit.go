package orders

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/rs/zerolog"

	"router/internal/binance"
	"router/internal/rest"
)

// Repoll settings for orders that are not yet visible after an ambiguous
// submit; overridable in tests.
var (
	ambiguityRepollDelay         = 500 * time.Millisecond
	ambiguityRepollAttempts      = 2
	errAdoptedOrderDead          = errors.New("adopted order is terminal with no fills")
	errRetryDisallowedForInstant = errors.New("retry disallowed for instantly-executable order")
)

// submitResolvingAmbiguity wraps an order POST so ambiguous or duplicate
// outcomes are resolved against the exchange instead of guessed at.
//
// A -2013 not-found after an ambiguous submit is NOT proof the POST never
// landed (degraded exchanges can execute after our timeout, and freshly
// accepted orders can lag the query path), so the order is re-polled before
// any retry, and orders that can execute instantly (allowRetry=false, e.g.
// MARKET) are never re-POSTed. Anything unresolved fails closed with the
// original error.
func submitResolvingAmbiguity(
	ctx context.Context,
	logger zerolog.Logger,
	client *binance.Client,
	symbol string,
	clientOrderID string,
	allowRetry bool,
	post func(context.Context) (*binance.OrderResponse, error),
) (*binance.OrderResponse, error) {
	resp, err := post(ctx)
	if err == nil {
		return resp, nil
	}

	ambiguous := errors.Is(err, rest.ErrAmbiguousSubmit)
	duplicate := rest.IsDuplicateClientOrderID(err)
	if !ambiguous && !duplicate {
		return nil, err
	}

	adopted, queryErr := queryWithRepoll(ctx, client, symbol, clientOrderID)
	if queryErr == nil {
		return adoptExisting(logger, symbol, clientOrderID, duplicate, adopted, err)
	}
	if !rest.IsOrderNotFound(queryErr) {
		return nil, fmt.Errorf(
			"unresolved submit for %s (query failed: %v): %w",
			clientOrderID, queryErr, err,
		)
	}
	if duplicate {
		// The exchange claims the id is a duplicate yet the order is not
		// visible: unresolved, fail closed.
		return nil, fmt.Errorf(
			"duplicate submit for %s but order not found: %w",
			clientOrderID, err,
		)
	}
	if !allowRetry {
		return nil, fmt.Errorf(
			"%v for %s: %w",
			errRetryDisallowedForInstant, clientOrderID, err,
		)
	}

	logger.Warn().
		Str("symbol", symbol).
		Str("client_order_id", clientOrderID).
		Msg("Ambiguous submit not visible on exchange; re-POSTing once")
	retryResp, retryErr := post(ctx)
	if retryErr == nil {
		return retryResp, nil
	}
	if rest.IsDuplicateClientOrderID(retryErr) {
		readopted, adoptErr := client.GetOrderByClientID(ctx, symbol, clientOrderID)
		if adoptErr == nil {
			return adoptExisting(logger, symbol, clientOrderID, true, readopted, retryErr)
		}
		return nil, fmt.Errorf(
			"unresolved submit retry for %s (query failed: %v): %w",
			clientOrderID, adoptErr, retryErr,
		)
	}
	return nil, retryErr
}

// queryWithRepoll looks the order up by client id, re-polling on -2013 to
// bridge the exchange's post-accept visibility lag.
func queryWithRepoll(
	ctx context.Context,
	client *binance.Client,
	symbol, clientOrderID string,
) (*binance.OrderResponse, error) {
	adopted, queryErr := client.GetOrderByClientID(ctx, symbol, clientOrderID)
	for attempt := 0; attempt < ambiguityRepollAttempts && queryErr != nil; attempt++ {
		if !rest.IsOrderNotFound(queryErr) || ctx.Err() != nil {
			break
		}
		time.Sleep(ambiguityRepollDelay)
		adopted, queryErr = client.GetOrderByClientID(ctx, symbol, clientOrderID)
	}
	return adopted, queryErr
}

// adoptExisting accepts the exchange's state for an order we could not
// confirm submitting, refusing terminal orders that never traded.
func adoptExisting(
	logger zerolog.Logger,
	symbol, clientOrderID string,
	wasDuplicate bool,
	existing *binance.OrderResponse,
	originalErr error,
) (*binance.OrderResponse, error) {
	switch existing.Status {
	case "CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH":
		if !existing.ExecutedQty.IsPositive() {
			return nil, fmt.Errorf(
				"%v (status=%s) for %s: %w",
				errAdoptedOrderDead, existing.Status, clientOrderID, originalErr,
			)
		}
	}

	logger.Warn().
		Str("symbol", symbol).
		Str("client_order_id", clientOrderID).
		Str("status", existing.Status).
		Bool("was_duplicate", wasDuplicate).
		Msg("Adopted exchange state for unresolved order submit")
	return existing, nil
}
