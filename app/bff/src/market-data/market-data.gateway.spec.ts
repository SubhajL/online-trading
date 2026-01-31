import { Test, TestingModule } from '@nestjs/testing';
import { MarketDataGateway } from './market-data.gateway';
import { EngineClientService } from '../engine-client/engine-client.service';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import { Server, Socket } from 'socket.io';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';

describe('MarketDataGateway', () => {
  let gateway: MarketDataGateway;
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
        'jwt.secret': 'test-secret',
      };
      return config[key];
    }),
  };

  const mockJwtService = {
    verifyAsync: jest.fn(),
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
        {
          provide: JwtService,
          useValue: mockJwtService,
        },
        WsJwtGuard,
      ],
    }).compile();

    gateway = module.get<MarketDataGateway>(MarketDataGateway);

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
      data: {
        user: {
          sub: 'user-123',
          username: 'testuser',
          roles: ['operator'],
        },
      },
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
        user: {
          username: 'testuser',
          roles: ['operator'],
        },
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
        version: '1.0.0',
        venue: 'SPOT',
        symbol: 'BTCUSDT',
        timeframe: '1m',
        open_time: '2024-01-01T00:00:00.000Z',
        close_time: '2024-01-01T00:01:00.000Z',
        open: '45000',
        high: '45500',
        low: '44800',
        close: '45200',
        volume: '100',
        quote_volume: '100',
        trades: 1000,
        taker_buy_volume: '50',
        taker_buy_quote_volume: '50',
        is_closed: true,
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'candles.v1',
      )[1];
      subscribeCallback(candleData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('candles.v1', candleData);
    });

    it('should forward feature events to subscribed clients', () => {
      const featureData = {
        version: '1.0.0',
        venue: 'SPOT',
        symbol: 'BTCUSDT',
        timeframe: '1m',
        open_time: '2024-01-01T00:00:00.000Z',
        close_time: '2024-01-01T00:01:00.000Z',
        ema_short: 45100,
        ema_long: 44900,
        rsi: 55.5,
        macd: 100,
        macd_signal: 90,
        macd_histogram: 10,
        atr: '500',
        bb_upper: 46000,
        bb_middle: 45000,
        bb_lower: 44000,
        volume_ma: 100,
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'features.v1',
      )[1];
      subscribeCallback(featureData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('features.v1', featureData);
    });

    it('should forward signal events to subscribed clients', () => {
      const signalData = {
        version: '1.0.0',
        venue: 'SPOT',
        symbol: 'BTCUSDT',
        timeframe: '1m',
        signal_id: 'sig-1',
        signal_time: '2024-01-01T00:00:00.000Z',
        signal_type: 'long',
        source: 'retest',
        entry_price: '45000',
        stop_loss: '44500',
        take_profit_1: '46000',
        take_profit_2: null,
        take_profit_3: null,
        confidence: 0.85,
        metadata: {},
      };

      // Simulate engine event
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'signals_raw.v1',
      )[1];
      subscribeCallback(signalData);

      expect(mockServer.to).toHaveBeenCalledWith('market:BTCUSDT:1m');
      expect(mockServer.emit).toHaveBeenCalledWith('signals_raw.v1', signalData);
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
