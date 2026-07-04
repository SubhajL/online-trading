import { Test, TestingModule } from '@nestjs/testing';
import { TradingGateway } from './trading.gateway';
import { TradingService } from './trading.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Server, Socket } from 'socket.io';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';
import { CommandBus } from '@nestjs/cqrs';
import { CONTRACT_TOPICS } from '../contracts/topics';

describe('TradingGateway', () => {
  let gateway: TradingGateway;
  let tradingService: TradingService;
  let mockServer: Server;
  let mockClient: Socket;

  const mockTradingService = {
    placeOrder: jest.fn(),
    getOrderStatus: jest.fn(),
    cancelOrder: jest.fn(),
    getPositions: jest.fn(),
    getActiveOrders: jest.fn(),
    setAutoTrading: jest.fn(),
    isAutoTradingEnabled: jest.fn(),
  };

  const mockEventEmitter = {
    on: jest.fn(),
  };

  const mockJwtService = {
    verifyAsync: jest.fn(),
  };

  const mockConfigService = {
    get: jest.fn((key: string) => {
      if (key === 'jwt.secret') return 'test-secret';
      return null;
    }),
  };

  const mockCommandBus = {
    execute: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TradingGateway,
        {
          provide: TradingService,
          useValue: mockTradingService,
        },
        {
          provide: EventEmitter2,
          useValue: mockEventEmitter,
        },
        {
          provide: JwtService,
          useValue: mockJwtService,
        },
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
        {
          provide: CommandBus,
          useValue: mockCommandBus,
        },
        WsJwtGuard,
      ],
    }).compile();

    gateway = module.get<TradingGateway>(TradingGateway);
    tradingService = module.get<TradingService>(TradingService);

    // Mock Socket.io server
    mockServer = {
      emit: jest.fn(),
      use: jest.fn(),
      to: jest.fn().mockReturnThis(),
    } as any;

    // Mock client socket
    mockClient = {
      id: 'test-client-123',
      emit: jest.fn(),
      join: jest.fn(),
      leave: jest.fn(),
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

      expect(mockClient.join).toHaveBeenCalledWith('trading');
      expect(mockClient.emit).toHaveBeenCalledWith('connected', {
        message: 'Connected to trading gateway',
        user: {
          username: 'testuser',
          roles: ['operator'],
        },
      });
    });
  });

  describe('handleDisconnect', () => {
    it('should handle client disconnection', () => {
      gateway.handleDisconnect(mockClient);

      expect(mockClient.leave).toHaveBeenCalledWith('trading');
    });
  });

  describe('placeOrder', () => {
    it('should place an order via WebSocket', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'USD_M' as const,
      };

      const orderResponse = {
        orderId: '123456',
        status: 'NEW',
      };

      mockCommandBus.execute.mockResolvedValue(orderResponse);

      const result = await gateway.placeOrder(mockClient, orderRequest);

      expect(result).toEqual({ success: true, data: orderResponse });
      expect(mockCommandBus.execute).toHaveBeenCalled();
    });

    it('should handle order placement errors', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'USD_M' as const,
      };

      const error = new Error('Insufficient balance');
      mockCommandBus.execute.mockRejectedValue(error);

      const result = await gateway.placeOrder(mockClient, orderRequest);

      expect(result).toEqual({
        success: false,
        error: 'Insufficient balance',
      });
    });
  });

  describe('event forwarding', () => {
    beforeEach(() => {
      gateway.afterInit(mockServer);
    });

    it('should forward order events to trading room', () => {
      const orderEvent = {
        orderId: '123456',
        status: 'FILLED',
      };

      // Get the callback registered for order_update.v1 event
      const eventCallback = mockEventEmitter.on.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.orderUpdateV1,
      )?.[1];

      expect(eventCallback).toBeDefined();

      // Simulate order placed event
      eventCallback(orderEvent);

      expect(mockServer.to).toHaveBeenCalledWith('trading');
      expect(mockServer.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, orderEvent);
    });

    it('should forward position update events', () => {
      const positionEvent = {
        symbol: 'BTCUSDT',
        side: 'LONG',
        quantity: 0.01,
        pnl: 50,
      };

      // Get the callback registered for position_update.v1 event
      const eventCallback = mockEventEmitter.on.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.positionUpdateV1,
      )?.[1];

      expect(eventCallback).toBeDefined();

      // Simulate position update event
      eventCallback(positionEvent);

      expect(mockServer.to).toHaveBeenCalledWith('trading');
      expect(mockServer.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.positionUpdateV1, positionEvent);
    });

    it('should forward auto trading status changes', () => {
      const autoTradingEvent = {
        enabled: true,
      };

      // Get the callback registered for auto_trading.v1 event
      const eventCallback = mockEventEmitter.on.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.autoTradingV1,
      )?.[1];

      expect(eventCallback).toBeDefined();

      // Simulate auto trading change event
      eventCallback(autoTradingEvent);

      expect(mockServer.to).toHaveBeenCalledWith('trading');
      expect(mockServer.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.autoTradingV1, autoTradingEvent);
    });
  });

  describe('getPositions', () => {
    it('should get positions via WebSocket', async () => {
      const positions = [
        {
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 0.01,
          pnl: 100,
        },
      ];

      mockTradingService.getPositions.mockResolvedValue(positions);

      const result = await gateway.getPositions();

      expect(result).toEqual(positions);
      expect(tradingService.getPositions).toHaveBeenCalled();
    });
  });

  describe('getActiveOrders', () => {
    it('should get active orders via WebSocket', async () => {
      const orders = [
        {
          orderId: '123456',
          status: 'NEW',
          symbol: 'BTCUSDT',
        },
      ];

      mockTradingService.getActiveOrders.mockResolvedValue(orders);

      const result = await gateway.getActiveOrders();

      expect(result).toEqual(orders);
      expect(tradingService.getActiveOrders).toHaveBeenCalled();
    });
  });

  describe('handshake auth middleware', () => {
    it('registers a middleware that rejects token-less sockets with an error', async () => {
      gateway.afterInit(mockServer);

      const useMock = (mockServer as unknown as { use: jest.Mock }).use;
      expect(useMock).toHaveBeenCalledTimes(1);
      const middleware = useMock.mock.calls[0][0] as (
        socket: unknown,
        next: (err?: Error) => void,
      ) => Promise<void>;

      const next = jest.fn();
      await middleware(
        { id: 'anon', handshake: { auth: {}, headers: {}, query: {} }, data: {} },
        next,
      );

      expect(next).toHaveBeenCalledTimes(1);
      expect(next).toHaveBeenCalledWith(expect.any(Error));
    });
  });
});
