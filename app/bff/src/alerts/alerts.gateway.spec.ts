import { Test, TestingModule } from '@nestjs/testing';
import { AlertsGateway } from './alerts.gateway';
import { AlertsService } from './alerts.service';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { Server, Socket } from 'socket.io';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import { WsJwtGuard } from '../auth/guards/ws-jwt.guard';

describe('AlertsGateway', () => {
  let gateway: AlertsGateway;
  let alertsService: AlertsService;
  let eventEmitter: EventEmitter2;
  let mockServer: Server;
  let mockClient: Socket;

  const mockAlertsService = {
    create: jest.fn(),
    getUnreadCount: jest.fn(),
  };

  const mockEventEmitter = {
    on: jest.fn(),
    emit: jest.fn(),
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

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AlertsGateway,
        {
          provide: AlertsService,
          useValue: mockAlertsService,
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
        WsJwtGuard,
      ],
    }).compile();

    gateway = module.get<AlertsGateway>(AlertsGateway);
    alertsService = module.get<AlertsService>(AlertsService);
    eventEmitter = module.get<EventEmitter2>(EventEmitter2);

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

  describe('afterInit', () => {
    it('should set up event listeners', () => {
      gateway.afterInit(mockServer);

      // Should subscribe to various alert events
      expect(eventEmitter.on).toHaveBeenCalledTimes(4);
      expect(eventEmitter.on).toHaveBeenCalledWith('alert.new', expect.any(Function));
      expect(eventEmitter.on).toHaveBeenCalledWith('alert.updated', expect.any(Function));
      expect(eventEmitter.on).toHaveBeenCalledWith('decision.received', expect.any(Function));
      expect(eventEmitter.on).toHaveBeenCalledWith('order.updated', expect.any(Function));
    });
  });

  describe('handleConnection', () => {
    it('should handle new client connection', async () => {
      mockAlertsService.getUnreadCount.mockResolvedValue({ count: 5 });

      await gateway.handleConnection(mockClient);

      expect(mockClient.join).toHaveBeenCalledWith('alerts:user-123');
      expect(mockClient.emit).toHaveBeenCalledWith('connected', {
        message: 'Connected to alerts gateway',
        unreadCount: 5,
      });
    });
  });

  describe('handleDisconnect', () => {
    it('should handle client disconnection', () => {
      gateway.handleDisconnect(mockClient);

      expect(mockClient.leave).toHaveBeenCalledWith('alerts:user-123');
    });
  });

  describe('subscribe', () => {
    it('should subscribe client to alerts', () => {
      const response = gateway.subscribe(mockClient);

      expect(mockClient.join).toHaveBeenCalledWith('alerts');
      expect(response).toEqual({
        event: 'subscribed',
        data: { message: 'Subscribed to alerts' },
      });
    });
  });

  describe('unsubscribe', () => {
    it('should unsubscribe client from alerts', () => {
      const response = gateway.unsubscribe(mockClient);

      expect(mockClient.leave).toHaveBeenCalledWith('alerts');
      expect(response).toEqual({
        event: 'unsubscribed',
        data: { message: 'Unsubscribed from alerts' },
      });
    });
  });

  describe('getUnreadCount', () => {
    it('should return unread count', async () => {
      mockAlertsService.getUnreadCount.mockResolvedValue({ count: 3 });

      const result = await gateway.getUnreadCount();

      expect(result).toEqual({ count: 3 });
      expect(alertsService.getUnreadCount).toHaveBeenCalled();
    });
  });

  describe('event handlers', () => {
    beforeEach(() => {
      gateway.afterInit(mockServer);
    });

    it('should handle alert.new event', async () => {
      const mockAlert = {
        id: 'alert-123',
        type: 'order',
        priority: 'high',
        title: 'Order Filled',
        message: 'Your order has been filled',
      };

      // Get the callback that was registered for alert.new
      const alertNewCallback = mockEventEmitter.on.mock.calls.find(
        call => call[0] === 'alert.new'
      )[1];

      // Simulate the event
      await alertNewCallback(mockAlert);

      expect(mockServer.to).toHaveBeenCalledWith('alerts');
      expect(mockServer.emit).toHaveBeenCalledWith('alert.new', mockAlert);
    });

    it('should create alert from decision event', async () => {
      const mockDecision = {
        symbol: 'BTCUSDT',
        action: 'BUY',
        confidence: 0.85,
        entry: 45000,
        stopLoss: 44000,
        takeProfit: 46000,
      };

      const createdAlert = {
        id: 'alert-456',
        type: 'decision',
        priority: 'high',
        title: 'Trading Signal: BUY BTCUSDT',
        message: 'Signal generated with 85% confidence',
      };

      mockAlertsService.create.mockResolvedValue(createdAlert);

      // Get the callback for decision.received
      const decisionCallback = mockEventEmitter.on.mock.calls.find(
        call => call[0] === 'decision.received'
      )[1];

      await decisionCallback(mockDecision);

      expect(alertsService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'decision',
          priority: 'high',
          title: 'Trading Signal: BUY BTCUSDT',
        })
      );
    });

    it('should create alert from order update', async () => {
      const mockOrderUpdate = {
        orderId: 'order-789',
        symbol: 'ETHUSDT',
        status: 'FILLED',
        executedQty: 1.5,
        executedPrice: 2500,
      };

      const createdAlert = {
        id: 'alert-789',
        type: 'order',
        priority: 'medium',
        title: 'Order FILLED: ETHUSDT',
        message: 'Order order-789 has been FILLED',
      };

      mockAlertsService.create.mockResolvedValue(createdAlert);

      // Get the callback for order.updated
      const orderCallback = mockEventEmitter.on.mock.calls.find(
        call => call[0] === 'order.updated'
      )[1];

      await orderCallback(mockOrderUpdate);

      expect(alertsService.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'order',
          title: 'Order FILLED: ETHUSDT',
        })
      );
    });
  });
});