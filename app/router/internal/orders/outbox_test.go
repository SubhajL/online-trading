package orders

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type retryOutboxStore struct {
	mu        sync.Mutex
	message   *OutboxMessage
	delivered bool
	attempts  int
}

func (store *retryOutboxStore) Enqueue(context.Context, *OrderUpdate) error { return nil }

func (store *retryOutboxStore) Claim(context.Context) (*OutboxMessage, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.delivered || store.message == nil {
		return nil, nil
	}
	store.attempts++
	copy := *store.message
	copy.Attempts = store.attempts
	return &copy, nil
}

func (store *retryOutboxStore) MarkDelivered(context.Context, uuid.UUID) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.delivered = true
	return nil
}

func (store *retryOutboxStore) MarkFailed(
	context.Context,
	uuid.UUID,
	int,
	string,
	time.Time,
	bool,
) error {
	return nil
}

func TestOutboxRetriesAfterEngineOutage(t *testing.T) {
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		assert.Equal(t, "Bearer engine-token", r.Header.Get("Authorization"))
		var envelope OrderUpdateEnvelope
		require.NoError(t, json.NewDecoder(r.Body).Decode(&envelope))
		assert.Equal(t, int64(1), envelope.Sequence)
		if requests == 1 {
			http.Error(w, "engine unavailable", http.StatusServiceUnavailable)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(server.Close)

	store := &retryOutboxStore{message: &OutboxMessage{Envelope: OrderUpdateEnvelope{
		EventID: uuid.New(), AggregateID: "SPOT:abc_entry", Sequence: 1,
		EventVersion: 1, EventType: "order_update.v1", OccurredAt: time.Now().UTC(),
		Payload: json.RawMessage(`{"client_order_id":"abc_entry","status":"FILLED"}`),
	}}}
	dispatcher := NewOutboxDispatcher(store, server.URL, "engine-token", zerolog.Nop())

	didWork, firstErr := dispatcher.DispatchOnce(context.Background())
	require.True(t, didWork)
	require.Error(t, firstErr)
	assert.False(t, store.delivered)

	didWork, secondErr := dispatcher.DispatchOnce(context.Background())
	require.True(t, didWork)
	require.NoError(t, secondErr)
	assert.True(t, store.delivered)
	assert.Equal(t, 2, requests)
}
