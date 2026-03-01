import { Test, TestingModule } from '@nestjs/testing';
import { TradingService } from './trading.service';
import { EngineClientService } from '../engine-client/engine-client.service';
import { RouterClientService } from '../router-client/router-client.service';
import { OrderRepository } from '../orders/repositories/order.repository';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CONTRACT_TOPICS } from '../contracts/topics';

describe('TradingService', () => {
  let service: TradingService;
  let routerClient: RouterClientService;
  let eventEmitter: EventEmitter2;

  const mockEngineClientService = {
    subscribe: jest.fn(),
    publish: jest.fn(),
  };

  const mockRouterClientService = {
    placeOrder: jest.fn(),
    getOrderStatus: jest.fn(),
    cancelOrder: jest.fn(),
    closeAllPositions: jest.fn(),
  };

  const mockEventEmitter = {
    emit: jest.fn(),
    on: jest.fn(),
  };

  const mockOrderRepository = {
    save: jest.fn(),
    findOne: jest.fn(),
    find: jest.fn(),
    findActiveOrders: jest.fn().mockResolvedValue([]),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TradingService,
        {
          provide: EngineClientService,
          useValue: mockEngineClientService,
        },
        {
          provide: RouterClientService,
          useValue: mockRouterClientService,
        },
        {
          provide: EventEmitter2,
          useValue: mockEventEmitter,
        },
        {
          provide: OrderRepository,
          useValue: mockOrderRepository,
        },
      ],
    }).compile();

    service = module.get<TradingService>(TradingService);
    routerClient = module.get<RouterClientService>(RouterClientService);
    eventEmitter = module.get<EventEmitter2>(EventEmitter2);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('placeOrder', () => {
    it('should place a market order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
      };

      const orderResponse = {
        orderId: '123456',
        status: 'NEW',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      const result = await service.placeOrder(orderRequest);

      expect(result).toEqual(orderResponse);
      expect(routerClient.placeOrder).toHaveBeenCalledWith(orderRequest);
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, orderResponse);
    });

    it('should place a limit order with price', async () => {
      const orderRequest = {
        symbol: 'ETHUSDT',
        side: 'SELL' as const,
        type: 'LIMIT' as const,
        quantity: 1,
        price: 3000,
        venue: 'SPOT' as const,
      };

      const orderResponse = {
        orderId: '789012',
        status: 'NEW',
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 1,
        price: 3000,
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      const result = await service.placeOrder(orderRequest);

      expect(result).toEqual(orderResponse);
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, orderResponse);
    });

    it('should handle order placement errors', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
      };

      const error = new Error('Insufficient balance');
      mockRouterClientService.placeOrder.mockRejectedValue(error);

      await expect(service.placeOrder(orderRequest)).rejects.toThrow('Insufficient balance');
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderFailedV1, {
        request: orderRequest,
        error: 'Insufficient balance',
      });
    });
  });

  describe('getOrderStatus', () => {
    it('should get order status successfully', async () => {
      const orderId = '123456';
      const venue = 'USD_M' as const;

      const orderStatus = {
        orderId: '123456',
        status: 'FILLED',
        executedQty: 0.01,
        cummulativeQuoteQty: 450,
      };

      mockRouterClientService.getOrderStatus.mockResolvedValue(orderStatus);

      const result = await service.getOrderStatus(orderId, venue);

      expect(result).toEqual(orderStatus);
      expect(routerClient.getOrderStatus).toHaveBeenCalledWith(orderId, venue);
    });
  });

  describe('cancelOrder', () => {
    it('should cancel order successfully', async () => {
      const orderId = '123456';
      const symbol = 'BTCUSDT';
      const venue = 'USD_M' as const;

      const cancelResponse = {
        orderId: '123456',
        status: 'CANCELED',
      };

      mockRouterClientService.cancelOrder.mockResolvedValue(cancelResponse);

      const result = await service.cancelOrder(orderId, symbol, venue);

      expect(result).toEqual(cancelResponse);
      expect(routerClient.cancelOrder).toHaveBeenCalledWith(orderId, symbol, venue);
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, cancelResponse);
    });
  });

  describe('getPositions', () => {
    it('should return current positions', async () => {
      const positions = [
        {
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 0.01,
          entryPrice: 45000,
          currentPrice: 46000,
          pnl: 10,
          pnlPercent: 2.22,
        },
      ];

      // Mock internal positions state
      (service as any).positions = new Map([['BTCUSDT', positions[0]]]);

      const result = await service.getPositions();

      expect(result).toEqual(positions);
    });
  });

  describe('engine event handling', () => {
    it('should handle decision events from engine', () => {
      const decisionEvent = {
        symbol: 'BTCUSDT',
        action: 'BUY' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
        type: 'MARKET' as const,
        confidence: 0.85,
      };

      // Get the callback registered for decision.v1 events
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'decision.v1',
      )?.[1];

      expect(subscribeCallback).toBeDefined();

      // Simulate decision event
      subscribeCallback(decisionEvent);

      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.decisionV1, decisionEvent);
    });

    it('should handle order update events from engine', () => {
      const orderUpdate = {
        orderId: '123456',
        symbol: 'BTCUSDT',
        status: 'FILLED',
        executedQty: 0.01,
        executedPrice: 45000,
      };

      // Get the callback registered for order_update.v1 events
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'order_update.v1',
      )?.[1];

      expect(subscribeCallback).toBeDefined();

      // Simulate order update event
      subscribeCallback(orderUpdate);

      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, orderUpdate);
    });
  });

  describe('auto trading', () => {
    it('should execute trades based on decision events when auto trading is enabled', async () => {
      await service.setAutoTrading(true);

      const decisionEvent = {
        symbol: 'BTCUSDT',
        action: 'BUY' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
        type: 'MARKET' as const,
        confidence: 0.85,
      };

      const orderResponse = {
        orderId: '123456',
        status: 'NEW',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      await service.handleDecisionEvent(decisionEvent);

      expect(routerClient.placeOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        venue: 'USD_M',
      });
    });

    it('should not execute trades when auto trading is disabled', async () => {
      await service.setAutoTrading(false);

      const decisionEvent = {
        symbol: 'BTCUSDT',
        action: 'BUY' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
        type: 'MARKET' as const,
        confidence: 0.85,
      };

      await service.handleDecisionEvent(decisionEvent);

      expect(routerClient.placeOrder).not.toHaveBeenCalled();
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.decisionSkippedV1, {
        reason: 'Auto trading disabled',
        decision: decisionEvent,
      });
    });
  });

  describe('emergencyClose', () => {
    it('should close ALL positions (spot and futures)', async () => {
      mockRouterClientService.closeAllPositions.mockResolvedValue({
        success: true,
        message: 'Closed',
      });

      const result = await service.emergencyClose('ALL');

      expect(result.success).toBe(true);
      expect(result.closedCount).toBe(2);
      expect(routerClient.closeAllPositions).toHaveBeenCalledTimes(2);
      expect(routerClient.closeAllPositions).toHaveBeenCalledWith({ is_futures: false });
      expect(routerClient.closeAllPositions).toHaveBeenCalledWith({ is_futures: true });
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        'emergency.close',
        expect.objectContaining({
          scope: 'ALL',
          closedCount: 2,
        }),
      );
    });

    it('should close SPOT positions only', async () => {
      mockRouterClientService.closeAllPositions.mockResolvedValue({
        success: true,
        message: 'Closed',
      });

      const result = await service.emergencyClose('SPOT');

      expect(result.success).toBe(true);
      expect(result.closedCount).toBe(1);
      expect(routerClient.closeAllPositions).toHaveBeenCalledTimes(1);
      expect(routerClient.closeAllPositions).toHaveBeenCalledWith({ is_futures: false });
    });

    it('should close FUTURES positions only', async () => {
      mockRouterClientService.closeAllPositions.mockResolvedValue({
        success: true,
        message: 'Closed',
      });

      const result = await service.emergencyClose('FUTURES');

      expect(result.success).toBe(true);
      expect(result.closedCount).toBe(1);
      expect(routerClient.closeAllPositions).toHaveBeenCalledTimes(1);
      expect(routerClient.closeAllPositions).toHaveBeenCalledWith({ is_futures: true });
    });

    it('should stop auto trading when stopEngine is true', async () => {
      mockRouterClientService.closeAllPositions.mockResolvedValue({
        success: true,
        message: 'Closed',
      });

      await service.setAutoTrading(true);
      expect(service.isAutoTradingEnabled()).toBe(true);

      await service.emergencyClose('ALL', true);

      expect(service.isAutoTradingEnabled()).toBe(false);
    });

    it('should emit emergency.close.failed on error', async () => {
      mockRouterClientService.closeAllPositions.mockRejectedValue(new Error('Network error'));

      await expect(service.emergencyClose('ALL')).rejects.toThrow('Network error');
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        'emergency.close.failed',
        expect.objectContaining({
          scope: 'ALL',
          error: 'Network error',
        }),
      );
    });
  });
});
