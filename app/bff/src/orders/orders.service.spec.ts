import { Test, TestingModule } from '@nestjs/testing';
import { OrdersService } from './orders.service';
import { OrderRepository } from './repositories/order.repository';
import { OrderEntity, OrderStatus } from './entities/order-entity';

describe('OrdersService', () => {
  let service: OrdersService;
  let orderRepository: OrderRepository;

  const mockOrderEntities: OrderEntity[] = [
    {
      orderId: '1',
      clientOrderId: 'client-123',
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      status: 'FILLED',
      venue: 'SPOT',
      price: 45000,
      quantity: 0.5,
      filledQuantity: 0.5,
      commission: 0.0005,
      commissionAsset: 'BTC',
      createdAt: new Date(Date.now() - 3600000),
      updatedAt: new Date(Date.now() - 3500000),
      timeInForce: 'GTC',
      stopPrice: null,
      decisionId: null,
      exchangeOrderId: 'exchange-123',
      lastUpdateTime: null,
      reduceOnly: false,
      postOnly: false,
      closePosition: false,
      activationPrice: null,
      callbackRate: null,
      workingType: null,
      priceProtect: false,
      rejectReason: null,
      averageFillPrice: 45000,
    } as OrderEntity,
    {
      orderId: '2',
      clientOrderId: 'client-124',
      symbol: 'ETHUSDT',
      side: 'SELL',
      type: 'MARKET',
      status: 'FILLED',
      venue: 'SPOT',
      quantity: 2,
      filledQuantity: 2,
      commission: 0.002,
      commissionAsset: 'ETH',
      createdAt: new Date(Date.now() - 7200000),
      updatedAt: new Date(Date.now() - 7100000),
      price: null,
      stopPrice: null,
      timeInForce: 'GTC',
      decisionId: null,
      exchangeOrderId: 'exchange-124',
      lastUpdateTime: null,
      reduceOnly: false,
      postOnly: false,
      closePosition: false,
      activationPrice: null,
      callbackRate: null,
      workingType: null,
      priceProtect: false,
      rejectReason: null,
      averageFillPrice: 3000,
    } as OrderEntity,
    {
      orderId: '3',
      clientOrderId: 'client-125',
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      status: 'NEW',
      venue: 'USD_M',
      price: 44500,
      quantity: 1,
      filledQuantity: 0,
      commission: 0,
      commissionAsset: null,
      createdAt: new Date(Date.now() - 600000),
      updatedAt: new Date(Date.now() - 600000),
      stopPrice: null,
      timeInForce: 'GTC',
      decisionId: null,
      exchangeOrderId: 'exchange-125',
      lastUpdateTime: null,
      reduceOnly: false,
      postOnly: false,
      closePosition: false,
      activationPrice: null,
      callbackRate: null,
      workingType: null,
      priceProtect: false,
      rejectReason: null,
      averageFillPrice: null,
    } as OrderEntity,
  ];

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OrdersService,
        {
          provide: OrderRepository,
          useValue: {
            findAll: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get<OrdersService>(OrdersService);
    orderRepository = module.get<OrderRepository>(OrderRepository);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getOrders', () => {
    it('fetches all orders from repository', async () => {
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce(mockOrderEntities);

      const result = await service.getOrders({});

      expect(orderRepository.findAll).toHaveBeenCalledWith({
        venue: undefined,
        symbol: undefined,
        status: undefined,
        limit: 100,
      });
      expect(result).toHaveLength(3);
      expect(result[0]).toMatchObject({
        id: '1',
        clientOrderId: 'client-123',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'LIMIT',
        status: 'FILLED',
      });
    });

    it('filters by venue when specified', async () => {
      const spotOrders = mockOrderEntities.filter((e) => e.venue === 'SPOT');
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce(spotOrders);

      const result = await service.getOrders({ venue: 'SPOT' });

      expect(orderRepository.findAll).toHaveBeenCalledWith({
        venue: 'SPOT',
        symbol: undefined,
        status: undefined,
        limit: 100,
      });
      expect(result).toHaveLength(2);
      expect(result.every((o) => o.venue === 'SPOT')).toBe(true);
    });

    it('filters by status when specified', async () => {
      const filledOrders = mockOrderEntities.filter((e) => e.status === 'FILLED');
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce(filledOrders);

      const result = await service.getOrders({ status: 'FILLED' as OrderStatus });

      expect(orderRepository.findAll).toHaveBeenCalledWith({
        venue: undefined,
        symbol: undefined,
        status: 'FILLED',
        limit: 100,
      });
      expect(result).toHaveLength(2);
      expect(result.every((o) => o.status === 'FILLED')).toBe(true);
    });

    it('filters by symbol when specified', async () => {
      const btcOrders = mockOrderEntities.filter((e) => e.symbol === 'BTCUSDT');
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce(btcOrders);

      const result = await service.getOrders({ symbol: 'BTCUSDT' });

      expect(orderRepository.findAll).toHaveBeenCalledWith({
        venue: undefined,
        symbol: 'BTCUSDT',
        status: undefined,
        limit: 100,
      });
      expect(result).toHaveLength(2);
      expect(result.every((o) => o.symbol === 'BTCUSDT')).toBe(true);
    });

    it('respects limit parameter', async () => {
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce([mockOrderEntities[0]]);

      const result = await service.getOrders({ limit: 1 });

      expect(orderRepository.findAll).toHaveBeenCalledWith({
        venue: undefined,
        symbol: undefined,
        status: undefined,
        limit: 1,
      });
      expect(result).toHaveLength(1);
    });

    it('returns empty array when no orders exist', async () => {
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce([]);

      const result = await service.getOrders({});

      expect(result).toHaveLength(0);
    });

    it('handles optional price field correctly', async () => {
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce([mockOrderEntities[1]]);

      const result = await service.getOrders({});

      expect(result[0].price).toBeUndefined();
    });

    it('handles optional feeAsset field correctly', async () => {
      jest.spyOn(orderRepository, 'findAll').mockResolvedValueOnce([mockOrderEntities[2]]);

      const result = await service.getOrders({});

      expect(result[0].feeAsset).toBeUndefined();
    });
  });
});
