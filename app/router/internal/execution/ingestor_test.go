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
