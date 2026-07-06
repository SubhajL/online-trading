package orders

import (
	"context"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"router/internal/storage"
)

type fakeWatcherStore struct {
	fakeArmerStore
}

func (f *fakeWatcherStore) LoadOpenBrackets(_ context.Context, _ time.Duration) ([]storage.BracketRecord, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.record == nil {
		return nil, nil
	}
	rec := *f.record
	rec.Legs = append([]storage.BracketLegRecord(nil), f.record.Legs...)
	return []storage.BracketRecord{rec}, nil
}

func newWatcherFixture(t *testing.T, fake *spotOCOExchange, store *fakeWatcherStore) *EntryFillWatcher {
	t.Helper()
	spotArmer, spotClient := newSpotArmerFixture(t, fake, &store.fakeArmerStore)
	return NewEntryFillWatcher(
		store, spotClient, spotArmer, nil, nil,
		time.Millisecond, time.Hour, zerolog.Nop(),
	)
}

func TestEntryFillWatcher_ArmsSpotBracketWhenEntryFills(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	require.Len(t, fake.requests(), 1, "filled entry must arm the OCO pair")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

func TestEntryFillWatcher_WaitsWhileEntryInvisibleOrOpen(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{getStatuses: []string{"NOT_FOUND", "NEW"}}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background()) // -2013: not visible yet
	watcher.pollOnce(context.Background()) // NEW: resting, no fill

	assert.Empty(t, fake.requests())
	assert.Empty(t, store.bracketUpdates)
}

func TestEntryFillWatcher_ReleasesDeadEntryBracket(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{getStatuses: []string{"CANCELED"}, getOrderQty: "0"}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	assert.Empty(t, fake.requests())
	assert.Contains(t, store.legUpdates, "arm-tp1:CANCELED")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusClosed)
}

func TestEntryFillWatcher_ArmsPartialFillOnCanceledEntry(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{getStatuses: []string{"CANCELED"}, getOrderQty: "0.01"}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	requests := fake.requests()
	require.Len(t, requests, 1, "a partial position must still be protected")
	assert.Equal(t, "0.01", requests[0].Get("quantity"))
}

func TestEntryFillWatcher_SkipsSynchronousAndSettledBrackets(t *testing.T) {
	syncRecord := spotArmerRecord()
	syncRecord.LegsOnFill = false
	store := &fakeWatcherStore{fakeArmerStore{record: syncRecord}}
	fake := &spotOCOExchange{}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	settled := spotArmerRecord()
	settled.Status = storage.BracketStatusClosed
	store.mu.Lock()
	store.record = settled
	store.mu.Unlock()

	watcher.pollOnce(context.Background())

	assert.Empty(t, fake.requests())
}

func TestEntryFillWatcher_SweepsReservedBrackets(t *testing.T) {
	record := spotArmerRecord()
	record.Status = storage.BracketStatusReserved // crash before bookkeeping write
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := &spotOCOExchange{}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	require.Len(t, fake.requests(), 1,
		"a RESERVED bracket with a live filled entry must still be protected")
	assert.Contains(t, store.bracketUpdates, storage.BracketStatusLegsPlaced)
}

func TestEntryFillWatcher_ReleaseKeepsEntryExchangeID(t *testing.T) {
	record := spotArmerRecord()
	record.Legs[0].ExchangeOrderID = 555
	store := &fakeWatcherStore{fakeArmerStore{record: record}}
	fake := &spotOCOExchange{getStatuses: []string{"CANCELED"}, getOrderQty: "0"}
	watcher := newWatcherFixture(t, fake, store)

	watcher.pollOnce(context.Background())

	assert.Contains(t, store.bracketUpdates, storage.BracketStatusClosed)
	assert.Equal(t, int64(555), store.legExchangeIDs["arm-main"],
		"releasing a dead bracket must not erase the entry's exchange order id")
}

func TestEntryFillWatcher_StartStopLifecycle(t *testing.T) {
	store := &fakeWatcherStore{fakeArmerStore{record: spotArmerRecord()}}
	fake := &spotOCOExchange{}
	watcher := newWatcherFixture(t, fake, store)

	watcher.Start(context.Background())
	require.Eventually(t, func() bool {
		return len(fake.requests()) == 1
	}, 2*time.Second, 5*time.Millisecond, "the polling loop must arm on its own")
	watcher.Stop()
}
