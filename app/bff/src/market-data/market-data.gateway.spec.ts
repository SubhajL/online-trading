import { Test, TestingModule } from '@nestjs/testing';
import { MarketDataGateway } from './market-data.gateway';
import { EngineClientService } from '../engine-client/engine-client.service';
import { ConfigService } from '@nestjs/config';
import { Server, Socket } from 'socket.io';

describe('MarketDataGateway', () => {
  let gateway: MarketDataGateway;
  let engineClient: EngineClientService;
  let mockServer: Server;
  let mockClient: Socket;

  const mockEngineClientService = {
    subscribe: jest.fn(),
    emit: jest.fn(),
    on: jest.fn(),
  };

  const mockConfigService = {
    get: jest.fn((key: string) => {
      const config: any = {
        'websocket.namespace': '/trading',
      };
      return config[key];
    }),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        MarketDataGateway,
        {
          provide: EngineClientService,
          useValue: mockEngineClientService,
        },
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
      ],
    }).compile();

    gateway = module.get<MarketDataGateway>(MarketDataGateway);
    engineClient = module.get<EngineClientService>(EngineClientService);

    // Mock Socket.io server
    mockServer = {
      emit: jest.fn(),
      to: jest.fn().mockReturnThis(),
      in: jest.fn().mockReturnThis(),
    } as any;

    // Mock client socket
    mockClient = {
      id: 'test-client-123',
      rooms: new Set(['test-client-123']),
      join: jest.fn(),
      leave: jest.fn(),
      emit: jest.fn(),
      on: jest.fn(),
      disconnect: jest.fn(),
    } as any;

    // Set the server on the gateway
    (gateway as any).server = mockServer;
  });

  it('should be defined', () => {
    expect(gateway).toBeDefined();
  });

  describe('handleConnection', () => {
    it('should handle new client connection', () => {
      gateway.handleConnection(mockClient);

      expect(mockClient.emit).toHaveBeenCalledWith('connected', {
        message: 'Connected to market data',
        clientId: 'test-client-123',
      });
    });
  });

  describe('handleDisconnect', () => {
    it('should handle client disconnection', () => {
      gateway.handleConnection(mockClient);
      gateway.handleDisconnect(mockClient);

      expect(mockClient.rooms.size).toBe(1); // Only the client's own room
    });
  });

  describe('subscribeToSymbol', () => {
    it('should subscribe client to symbol room', async () => {
      const subscribeData = { symbol: 'BTCUSDT', timeframe: '1m' };

      await gateway.subscribeToSymbol(mockClient, subscribeData);

      expect(mockClient.join).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockClient.emit).toHaveBeenCalledWith('subscribed', {
        symbol: 'BTCUSDT',
        timeframe: '1m',
      });
    });

    it('should handle invalid subscription data', async () => {
      const invalidData = { symbol: '', timeframe: '' };

      await gateway.subscribeToSymbol(mockClient, invalidData);

      expect(mockClient.emit).toHaveBeenCalledWith('error', {
        message: 'Invalid subscription data',
      });
    });
  });

  describe('unsubscribeFromSymbol', () => {
    it('should unsubscribe client from symbol room', async () => {
      const unsubscribeData = { symbol: 'BTCUSDT', timeframe: '1m' };

      await gateway.unsubscribeFromSymbol(mockClient, unsubscribeData);

      expect(mockClient.leave).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockClient.emit).toHaveBeenCalledWith('unsubscribed', {
        symbol: 'BTCUSDT',
        timeframe: '1m',
      });
    });
  });

  describe('engine event handling', () => {
    beforeEach(() => {
      gateway.afterInit(mockServer);
    });

    it('should forward candle events to subscribed clients', () => {
      const candleData = {
        symbol: 'BTCUSDT',
        timeframe: '1m',
        open: 45000,
        high: 45500,
        low: 44800,
        close: 45200,
        volume: 100,
        closeTime: Date.now(),
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'candles.v1',
      )[1];
      subscribeCallback(candleData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('candle', candleData);
    });

    it('should forward feature events to subscribed clients', () => {
      const featureData = {
        symbol: 'BTCUSDT',
        timeframe: '1m',
        ema20: 45100,
        ema50: 44900,
        rsi: 55.5,
        macd: {
          macd: 100,
          signal: 90,
          histogram: 10,
        },
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'features.v1',
      )[1];
      subscribeCallback(featureData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('features', featureData);
    });

    it('should forward signal events to subscribed clients', () => {
      const signalData = {
        symbol: 'BTCUSDT',
        timeframe: '1m',
        type: 'BUY',
        entry: 45000,
        stopLoss: 44500,
        takeProfit: 46000,
        confidence: 0.85,
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'signals_raw.v1',
      )[1];
      subscribeCallback(signalData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('signal', signalData);
    });
  });

  describe('getActiveSubscriptions', () => {
    it('should return active subscriptions for a client', () => {
      // Create a new client with mocked rooms
      const clientWithRooms = {
        ...mockClient,
        rooms: new Set(['test-client-123', 'market:BTCUSDT:1m', 'market:ETHUSDT:5m']),
      } as Socket;

      const result = gateway.getActiveSubscriptions(clientWithRooms);

      expect(result).toEqual({
        subscriptions: [
          { symbol: 'BTCUSDT', timeframe: '1m' },
          { symbol: 'ETHUSDT', timeframe: '5m' },
        ],
      });
    });
  });
});
