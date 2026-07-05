package execution

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/rs/zerolog"

	"router/internal/websocket"
)

type ListenKeyClient interface {
	CreateFuturesListenKey(ctx context.Context) (string, error)
	KeepAliveFuturesListenKey(ctx context.Context, listenKey string) error
	DeleteFuturesListenKey(ctx context.Context, listenKey string) error
}

type UserDataSubscriber interface {
	SubscribeToUserData(ctx context.Context, listenKey string, handler *websocket.UserDataHandler) error
	UnsubscribeFromUserData(ctx context.Context, listenKey string) error
}

type Ingestor struct {
	listenKeyClient ListenKeyClient
	subscriber      UserDataSubscriber
	logger          zerolog.Logger

	keepAliveInterval  time.Duration
	restartBackoff     time.Duration
	onOrderTradeUpdate func(*websocket.FuturesOrderTradeUpdateEvent) error

	mu        sync.Mutex
	listenKey string
	cancel    context.CancelFunc
	done      chan struct{}

	// restartMu and restartActive ensure only one restart runs at a time
	restartMu     sync.Mutex
	restartActive bool
}

type IngestorOption func(*Ingestor)

func WithKeepAliveInterval(interval time.Duration) IngestorOption {
	return func(i *Ingestor) {
		i.keepAliveInterval = interval
	}
}

func WithOrderTradeUpdateHandler(
	handler func(*websocket.FuturesOrderTradeUpdateEvent) error,
) IngestorOption {
	return func(i *Ingestor) {
		i.onOrderTradeUpdate = handler
	}
}

// WithRestartBackoff sets the base delay between stream-restart retries.
func WithRestartBackoff(backoff time.Duration) IngestorOption {
	return func(i *Ingestor) {
		if backoff > 0 {
			i.restartBackoff = backoff
		}
	}
}

func NewIngestor(
	listenKeyClient ListenKeyClient,
	subscriber UserDataSubscriber,
	logger zerolog.Logger,
	opts ...IngestorOption,
) *Ingestor {
	i := &Ingestor{
		listenKeyClient:   listenKeyClient,
		subscriber:        subscriber,
		logger:            logger,
		keepAliveInterval: 30 * time.Minute,
		restartBackoff:    time.Second,
		done:              make(chan struct{}),
	}
	for _, opt := range opts {
		opt(i)
	}
	return i
}

func (i *Ingestor) Start(ctx context.Context) error {
	if i.listenKeyClient == nil {
		return fmt.Errorf("listenKeyClient is required")
	}
	if i.subscriber == nil {
		return fmt.Errorf("subscriber is required")
	}

	i.mu.Lock()
	if i.cancel != nil {
		i.mu.Unlock()
		return fmt.Errorf("ingestor already started")
	}
	childCtx, cancel := context.WithCancel(ctx)
	i.cancel = cancel
	i.mu.Unlock()

	if err := i.startWithNewListenKey(childCtx); err != nil {
		_ = i.Stop(context.Background())
		return err
	}

	if i.keepAliveInterval > 0 {
		go i.keepAliveLoop(childCtx)
	}

	return nil
}

func (i *Ingestor) Stop(ctx context.Context) error {
	i.mu.Lock()
	cancel := i.cancel
	listenKey := i.listenKey
	i.cancel = nil
	i.listenKey = ""
	i.mu.Unlock()

	if cancel != nil {
		cancel()
	}

	if listenKey != "" {
		_ = i.subscriber.UnsubscribeFromUserData(ctx, listenKey)
		_ = i.listenKeyClient.DeleteFuturesListenKey(ctx, listenKey)
	}

	select {
	case <-i.done:
	default:
		close(i.done)
	}

	return nil
}

func (i *Ingestor) startWithNewListenKey(ctx context.Context) error {
	listenKey, err := i.listenKeyClient.CreateFuturesListenKey(ctx)
	if err != nil {
		return err
	}

	handler := &websocket.UserDataHandler{
		OnOrderTradeUpdate: func(event *websocket.FuturesOrderTradeUpdateEvent) error {
			if i.onOrderTradeUpdate == nil {
				return nil
			}
			return i.onOrderTradeUpdate(event)
		},
		OnListenKeyExpired: func() error {
			go func() {
				if err := i.restartSerialized(ctx); err != nil {
					i.logger.Error().Err(err).Msg("listen key restart failed")
				}
			}()
			return nil
		},
	}

	if err := i.subscriber.SubscribeToUserData(ctx, listenKey, handler); err != nil {
		_ = i.listenKeyClient.DeleteFuturesListenKey(ctx, listenKey)
		return err
	}

	i.mu.Lock()
	i.listenKey = listenKey
	i.mu.Unlock()

	i.logger.Info().Str("listen_key", listenKey).Msg("user data stream subscribed")
	return nil
}

// OnSocketReconnected rotates the listen key after a socket-level reconnect
// (or reconnect exhaustion). Binance invalidates the session server-side, so
// without this only a listenKeyExpired event (which the dead socket cannot
// deliver) would recover the user-data stream. Events for keys we no longer
// own are ignored so a raced zombie connection cannot kill a healthy one.
func (i *Ingestor) OnSocketReconnected(listenKey string) {
	i.mu.Lock()
	current := i.listenKey
	i.mu.Unlock()
	if listenKey != "" && current != "" && listenKey != current {
		i.logger.Debug().
			Str("listen_key", listenKey).
			Str("current", current).
			Msg("ignoring reconnect signal for stale listen key")
		return
	}

	i.logger.Warn().Str("listen_key", listenKey).
		Msg("user data socket reconnected; rotating listen key")
	if err := i.restartSerialized(context.Background()); err != nil {
		i.logger.Error().Err(err).Msg("failed to restart user data stream after reconnect")
	}
}

// restartSerialized ensures only one restart runs at a time.
// If a restart is already in progress, additional calls return immediately.
func (i *Ingestor) restartSerialized(ctx context.Context) error {
	i.restartMu.Lock()
	if i.restartActive {
		i.restartMu.Unlock()
		i.logger.Debug().Msg("restart already in progress, skipping")
		return nil
	}
	i.restartActive = true
	i.restartMu.Unlock()

	defer func() {
		i.restartMu.Lock()
		i.restartActive = false
		i.restartMu.Unlock()
	}()

	return i.restart(ctx)
}

func (i *Ingestor) restart(ctx context.Context) error {
	i.mu.Lock()
	oldKey := i.listenKey
	i.mu.Unlock()

	if oldKey != "" {
		_ = i.subscriber.UnsubscribeFromUserData(ctx, oldKey)
		_ = i.listenKeyClient.DeleteFuturesListenKey(ctx, oldKey)
	}

	// The failure that forced a rotation (network trouble) is exactly when
	// the new listen-key request will also fail; a single silent failure
	// here would leave orders flowing with fills invisible. Retry with
	// backoff until the stream is back or the ingestor stops.
	backoff := i.restartBackoff
	for {
		err := i.startWithNewListenKey(ctx)
		if err == nil {
			return nil
		}
		i.logger.Error().Err(err).Dur("retry_in", backoff).
			Msg("failed to restart user data stream; retrying")
		select {
		case <-i.done:
			return err
		case <-ctx.Done():
			return err
		case <-time.After(backoff):
		}
		if backoff < 30*time.Second {
			backoff *= 2
		}
	}
}

func (i *Ingestor) keepAliveLoop(ctx context.Context) {
	ticker := time.NewTicker(i.keepAliveInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			i.mu.Lock()
			key := i.listenKey
			i.mu.Unlock()
			if key == "" {
				continue
			}
			if err := i.listenKeyClient.KeepAliveFuturesListenKey(ctx, key); err != nil {
				i.logger.Error().Err(err).Msg("listen key keep-alive failed")
			}
		}
	}
}
