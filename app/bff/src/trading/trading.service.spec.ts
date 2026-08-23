import { Test, TestingModule } from '@nestjs/testing';
import { TradingService } from './trading.service';
import { EngineClientService } from '../engine-client/engine-client.service';
import { RouterClientService } from '../router-client/router-client.service';
import { OrderRepository } from '../orders/repositories/order.repository';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { CONTRACT_TOPICS } from '../contracts/topics';
import type { OrderUpdateV1 } from '../contracts/gen';
import { createRouterPlacementIdentity } from './placement-identity';

describe('TradingService', () => {
  let service: TradingService;
  let routerClient: RouterClientService;
  let eventEmitter: EventEmitter2;
  const placementIdentity = createRouterPlacementIdentity('user-123', 'request-456', 1);

  const createOrderUpdate = (overrides: Partial<OrderUpdateV1> = {}): OrderUpdateV1 => ({
    version: '1.0.0',
    venue: 'USD_M',
    symbol: 'BTCUSDT',
    order_id: '',
    client_order_id: 'main-1',
    decision_id: '11111111-1111-4111-8111-111111111111',
    update_time: '2026-03-21T20:05:00Z',
    status: 'new',
    side: 'buy',
    order_type: 'limit',
    price: '45000',
    stop_price: null,
    quantity: '0.01',
    filled_quantity: '0',
    average_fill_price: null,
    commission: null,
    commission_asset: null,
    error_message: null,
    is_reduce_only: false,
    ...overrides,
  });

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
    findActivePositionSnapshots: jest.fn().mockResolvedValue([]),
    update: jest.fn(),
    withLockedOrderForUpdate: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    mockOrderRepository.findActivePositionSnapshots.mockReset().mockResolvedValue([]);
    mockOrderRepository.withLockedOrderForUpdate.mockReset().mockImplementation(
      async (
        identity: {
          venue: 'SPOT' | 'USD_M';
          symbol: string;
          clientOrderId: string;
          exchangeOrderId: string;
        },
        reconcile: (order: Record<string, unknown>) => Record<string, unknown> | null,
      ) => {
        const persisted =
          (identity.clientOrderId
            ? await mockOrderRepository.findByClientOrderId(identity.clientOrderId, identity.venue)
            : null) ??
          (identity.exchangeOrderId
            ? await mockOrderRepository.findByExchangeOrderId(
                identity.exchangeOrderId,
                identity.venue,
                identity.symbol,
              )
            : null);
        if (!persisted) {
          return null;
        }

        const updates = reconcile(persisted);
        if (updates === null) {
          return { order: persisted, updated: false };
        }
        await mockOrderRepository.update(persisted.orderId, updates);
        return { order: { ...persisted, ...updates }, updated: true };
      },
    );

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

      const result = await service.placeOrder(orderRequest, placementIdentity);

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
      expect(routerClient.placeOrder).toHaveBeenCalledWith(orderRequest, placementIdentity);
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

      const result = await service.placeOrder(orderRequest, placementIdentity);

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

      await expect(service.placeOrder(orderRequest, placementIdentity)).rejects.toThrow(
        'Insufficient balance',
      );
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

    it('rebuilds exact restart positions from authoritative venue snapshots', async () => {
      mockOrderRepository.findActivePositionSnapshots.mockResolvedValue([
        {
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'BUY',
          size: '1.10000000',
          entryPrice: '106.66666667',
          currentPrice: '106.66666667',
          unrealizedPnl: '0.00000000',
          updatedAt: new Date('2026-03-21T20:03:00Z'),
        },
        {
          venue: 'SPOT',
          symbol: 'BTCUSDT',
          side: 'BUY',
          size: '0.20000000',
          entryPrice: '50.00000000',
          currentPrice: '50.00000000',
          unrealizedPnl: '0.00000000',
          updatedAt: new Date('2026-03-21T20:01:30Z'),
        },
      ]);

      await service.onModuleInit();

      const positions = await service.getPositions();
      expect(positions).toHaveLength(2);
      expect(positions).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            side: 'LONG',
            quantity: 1.1,
            entryPrice: expect.closeTo(106.66666667, 7),
          }),
          expect.objectContaining({
            venue: 'SPOT',
            symbol: 'BTCUSDT',
            side: 'LONG',
            quantity: 0.2,
            entryPrice: 50,
          }),
        ]),
      );
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
      mockOrderRepository.findActivePositionSnapshots.mockResolvedValue([
        {
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'BUY',
          size: '0.01000000',
          entryPrice: '45010.50000000',
          currentPrice: '45010.50000000',
          unrealizedPnl: '0.00000000',
          updatedAt: new Date('2026-03-21T20:05:00Z'),
        },
      ]);
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

      subscribeCallback(orderUpdate);
      await new Promise(setImmediate);

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

    it('durably accepts an order update without duplicating the live websocket event', async () => {
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
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);
      const orderUpdate: OrderUpdateV1 = {
        version: '1.0.0',
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        order_id: 'exchange-789',
        client_order_id: 'main-1',
        decision_id: 'decision-1',
        update_time: '2026-03-21T20:05:00Z',
        status: 'new',
        side: 'buy',
        order_type: 'limit',
        price: '45000',
        stop_price: null,
        quantity: '0.01',
        filled_quantity: '0',
        average_fill_price: null,
        commission: null,
        commission_asset: null,
        error_message: null,
        is_reduce_only: false,
      };

      await expect(service.acceptOrderUpdate(orderUpdate)).resolves.toEqual({
        orderId: 'bracket-123',
        symbol: 'BTCUSDT',
        status: 'NEW',
        executedQty: 0,
        timestamp: Date.parse('2026-03-21T20:05:00Z'),
      });

      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'bracket-123',
        expect.objectContaining({
          status: 'NEW',
          exchangeOrderId: 'exchange-789',
        }),
      );
      expect(eventEmitter.emit).not.toHaveBeenCalledWith(
        CONTRACT_TOPICS.orderUpdateV1,
        expect.anything(),
      );
    });

    it('emits the live update when durable acceptance won the delivery race', async () => {
      let effectiveOrder = {
        orderId: 'bracket-123',
        clientOrderId: 'main-1',
        exchangeOrderId: null,
        decisionId: 'decision-1',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.withLockedOrderForUpdate.mockImplementation(
        async (_identity, reconcile) => {
          const updates = reconcile(effectiveOrder);
          if (updates === null) {
            return { order: effectiveOrder, updated: false };
          }
          effectiveOrder = { ...effectiveOrder, ...updates };
          return { order: effectiveOrder, updated: true };
        },
      );
      const orderUpdate = createOrderUpdate({
        order_id: 'exchange-789',
        decision_id: 'decision-1',
        status: 'filled',
        filled_quantity: '0.01',
        average_fill_price: '45010.5',
      });

      await service.acceptOrderUpdate(orderUpdate);
      mockEventEmitter.emit.mockClear();

      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.orderUpdateV1,
      )?.[1];
      subscribeCallback(orderUpdate);
      await new Promise(setImmediate);

      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, {
        orderId: 'bracket-123',
        symbol: 'BTCUSDT',
        status: 'FILLED',
        executedQty: 0.01,
        executedPrice: 45010.5,
        timestamp: Date.parse('2026-03-21T20:05:00Z'),
      });
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.positionUpdateV1, undefined);
    });

    it('keeps a filled projection terminal when the lost-response placement retries', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'bracket-123',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: 45010.5,
        status: 'FILLED',
        venue: 'USD_M',
        filledQuantity: 0.01,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:06:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);
      (service as any).activeOrders.set('order-row-123', {
        orderId: 'order-row-123',
        status: 'NEW',
      });

      await expect(service.acceptOrderUpdate(createOrderUpdate())).resolves.toEqual({
        orderId: 'order-row-123',
        symbol: 'BTCUSDT',
        status: 'FILLED',
        executedQty: 0.01,
        executedPrice: 45010.5,
        timestamp: Date.parse('2026-03-21T20:06:00Z'),
      });

      expect(mockOrderRepository.update).not.toHaveBeenCalled();
      await expect(service.getActiveOrders()).resolves.toEqual([]);
    });

    it.each(['CANCELED', 'REJECTED', 'EXPIRED'] as const)(
      'keeps a %s projection terminal when the original placement retries',
      async (terminalStatus) => {
        const persistedOrder = {
          orderId: 'order-row-123',
          clientOrderId: 'main-1',
          exchangeOrderId: 'bracket-123',
          decisionId: '11111111-1111-4111-8111-111111111111',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'LIMIT',
          quantity: 0.01,
          price: 45000,
          stopPrice: null,
          averageFillPrice: null,
          status: terminalStatus,
          venue: 'USD_M',
          filledQuantity: 0,
          createdAt: new Date('2026-03-21T20:00:00Z'),
          updatedAt: new Date('2026-03-21T20:06:00Z'),
          rejectReason: null,
          lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
        };
        mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

        await expect(service.acceptOrderUpdate(createOrderUpdate())).resolves.toEqual(
          expect.objectContaining({ status: terminalStatus }),
        );
        expect(mockOrderRepository.update).not.toHaveBeenCalled();
      },
    );

    it('acknowledges a synthetic placement replay against a partial fill as a no-op', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: 45005,
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: 0.006,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:06:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);
      (service as any).activeOrders.set('order-row-123', {
        orderId: 'order-row-123',
        status: 'NEW',
      });

      await expect(service.acceptOrderUpdate(createOrderUpdate())).resolves.toEqual({
        orderId: 'order-row-123',
        symbol: 'BTCUSDT',
        status: 'PARTIALLY_FILLED',
        executedQty: 0.006,
        executedPrice: 45005,
        timestamp: Date.parse('2026-03-21T20:06:00Z'),
      });

      expect(mockOrderRepository.update).not.toHaveBeenCalled();
      await expect(service.getActiveOrders()).resolves.toEqual([
        expect.objectContaining({
          orderId: 'order-row-123',
          status: 'PARTIALLY_FILLED',
          executedQty: 0.006,
        }),
      ]);
      await expect(service.getPositions()).resolves.toEqual([]);
    });

    it('preserves the greatest partial fill and its average price', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'bracket-123',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: 45005,
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: 0.006,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await service.acceptOrderUpdate(
        createOrderUpdate({
          update_time: '2026-03-21T20:06:00Z',
          status: 'partially_filled',
          filled_quantity: '0.004',
          average_fill_price: '45000',
        }),
      );

      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'order-row-123',
        expect.objectContaining({
          status: 'PARTIALLY_FILLED',
          filledQuantity: 0.006,
          averageFillPrice: 45005,
        }),
      );
    });

    it.each([
      ['PARTIALLY_FILLED', 'partially_filled', '0.50000000', 0.5],
      ['FILLED', 'filled', '1.00000000', 1],
    ] as const)(
      'accepts a newer same-quantity average-fill correction for %s',
      async (persistedStatus, incomingStatus, filledQuantity, executedQty) => {
        const persistedOrder = {
          orderId: 'order-row-123',
          clientOrderId: 'main-1',
          exchangeOrderId: 'exchange-789',
          decisionId: '11111111-1111-4111-8111-111111111111',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'LIMIT',
          quantity: '1.00000000',
          price: '45000.00000000',
          stopPrice: null,
          averageFillPrice: '45005.00000000',
          status: persistedStatus,
          venue: 'USD_M',
          filledQuantity,
          createdAt: new Date('2026-03-21T20:00:00Z'),
          updatedAt: new Date('2026-03-21T20:05:00Z'),
          rejectReason: null,
          lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
        };
        mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);
        mockOrderRepository.findActivePositionSnapshots.mockResolvedValue([
          {
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            side: 'BUY',
            size: filledQuantity,
            entryPrice: '45010.00000000',
            currentPrice: '45010.00000000',
            unrealizedPnl: '0.00000000',
            updatedAt: new Date('2026-03-21T20:06:00Z'),
          },
        ]);

        await expect(
          service.acceptOrderUpdate(
            createOrderUpdate({
              order_id: 'exchange-789',
              update_time: '2026-03-21T20:06:00Z',
              status: incomingStatus,
              quantity: '1.00000000',
              price: '45000.00000000',
              filled_quantity: filledQuantity,
              average_fill_price: '45010.00000000',
            }),
          ),
        ).resolves.toEqual({
          orderId: 'order-row-123',
          symbol: 'BTCUSDT',
          status: persistedStatus,
          executedQty,
          executedPrice: 45010,
          timestamp: Date.parse('2026-03-21T20:06:00Z'),
        });

        expect(mockOrderRepository.update).toHaveBeenCalledWith(
          'order-row-123',
          expect.objectContaining({
            averageFillPrice: '45010.00000000',
          }),
        );
        await expect(service.getPositions()).resolves.toEqual([
          expect.objectContaining({
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            quantity: executedQty,
            entryPrice: 45010,
            currentPrice: 45010,
          }),
        ]);
      },
    );

    it('rebuilds a filled position after an average correction without duplicating quantity', async () => {
      let effectiveOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '1.00000000',
        price: '45000.00000000',
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: '0.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:01:00Z'),
      };
      mockOrderRepository.withLockedOrderForUpdate.mockImplementation(
        async (_identity, reconcile) => {
          const updates = reconcile(effectiveOrder);
          if (updates === null) {
            return { order: effectiveOrder, updated: false };
          }
          effectiveOrder = { ...effectiveOrder, ...updates };
          return { order: effectiveOrder, updated: true };
        },
      );
      mockOrderRepository.findActivePositionSnapshots
        .mockResolvedValueOnce([
          {
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            side: 'BUY',
            size: '1.00000000',
            entryPrice: '45005.00000000',
            currentPrice: '45005.00000000',
            unrealizedPnl: '0.00000000',
            updatedAt: new Date('2026-03-21T20:05:00Z'),
          },
        ])
        .mockResolvedValueOnce([
          {
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            side: 'BUY',
            size: '1.00000000',
            entryPrice: '45010.00000000',
            currentPrice: '45010.00000000',
            unrealizedPnl: '0.00000000',
            updatedAt: new Date('2026-03-21T20:06:00Z'),
          },
        ]);

      await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          status: 'filled',
          quantity: '1.00000000',
          filled_quantity: '1.00000000',
          average_fill_price: '45005.00000000',
        }),
      );
      await expect(service.getPositions()).resolves.toEqual([
        expect.objectContaining({
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 1,
          entryPrice: 45005,
          currentPrice: 45005,
        }),
      ]);

      await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          update_time: '2026-03-21T20:06:00Z',
          status: 'filled',
          quantity: '1.00000000',
          filled_quantity: '1.00000000',
          average_fill_price: '45010.00000000',
        }),
      );

      await expect(service.getPositions()).resolves.toEqual([
        expect.objectContaining({
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 1,
          entryPrice: 45010,
          currentPrice: 45010,
        }),
      ]);
      expect(mockOrderRepository.findActivePositionSnapshots).toHaveBeenCalledTimes(2);
      expect(eventEmitter.emit).toHaveBeenLastCalledWith(
        CONTRACT_TOPICS.positionUpdateV1,
        expect.objectContaining({ quantity: 1, entryPrice: 45010 }),
      );
    });

    it('serializes position refreshes for concurrent orders on the same venue and symbol', async () => {
      const acceptedOrder = {
        orderId: 'order-row-1',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '1.00000000',
        price: '100.00000000',
        stopPrice: null,
        averageFillPrice: '100.00000000',
        status: 'FILLED',
        venue: 'USD_M',
        filledQuantity: '1.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      const firstSnapshot = {
        venue: 'USD_M',
        symbol: 'BTCUSDT',
        side: 'BUY',
        size: '1.00000000',
        entryPrice: '100.00000000',
        currentPrice: '100.00000000',
        unrealizedPnl: '0.00000000',
        updatedAt: new Date('2026-03-21T20:05:00Z'),
      };
      const finalSnapshot = {
        ...firstSnapshot,
        size: '1.50000000',
        entryPrice: '106.66666667',
        currentPrice: '106.66666667',
        updatedAt: new Date('2026-03-21T20:06:00Z'),
      };
      let releaseFirstRefresh: (snapshots: (typeof firstSnapshot)[]) => void = () => undefined;
      const delayedFirstRefresh = new Promise<(typeof firstSnapshot)[]>((resolve) => {
        releaseFirstRefresh = resolve;
      });
      mockOrderRepository.findActivePositionSnapshots
        .mockImplementationOnce(async () => delayedFirstRefresh)
        .mockResolvedValueOnce([finalSnapshot]);
      mockOrderRepository.withLockedOrderForUpdate.mockImplementation(async (identity) => ({
        order: {
          ...acceptedOrder,
          orderId: identity.clientOrderId === 'main-1' ? 'order-row-1' : 'order-row-2',
          clientOrderId: identity.clientOrderId,
          exchangeOrderId: identity.exchangeOrderId,
        },
        updated: true,
      }));

      const firstUpdate = service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          status: 'filled',
          quantity: '1.00000000',
          filled_quantity: '1.00000000',
          average_fill_price: '100.00000000',
        }),
      );
      await new Promise(setImmediate);
      const secondUpdate = service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-790',
          client_order_id: 'main-2',
          update_time: '2026-03-21T20:06:00Z',
          status: 'filled',
          quantity: '0.50000000',
          filled_quantity: '0.50000000',
          average_fill_price: '120.00000000',
        }),
      );
      await new Promise(setImmediate);
      releaseFirstRefresh([firstSnapshot]);
      await Promise.all([firstUpdate, secondUpdate]);

      await expect(service.getPositions()).resolves.toEqual([
        expect.objectContaining({
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 1.5,
          entryPrice: 106.66666667,
          currentPrice: 106.66666667,
        }),
      ]);
      expect(mockOrderRepository.findActivePositionSnapshots).toHaveBeenCalledTimes(2);
    });

    it('repairs a failed position refresh when the accepted order update is replayed', async () => {
      const filledOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '1.00000000',
        price: '100.00000000',
        stopPrice: null,
        averageFillPrice: '100.00000000',
        status: 'FILLED',
        venue: 'USD_M',
        filledQuantity: '1.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      mockOrderRepository.withLockedOrderForUpdate
        .mockResolvedValueOnce({ order: filledOrder, updated: true })
        .mockResolvedValueOnce({ order: filledOrder, updated: false });
      mockOrderRepository.findActivePositionSnapshots
        .mockRejectedValueOnce(new Error('projection read failed'))
        .mockResolvedValueOnce([
          {
            venue: 'USD_M',
            symbol: 'BTCUSDT',
            side: 'BUY',
            size: '1.00000000',
            entryPrice: '100.00000000',
            currentPrice: '100.00000000',
            unrealizedPnl: '0.00000000',
            updatedAt: new Date('2026-03-21T20:05:00Z'),
          },
        ]);
      const update = createOrderUpdate({
        order_id: 'exchange-789',
        status: 'filled',
        quantity: '1.00000000',
        filled_quantity: '1.00000000',
        average_fill_price: '100.00000000',
      });

      await expect(service.acceptOrderUpdate(update)).rejects.toThrow('projection read failed');
      await expect(service.acceptOrderUpdate(update)).resolves.toEqual(
        expect.objectContaining({ status: 'FILLED', executedQty: 1, executedPrice: 100 }),
      );

      await expect(service.getPositions()).resolves.toEqual([
        expect.objectContaining({
          venue: 'USD_M',
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 1,
          entryPrice: 100,
        }),
      ]);
      expect(mockOrderRepository.findActivePositionSnapshots).toHaveBeenCalledTimes(2);
    });

    it('rejects an average correction for an underfilled FILLED projection', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '1.00000000',
        price: '45000.00000000',
        stopPrice: null,
        averageFillPrice: '45005.00000000',
        status: 'FILLED',
        venue: 'USD_M',
        filledQuantity: '0.50000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(
          createOrderUpdate({
            order_id: 'exchange-789',
            update_time: '2026-03-21T20:06:00Z',
            status: 'filled',
            quantity: '1.00000000',
            price: '45000.00000000',
            filled_quantity: '0.50000000',
            average_fill_price: '45010.00000000',
          }),
        ),
      ).resolves.toBeNull();
      expect(mockOrderRepository.update).not.toHaveBeenCalled();
      await expect(service.getPositions()).resolves.toEqual([]);
    });

    it('ignores a stale terminal update and returns the newer active projection', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: 45005,
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: 0.006,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:06:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(
          createOrderUpdate({
            order_id: 'exchange-789',
            update_time: '2026-03-21T20:05:00Z',
            status: 'cancelled',
            filled_quantity: '0.004',
            average_fill_price: '45000',
          }),
        ),
      ).resolves.toEqual({
        orderId: 'order-row-123',
        symbol: 'BTCUSDT',
        status: 'PARTIALLY_FILLED',
        executedQty: 0.006,
        executedPrice: 45005,
        timestamp: Date.parse('2026-03-21T20:06:00Z'),
      });

      expect(mockOrderRepository.update).not.toHaveBeenCalled();
      await expect(service.getActiveOrders()).resolves.toEqual([
        expect.objectContaining({ orderId: 'order-row-123', status: 'PARTIALLY_FILLED' }),
      ]);
    });

    it('emits the newer active projection for a stale live terminal update', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: 45005,
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: 0.006,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:06:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:06:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);
      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.orderUpdateV1,
      )?.[1];

      subscribeCallback(
        createOrderUpdate({
          order_id: 'exchange-789',
          update_time: '2026-03-21T20:05:00Z',
          status: 'rejected',
          error_message: 'stale rejection',
        }),
      );
      await new Promise(setImmediate);

      expect(mockOrderRepository.update).not.toHaveBeenCalled();
      expect(eventEmitter.emit).toHaveBeenCalledWith(CONTRACT_TOPICS.orderUpdateV1, {
        orderId: 'order-row-123',
        symbol: 'BTCUSDT',
        status: 'PARTIALLY_FILLED',
        executedQty: 0.006,
        executedPrice: 45005,
        timestamp: Date.parse('2026-03-21T20:06:00Z'),
      });
    });

    it('preserves the authoritative exchange identifier on placement acceptance', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'bracket-123',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await service.acceptOrderUpdate(createOrderUpdate());

      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'order-row-123',
        expect.objectContaining({ exchangeOrderId: 'bracket-123' }),
      );
    });

    it('rejects adjacent high-precision prices as distinct immutable identity', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '0.01000000',
        price: '9999999999.00000001',
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: '0.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(
          createOrderUpdate({
            order_id: 'exchange-789',
            price: '9999999999.00000002',
          }),
        ),
      ).resolves.toBeNull();
      expect(mockOrderRepository.update).not.toHaveBeenCalled();
    });

    it('does not rewrite exact persisted decimals for a status-only update', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '0.01000000',
        price: '9999999999.00000001',
        stopPrice: null,
        averageFillPrice: '9999999999.00000001',
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: '0.00600000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          update_time: '2026-03-21T20:06:00Z',
          status: 'cancelled',
          price: '9999999999.00000001',
          filled_quantity: '0.00600000',
          average_fill_price: '9999999999.00000001',
        }),
      );

      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'order-row-123',
        expect.not.objectContaining({
          filledQuantity: expect.anything(),
          averageFillPrice: expect.anything(),
        }),
      );
    });

    it('persists an increased fill using its exact decimal string', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '1.00000000',
        price: '9999999999.00000001',
        stopPrice: null,
        averageFillPrice: '9999999999.00000001',
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: '0.12345678',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:05:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          update_time: '2026-03-21T20:06:00Z',
          quantity: '1.00000000',
          price: '9999999999.00000001',
          filled_quantity: '0.12345679',
          average_fill_price: '9999999999.00000002',
        }),
      );

      expect(mockOrderRepository.update).toHaveBeenCalledWith(
        'order-row-123',
        expect.objectContaining({
          filledQuantity: '0.12345679',
          averageFillPrice: '9999999999.00000002',
        }),
      );
    });

    it('does not let a synthetic placement timestamp suppress an earlier exchange fill', async () => {
      let persistedOrder: Record<string, unknown> = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: null,
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '0.01000000',
        price: '45000.00000000',
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: '0.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:00:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findByClientOrderId.mockImplementation(async () => persistedOrder);
      mockOrderRepository.withLockedOrderForUpdate.mockImplementation(
        async (_identity, reconcile) => {
          const updates = reconcile(persistedOrder);
          if (updates === null) {
            return { order: persistedOrder, updated: false };
          }
          persistedOrder = { ...persistedOrder, ...updates };
          return { order: persistedOrder, updated: true };
        },
      );

      await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: '',
          update_time: '2026-03-21T20:06:00Z',
        }),
      );
      const fill = await service.acceptOrderUpdate(
        createOrderUpdate({
          order_id: 'exchange-789',
          update_time: '2026-03-21T20:05:00Z',
          status: 'filled',
          filled_quantity: '0.01000000',
          average_fill_price: '45001.00000000',
        }),
      );

      expect(fill).toEqual(
        expect.objectContaining({
          status: 'FILLED',
          executedQty: 0.01,
          executedPrice: 45001,
        }),
      );
      expect(persistedOrder).toEqual(
        expect.objectContaining({
          exchangeOrderId: 'exchange-789',
          status: 'FILLED',
          filledQuantity: '0.01000000',
          averageFillPrice: '45001.00000000',
          lastUpdateTime: new Date('2026-03-21T20:05:00Z'),
        }),
      );
    });

    it.each([
      [
        'filled with zero quantity',
        { status: 'filled', filled_quantity: '0', average_fill_price: null },
      ],
      [
        'filled above order quantity',
        { status: 'filled', filled_quantity: '0.02', average_fill_price: '45000' },
      ],
      [
        'partial fill equal to order quantity',
        { status: 'partially_filled', filled_quantity: '0.01', average_fill_price: '45000' },
      ],
      [
        'partial fill with zero quantity',
        { status: 'partially_filled', filled_quantity: '0', average_fill_price: null },
      ],
      [
        'new status with a fill',
        { status: 'new', filled_quantity: '0.001', average_fill_price: '45000' },
      ],
      [
        'average price without a fill',
        { status: 'new', filled_quantity: '0', average_fill_price: '45000' },
      ],
    ] as const)('rejects impossible %s state before terminalization', async (_case, overrides) => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '0.01000000',
        price: '45000.00000000',
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: '0.00000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:00:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(
          createOrderUpdate({
            order_id: 'exchange-789',
            ...overrides,
          } as Partial<OrderUpdateV1>),
        ),
      ).resolves.toBeNull();
      expect(mockOrderRepository.update).not.toHaveBeenCalled();
    });

    it('does not preserve an already overfilled projection through a terminal update', async () => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'exchange-789',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: '0.01000000',
        price: '45000.00000000',
        stopPrice: null,
        averageFillPrice: '45000.00000000',
        status: 'PARTIALLY_FILLED',
        venue: 'USD_M',
        filledQuantity: '0.02000000',
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:00:00Z'),
        rejectReason: null,
        lastUpdateTime: new Date('2026-03-21T20:04:00Z'),
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(
          createOrderUpdate({
            order_id: 'exchange-789',
            update_time: '2026-03-21T20:05:00Z',
            status: 'cancelled',
            filled_quantity: '0.02000000',
            average_fill_price: '45000.00000000',
          }),
        ),
      ).resolves.toBeNull();
      expect(mockOrderRepository.update).not.toHaveBeenCalled();
    });

    it.each([
      ['venue', { venue: 'SPOT' }],
      ['symbol', { symbol: 'ETHUSDT' }],
      ['side', { side: 'sell' }],
      ['type', { order_type: 'market' }],
      ['quantity', { quantity: '0.02' }],
      ['decision', { decision_id: '22222222-2222-4222-8222-222222222222' }],
      ['exchange order', { order_id: 'exchange-conflict' }],
      ['price', { price: '45001' }],
      ['stop price', { stop_price: '44000' }],
    ] as const)('rejects divergent immutable %s identity', async (_field, overrides) => {
      const persistedOrder = {
        orderId: 'order-row-123',
        clientOrderId: 'main-1',
        exchangeOrderId: 'bracket-123',
        decisionId: '11111111-1111-4111-8111-111111111111',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 0.01,
        price: 45000,
        stopPrice: null,
        averageFillPrice: null,
        status: 'NEW',
        venue: 'USD_M',
        filledQuantity: 0,
        createdAt: new Date('2026-03-21T20:00:00Z'),
        updatedAt: new Date('2026-03-21T20:01:00Z'),
        rejectReason: null,
        lastUpdateTime: null,
      };
      mockOrderRepository.findByClientOrderId.mockResolvedValue(persistedOrder);

      await expect(
        service.acceptOrderUpdate(createOrderUpdate(overrides as Partial<OrderUpdateV1>)),
      ).resolves.toBeNull();
      expect(mockOrderRepository.update).not.toHaveBeenCalled();
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

      expect(routerClient.placeOrder).toHaveBeenCalledWith(
        {
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'MARKET',
          quantity: 0.01,
          stopLossPrice: 44000,
          takeProfitPrice: 47000,
          venue: 'USD_M',
        },
        expect.any(Object),
      );
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

  describe('engine event containment', () => {
    // Regression: 2026-07-11 soak — async engine-event listeners with
    // unhandled rejections kill the whole Node process.
    const flushMicrotasks = async () => {
      await Promise.resolve();
      await Promise.resolve();
    };

    it('contains order-update handler failures instead of crashing', async () => {
      const errorSpy = jest.spyOn((service as any).logger, 'error').mockImplementation();
      jest.spyOn(service as any, 'handleOrderUpdate').mockRejectedValue(new Error('db down'));

      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.orderUpdateV1,
      )?.[1];
      expect(subscribeCallback).toBeDefined();

      const result = subscribeCallback({ client_order_id: 'x' });
      await flushMicrotasks();

      expect(result).toBeUndefined();
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('order update'));
    });

    it('contains decision handler failures instead of crashing', async () => {
      const errorSpy = jest.spyOn((service as any).logger, 'error').mockImplementation();
      jest.spyOn(service as any, 'handleDecisionEvent').mockRejectedValue(new Error('db down'));

      const subscribeCallback = mockEngineClientService.subscribe.mock.calls.find(
        (call) => call[0] === CONTRACT_TOPICS.decisionV1,
      )?.[1];
      expect(subscribeCallback).toBeDefined();

      const result = subscribeCallback({ symbol: 'BTCUSDT' });
      await flushMicrotasks();

      expect(result).toBeUndefined();
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('decision'));
    });
  });
});
