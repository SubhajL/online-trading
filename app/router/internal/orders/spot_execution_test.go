package orders

import (
	"context"
	"fmt"
	"sync"

	"github.com/shopspring/decimal"
)

type fakeSpotExecutionLedger struct {
	mu        sync.Mutex
	called    bool
	snapshots []SpotExecutionSnapshot
	err       error
}

func (f *fakeSpotExecutionLedger) PersistSpotExecution(ctx context.Context, snapshot SpotExecutionSnapshot) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.called = true
	f.snapshots = append(f.snapshots, snapshot)
	return f.err
}

func (f *fakeSpotExecutionLedger) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.snapshots)
}

func (f *fakeSpotExecutionLedger) latestSnapshot() SpotExecutionSnapshot {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.snapshots[len(f.snapshots)-1]
}

func mustSpotExecutionTrade(
	tradeID int64,
	price string,
	quantity string,
	commission string,
	commissionAsset string,
) SpotExecutionTrade {
	return SpotExecutionTrade{
		TradeID:         tradeID,
		Price:           decimal.RequireFromString(price),
		Quantity:        decimal.RequireFromString(quantity),
		Commission:      decimal.RequireFromString(commission),
		CommissionAsset: commissionAsset,
	}
}

type flakySpotExecutionLedger struct {
	mu                sync.Mutex
	remainingFailures int
	snapshots         []SpotExecutionSnapshot
}

func (f *flakySpotExecutionLedger) PersistSpotExecution(ctx context.Context, snapshot SpotExecutionSnapshot) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.snapshots = append(f.snapshots, snapshot)
	if f.remainingFailures > 0 {
		f.remainingFailures--
		return fmt.Errorf("transient persistence failure")
	}
	return nil
}

func (f *flakySpotExecutionLedger) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.snapshots)
}
