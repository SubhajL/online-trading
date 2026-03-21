import { Test, TestingModule } from '@nestjs/testing';
import { TradingService } from './trading.service';
import { EngineClientService } from '../engine-client/engine-client.service';
import { RouterClientService } from '../router-client/router-client.service';
import { OrderRepository } from '../orders/repositories/order.repository';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CONTRACT_TOPICS } from '../contracts/topics';
import type { OrderUpdateV1 } from '../contracts/gen';

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
    cancelOrder: jest.fn(),
    closeAllPositions: jest.fn(),
  };

  const mockEventEmitter = {
    emit: jest.fn(),
    on: jest.fn(),
  };

  const mockOrderRepository = {
    save: jest.fn(),
    findByOrderId: jest.fn(),
    findByClientOrderId: jest.fn(),
    findByExchangeOrderId: jest.fn(),
    find: jest.fn(),
    findActiveOrders: jest.fn().mockResolvedValue([]),
    update: jest.fn(),
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
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'USD_M' as const,
      };

      const orderResponse = {
        bracket_order_id: '123456',
        client_order_ids: {
          main: 'main-1',
          take_profits: ['tp-1'],
          stop_loss: 'sl-1',
        },
        symbol: 'BTCUSDT',
        side: 'BUY',
        quantity: 0.01,
        created_at: '2026-03-21T20:00:00Z',
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      const result = await service.placeOrder(orderRequest);

      expect(result).toEqual(
        expect.objectContaining({
          orderId: '123456',
          status: 'NEW',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'MARKET',
          quantity: 0.01,
          venue: 'USD_M',
        }),
      );
      expect(routerClient.placeOrder).toHaveBeenCalledWith(orderRequest);
      expect(mockOrderRepository.save).toHaveBeenCalledWith(
        expect.objectContaining({
          orderId: '123456',
          clientOrderId: 'main-1',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'MARKET',
          quantity: 0.01,
          stopPrice: 44000,
          venue: 'USD_M',
          status: 'NEW',
        }),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        CONTRACT_TOPICS.orderUpdateV1,
        expect.objectContaining({ orderId: '123456', status: 'NEW' }),
      );
    });

    it('should place a limit order with price', async () => {
      const orderRequest = {
        symbol: 'ETHUSDT',
        side: 'SELL' as const,
        type: 'LIMIT' as const,
        quantity: 1,
        price: 3000,
        stopLossPrice: 3100,
        takeProfitPrice: 2800,
        venue: 'SPOT' as const,
      };

      const orderResponse = {
        bracket_order_id: '789012',
        client_order_ids: {
          main: 'main-2',
          take_profits: ['tp-2'],
          stop_loss: 'sl-2',
        },
        symbol: 'ETHUSDT',
        side: 'SELL',
        quantity: 1,
        created_at: '2026-03-21T20:00:00Z',
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      const result = await service.placeOrder(orderRequest);

      expect(result).toEqual(
        expect.objectContaining({
          orderId: '789012',
          status: 'NEW',
          symbol: 'ETHUSDT',
          side: 'SELL',
          type: 'LIMIT',
          quantity: 1,
          price: 3000,
        }),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        CONTRACT_TOPICS.orderUpdateV1,
        expect.objectContaining({ orderId: '789012', status: 'NEW' }),
      );
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
        clientOrderId: 'main-1',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        status: 'FILLED',
        venue,
        filledQuantity: 0.01,
        averageFillPrice: 45000,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
      };

      mockOrderRepository.findByOrderId.mockResolvedValue(orderStatus);

      const result = await service.getOrderStatus(orderId, venue);

      expect(result).toEqual(
        expect.objectContaining({
          orderId: '123456',
          status: 'FILLED',
          executedQty: 0.01,
          price: 45000,
        }),
      );
      expect(mockOrderRepository.findByOrderId).toHaveBeenCalledWith(orderId, venue);
    });
  });

  describe('cancelOrder', () => {
    it('should cancel order successfully', async () => {
      const orderId = '123456';
      const symbol = 'BTCUSDT';
      const venue = 'USD_M' as const;

      mockOrderRepository.findByOrderId.mockResolvedValue({
        orderId: '123456',
        clientOrderId: 'main-1',
        exchangeOrderId: '987654',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        status: 'NEW',
        venue,
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
      });

      mockRouterClientService.cancelOrder.mockResolvedValue({ success: true });

      const result = await service.cancelOrder(orderId, symbol, venue);

      expect(result).toEqual(
        expect.objectContaining({
          orderId: '123456',
          status: 'CANCELED',
        }),
      );
      expect(routerClient.cancelOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        venue,
        orderId: '123456',
        exchangeOrderId: '987654',
        clientOrderId: 'main-1',
      });
      expect(mockOrderRepository.update).toHaveBeenCalledWith('123456', expect.any(Object));
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        CONTRACT_TOPICS.orderUpdateV1,
        expect.objectContaining({ orderId: '123456', status: 'CANCELED' }),
      );
    });

    it('should fall back to client order id when exchange id is unavailable', async () => {
      mockOrderRepository.findByOrderId.mockResolvedValue({
        orderId: 'order-spot-1',
        clientOrderId: 'main-spot-1',
        exchangeOrderId: null,
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'LIMIT',
        quantity: 0.5,
        price: 3000,
        status: 'NEW',
        venue: 'SPOT',
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
      });
      mockRouterClientService.cancelOrder.mockResolvedValue({ success: true });

      await service.cancelOrder('order-spot-1', 'IGNORED', 'SPOT');

      expect(routerClient.cancelOrder).toHaveBeenCalledWith({
        symbol: 'ETHUSDT',
        venue: 'SPOT',
        orderId: 'order-spot-1',
        exchangeOrderId: null,
        clientOrderId: 'main-spot-1',
      });
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

    it('should register an order update subscription', () => {
      // Get the callback registered for order_update.v1 events
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === 'order_update.v1',
      )?.[1];

      expect(subscribeCallback).toBeDefined();
    });

    it('should normalize live order_update.v1 events and persist them by client order id', async () => {
      const persistedOrder = {
        orderId: 'bracket-123',
        clientOrderId: 'main-1',
        exchangeOrderId: null,
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findActiveOrders.mockResolvedValue([persistedOrder]);
      await service.onModuleInit();
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      const orderUpdate: OrderUpdateV1 = {
        version: '1.0.0',
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        order_id: 'exchange-789',
        client_order_id: 'main-1',
        decision_id: 'decision-1',
        update_time: '2026-03-21T20:05:00Z',
        status: 'filled',
        side: 'buy',
        order_type: 'limit',
        price: '45000',
        stop_price: null,
        quantity: '0.01',
        filled_quantity: '0.01',
        average_fill_price: '45010.5',
        commission: null,
        commission_asset: null,
        error_message: null,
        is_reduce_only: false,
      };

      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.orderUpdateV1,
      )?.[1];

      expect(subscribeCallback).toBeDefined();

      await subscribeCallback(orderUpdate);

      expect(mockOrderRepository.findByClientOrderId).toHaveBeenCalledWith('main-1', 'USD_M');
      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'bracket-123',
        expect.objectContaining({
          status: 'FILLED',
          filledQuantity: 0.01,
          averageFillPrice: 45010.5,
          exchangeOrderId: 'exchange-789',
        }),
      );
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, {
        orderId: 'bracket-123',
        symbol: 'BTCUSDT',
        status: 'FILLED',
        executedQty: 0.01,
        executedPrice: 45010.5,
        timestamp: Date.parse('2026-03-21T20:05:00Z'),
      });
      expect(eventEmitter.emit).toHaveBeenCalledWith(
        CONTRACT_TOPICS.positionUpdateV1,
        expect.objectContaining({
          symbol: 'BTCUSDT',
          side: 'LONG',
          entryPrice: 45010.5,
          quantity: 0.01,
        }),
      );
      await expect(service.getActiveOrders()).resolves.toEqual([]);
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
        stopLoss: 44000,
        takeProfit: 47000,
        confidence: 0.85,
      };

      const orderResponse = {
        bracket_order_id: '123456',
        client_order_ids: {
          main: 'main-1',
          take_profits: ['tp-1'],
          stop_loss: 'sl-1',
        },
        symbol: 'BTCUSDT',
        side: 'BUY',
        quantity: 0.01,
        created_at: '2026-03-21T20:00:00Z',
      };

      mockRouterClientService.placeOrder.mockResolvedValue(orderResponse);

      await service.handleDecisionEvent(decisionEvent);

      expect(routerClient.placeOrder).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
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
