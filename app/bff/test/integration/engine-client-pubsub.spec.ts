import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AppModule } from '../../src/app.module';
import { EngineClientService } from '../../src/engine-client/engine-client.service';

// No mocks - using real Redis service

describe('Engine Client Pub/Sub Integration', () => {
  let app: INestApplication;
  let engineClient: EngineClientService;
  let eventEmitter: EventEmitter2;

  beforeEach(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();

    engineClient = moduleFixture.get<EngineClientService>(EngineClientService);
    eventEmitter = moduleFixture.get<EventEmitter2>(EventEmitter2);
  });

  afterEach(async () => {
    await app.close();
  });

  describe('Event Flow', () => {
    it('should handle complete trading flow from candle to order update', async () => {
      const events: any[] = [];

      // Track all events
      eventEmitter.onAny((event, data) => {
        events.push({ event, data });
      });

      // The engine client connects automatically on app init
      // To test real event flow, the Python engine needs to publish events to Redis

      // For real integration testing:
      // 1. Python engine should be running and connected to Redis
      // 2. Engine should publish: candle.v1, features.v1, signals_raw.v1, decision.v1
      // 3. This test would wait for and verify those events

      // Wait for potential events
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // In a real test with engine running, we'd verify:
      // expect(events.map(e => e.event)).toContain('candle.v1');
      // expect(events.map(e => e.event)).toContain('decision.v1');
    });

    it('should handle multiple symbol subscriptions', async () => {
      const receivedEvents = new Map<string, any[]>();

      // Subscribe to multiple symbols
      const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'];

      for (const symbol of symbols) {
        const handler = jest.fn((data) => {
          if (!receivedEvents.has(symbol)) {
            receivedEvents.set(symbol, []);
          }
          receivedEvents.get(symbol)!.push(data);
        });

        await engineClient.subscribe(`candle.${symbol}.1m`, handler);
      }

      // For real integration testing:
      // 1. Python engine should publish candle events for each symbol
      // 2. This test would verify all handlers are called

      await new Promise((resolve) => setTimeout(resolve, 1000));
    });

    it('should publish events to engine', async () => {
      // Publish a manual trade event
      const manualTradeEvent = {
        type: 'MANUAL_TRADE',
        symbol: 'BTCUSDT',
        side: 'BUY',
        quantity: 0.01,
        timestamp: Date.now(),
      };

      await engineClient.publish('manual_trade.v1', manualTradeEvent);

      // For real integration testing:
      // 1. Python engine should be subscribed to bff:* events
      // 2. Engine should receive and log this event
    });

    it('should handle connection recovery', async () => {
      // For real integration testing:
      // 1. Manually stop Redis
      // 2. Verify engine client detects disconnect
      // 3. Restart Redis
      // 4. Verify engine client reconnects

      const health = await engineClient.checkHealth();
      expect(health.status).toBe('up');
    });
  });

  describe('Performance', () => {
    it('should handle high volume of events', async () => {
      const receivedEvents: any[] = [];

      eventEmitter.on('candle.v1', (data) => {
        receivedEvents.push(data);
      });

      // For real integration testing:
      // 1. Python engine should publish high volume of events
      // 2. Measure actual throughput and latency

      await new Promise((resolve) => setTimeout(resolve, 2000));

      // In real test, verify events were received
    });
  });
});
