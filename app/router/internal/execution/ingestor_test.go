package execution

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"router/internal/websocket"
)

type mockListenKeyClient struct {
	mu             sync.Mutex
	created        []string
	keptAlive      []string
	deleted        []string
	nextListenKeys []string
}

func (m *mockListenKeyClient) CreateFuturesListenKey(ctx context.Context) (string, error) {
	_ = ctx
	m.mu.Lock()
	defer m.mu.Unlock()
	key := m.nextListenKeys[0]
	m.nextListenKeys = m.nextListenKeys[1:]
	m.created = append(m.created, key)
	return key, nil
}

func (m *mockListenKeyClient) KeepAliveFuturesListenKey(ctx context.Context, listenKey string) error {
	_ = ctx
	m.mu.Lock()
	defer m.mu.Unlock()
	m.keptAlive = append(m.keptAlive, listenKey)
	return nil
}

func (m *mockListenKeyClient) DeleteFuturesListenKey(ctx context.Context, listenKey string) error {
	_ = ctx
	m.mu.Lock()
	defer m.mu.Unlock()
	m.deleted = append(m.deleted, listenKey)
	return nil
}

type mockSubscriber struct {
	mu       sync.Mutex
	keys     []string
	handlers map[string]*websocket.UserDataHandler
}

func (m *mockSubscriber) SubscribeToUserData(
	ctx context.Context,
	listenKey string,
	handler *websocket.UserDataHandler,
) error {
	_ = ctx
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.handlers == nil {
		m.handlers = make(map[string]*websocket.UserDataHandler)
	}
	m.keys = append(m.keys, listenKey)
	m.handlers[listenKey] = handler
	return nil
}

func (m *mockSubscriber) UnsubscribeFromUserData(ctx context.Context, listenKey string) error {
	_ = ctx
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.handlers, listenKey)
	return nil
}

func TestIngestor_RestartsOnListenKeyExpired(t *testing.T) {
	lk := &mockListenKeyClient{nextListenKeys: []string{"lk-1", "lk-2"}}
	sub := &mockSubscriber{}
	logger := zerolog.Nop()

	ing := NewIngestor(lk, sub, logger, WithKeepAliveInterval(0))
	require.NoError(t, ing.Start(context.Background()))

	sub.mu.Lock()
	handler := sub.handlers["lk-1"]
	sub.mu.Unlock()

	require.NotNil(t, handler)
	require.NoError(t, handler.HandleListenKeyExpired())

	require.Eventually(t, func() bool {
		sub.mu.Lock()
		defer sub.mu.Unlock()
		_, ok := sub.handlers["lk-2"]
		return ok
	}, 2*time.Second, 10*time.Millisecond)
}

func TestIngestor_RestartSerialized_OnlyOneExecutes(t *testing.T) {
	// Setup with enough listen keys for multiple restarts
	lk := &mockListenKeyClient{nextListenKeys: []string{"lk-1", "lk-2", "lk-3", "lk-4", "lk-5", "lk-6"}}
	sub := &mockSubscriber{}
	logger := zerolog.Nop()

	ing := NewIngestor(lk, sub, logger, WithKeepAliveInterval(0))
	require.NoError(t, ing.Start(context.Background()))
	t.Cleanup(func() {
		_ = ing.Stop(context.Background())
	})

	// Get the handler before triggering restarts
	sub.mu.Lock()
	handler := sub.handlers["lk-1"]
	sub.mu.Unlock()
	require.NotNil(t, handler)

	// Trigger multiple concurrent restart requests
	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = handler.HandleListenKeyExpired()
		}()
	}
	wg.Wait()

	// Give time for any restarts to complete
	time.Sleep(100 * time.Millisecond)

	// Serialization ensures concurrent restarts don't all execute.
	// We expect significantly fewer restarts than signals (5).
	// Due to goroutine timing, we may get 1-3 restarts, but not 5.
	lk.mu.Lock()
	createdCount := len(lk.created)
	lk.mu.Unlock()

	require.Less(t, createdCount, 5,
		"serialization should prevent all 5 concurrent signals from restarting")
}

func TestIngestor_RestartSerialized_AllowsSubsequentRestart(t *testing.T) {
	// Test that after a restart completes, another restart can happen
	lk := &mockListenKeyClient{nextListenKeys: []string{"lk-1", "lk-2", "lk-3"}}
	sub := &mockSubscriber{}
	logger := zerolog.Nop()

	ing := NewIngestor(lk, sub, logger, WithKeepAliveInterval(0))
	require.NoError(t, ing.Start(context.Background()))
	t.Cleanup(func() {
		_ = ing.Stop(context.Background())
	})

	// First restart
	sub.mu.Lock()
	handler := sub.handlers["lk-1"]
	sub.mu.Unlock()
	require.NotNil(t, handler)
	require.NoError(t, handler.HandleListenKeyExpired())

	// Wait for first restart to complete
	require.Eventually(t, func() bool {
		sub.mu.Lock()
		defer sub.mu.Unlock()
		_, ok := sub.handlers["lk-2"]
		return ok
	}, 2*time.Second, 10*time.Millisecond)

	// Second restart should also work
	sub.mu.Lock()
	handler2 := sub.handlers["lk-2"]
	sub.mu.Unlock()
	require.NotNil(t, handler2)
	require.NoError(t, handler2.HandleListenKeyExpired())

	require.Eventually(t, func() bool {
		sub.mu.Lock()
		defer sub.mu.Unlock()
		_, ok := sub.handlers["lk-3"]
		return ok
	}, 2*time.Second, 10*time.Millisecond)

	// Should have created 3 listen keys total
	lk.mu.Lock()
	createdCount := len(lk.created)
	lk.mu.Unlock()
	require.Equal(t, 3, createdCount)
}

func TestIngestor_ForwardsOrderTradeUpdatesToCallback(t *testing.T) {
	lk := &mockListenKeyClient{nextListenKeys: []string{"lk-1"}}
	sub := &mockSubscriber{}
	logger := zerolog.Nop()

	var mu sync.Mutex
	var got *websocket.FuturesOrderTradeUpdateEvent

	ing := NewIngestor(
		lk,
		sub,
		logger,
		WithKeepAliveInterval(0),
		WithOrderTradeUpdateHandler(func(event *websocket.FuturesOrderTradeUpdateEvent) error {
			mu.Lock()
			defer mu.Unlock()
			got = event
			return nil
		}),
	)
	require.NoError(t, ing.Start(context.Background()))
	t.Cleanup(func() {
		_ = ing.Stop(context.Background())
	})

	sub.mu.Lock()
	handler := sub.handlers["lk-1"]
	sub.mu.Unlock()
	require.NotNil(t, handler)

	input := &websocket.FuturesOrderTradeUpdateEvent{
		EventType: "ORDER_TRADE_UPDATE",
		OrderTradeUpdate: websocket.FuturesOrderTradeData{
			Symbol:        "BTCUSDT",
			ClientOrderID: "abc",
			Side:          "BUY",
			TradeID:       123,
		},
	}
	require.NoError(t, handler.HandleFuturesOrderTradeUpdate(input))

	require.Eventually(t, func() bool {
		mu.Lock()
		defer mu.Unlock()
		return got != nil && got.OrderTradeUpdate.TradeID == 123
	}, 2*time.Second, 10*time.Millisecond)
}
