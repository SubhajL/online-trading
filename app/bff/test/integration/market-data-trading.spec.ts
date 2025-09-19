import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { io, Socket } from 'socket.io-client';
import { AppModule } from '../../src/app.module';

// No mocks - using real services

describe('Market Data to Trading Integration', () => {
  let app: INestApplication;
  let marketDataClient: Socket;
  let tradingClient: Socket;
  let eventEmitter: EventEmitter2;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.listen(3001);

    eventEmitter = moduleFixture.get<EventEmitter2>(EventEmitter2);

    // Connect WebSocket clients
    marketDataClient = io('http://localhost:3001/market-data', {
      transports: ['websocket'],
    });

    tradingClient = io('http://localhost:3001/trading', {
      transports: ['websocket'],
    });

    await new Promise<void>((resolve) => {
      let connected = 0;
      marketDataClient.on('connect', () => {
        connected++;
        if (connected === 2) resolve();
      });
      tradingClient.on('connect', () => {
        connected++;
        if (connected === 2) resolve();
      });
    });
  });

  afterEach(async () => {
    marketDataClient.disconnect();
    tradingClient.disconnect();
    await app.close();
  });

  it('should process market data event through to order placement', async () => {
    // No mocks - using real router service

    // Enable auto trading
    await new Promise<void>((resolve) => {
      tradingClient.emit('setAutoTrading', { enabled: true }, (response: any) => {
        expect(response.success).toBe(true);
        resolve();
      });
    });

    // Subscribe to market data
    await new Promise<void>((resolve) => {
      marketDataClient.emit(
        'subscribe',
        {
          symbol: 'BTCUSDT',
          timeframe: '1m',
        },
        (response: any) => {
          expect(response.success).toBe(true);
          resolve();
        },
      );
    });

    // Listen for order placed event
    const orderPlacedPromise = new Promise((resolve) => {
      tradingClient.on('order.placed', resolve);
    });

    // Simulate candle event from engine
    const candleEvent = {
      symbol: 'BTCUSDT',
      timeframe: '1m',
      timestamp: Date.now(),
      open: 45000,
      high: 45500,
      low: 44800,
      close: 45200,
      volume: 100,
    };

    // Emit candle event
    eventEmitter.emit('candle.v1', candleEvent);

    // Simulate decision event from engine
    const decisionEvent = {
      symbol: 'BTCUSDT',
      action: 'BUY' as const,
      quantity: 0.01,
      venue: 'USD_M' as const,
      type: 'MARKET' as const,
      confidence: 0.85,
      timestamp: Date.now(),
    };

    eventEmitter.emit('decision.v1', decisionEvent);

    // Wait for order to be placed
    const orderPlaced = await orderPlacedPromise;

    expect(orderPlaced).toMatchObject({
      status: 'NEW',
      symbol: 'BTCUSDT',
      side: 'BUY',
    });

    // Order should have been placed via real router service
  });

  it('should handle order update events from engine', async () => {
    // Enable auto trading
    await new Promise<void>((resolve) => {
      tradingClient.emit('setAutoTrading', { enabled: true }, (response: any) => {
        expect(response.success).toBe(true);
        resolve();
      });
    });

    // No mocks - using real router service

    // Listen for position update
    const positionUpdatePromise = new Promise((resolve) => {
      tradingClient.on('position.updated', resolve);
    });

    // Emit decision event
    const decisionEvent = {
      symbol: 'ETHUSDT',
      action: 'SELL' as const,
      quantity: 1,
      venue: 'SPOT' as const,
      type: 'LIMIT' as const,
      price: 3000,
      confidence: 0.75,
      timestamp: Date.now(),
    };

    eventEmitter.emit('decision.v1', decisionEvent);

    // Wait for order to be placed
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Simulate order fill event
    const orderUpdateEvent = {
      orderId: '789012',
      symbol: 'ETHUSDT',
      status: 'FILLED',
      executedQty: 1,
      executedPrice: 3000,
      timestamp: Date.now(),
    };

    eventEmitter.emit('order_update.v1', orderUpdateEvent);

    // Wait for position update
    const positionUpdate = await positionUpdatePromise;

    expect(positionUpdate).toMatchObject({
      symbol: 'ETHUSDT',
      side: 'SHORT',
      quantity: 1,
      entryPrice: 3000,
      currentPrice: 3000,
      pnl: 0,
      pnlPercent: 0,
      venue: 'SPOT',
    });
  });

  it('should skip trading when auto trading is disabled', async () => {
    // Listen for decision skipped event
    const decisionSkippedPromise = new Promise((resolve) => {
      tradingClient.on('decision.skipped', resolve);
    });

    // Emit decision event with auto trading disabled
    const decisionEvent = {
      symbol: 'BTCUSDT',
      action: 'BUY' as const,
      quantity: 0.01,
      venue: 'USD_M' as const,
      type: 'MARKET' as const,
      confidence: 0.85,
      timestamp: Date.now(),
    };

    eventEmitter.emit('decision.v1', decisionEvent);

    // Wait for decision skipped event
    const skippedEvent = await decisionSkippedPromise;

    expect(skippedEvent).toMatchObject({
      reason: 'Auto trading disabled',
      decision: decisionEvent,
    });
  });

  it('should handle multiple subscriptions across rooms', async () => {
    const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'];
    const timeframes = ['1m', '5m'];
    const subscriptions = [];

    // Subscribe to multiple symbols and timeframes
    for (const symbol of symbols) {
      for (const timeframe of timeframes) {
        const promise = new Promise<void>((resolve) => {
          marketDataClient.emit('subscribe', { symbol, timeframe }, (response: any) => {
            expect(response.success).toBe(true);
            resolve();
          });
        });
        subscriptions.push(promise);
      }
    }

    await Promise.all(subscriptions);

    // Track received candles
    const receivedCandles = new Map<string, any>();
    marketDataClient.on('candle', (data: any) => {
      const key = `${data.symbol}:${data.timeframe}`;
      receivedCandles.set(key, data);
    });

    // Emit candles for all subscriptions
    for (const symbol of symbols) {
      for (const timeframe of timeframes) {
        const candleEvent = {
          symbol,
          timeframe,
          timestamp: Date.now(),
          open: 100,
          high: 110,
          low: 90,
          close: 105,
          volume: 1000,
        };
        eventEmitter.emit('candle.v1', candleEvent);
      }
    }

    // Wait for events to propagate
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Verify all candles were received
    expect(receivedCandles.size).toBe(6);
    for (const symbol of symbols) {
      for (const timeframe of timeframes) {
        const key = `${symbol}:${timeframe}`;
        expect(receivedCandles.has(key)).toBe(true);
      }
    }
  });
});
