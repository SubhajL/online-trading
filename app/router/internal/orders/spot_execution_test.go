package orders

import (
	"context"
	"fmt"
	"sync"
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
