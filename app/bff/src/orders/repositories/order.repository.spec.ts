import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { OrderRepository } from './order.repository';
import { OrderEntity } from '../entities/order-entity';
import type { OrderStatus, Venue } from '../entities/order-entity';
import { Repository } from 'typeorm';

describe('OrderRepository', () => {
  let orderRepository: OrderRepository;
  let mockRepository: Repository<OrderEntity>;

  const mockQueryBuilder = {
    where: jest.fn().mockReturnThis(),
    andWhere: jest.fn().mockReturnThis(),
    orderBy: jest.fn().mockReturnThis(),
    limit: jest.fn().mockReturnThis(),
    getMany: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OrderRepository,
        {
          provide: getRepositoryToken(OrderEntity),
          useValue: {
            createQueryBuilder: jest.fn(() => mockQueryBuilder),
            findOne: jest.fn(),
            save: jest.fn(),
            update: jest.fn(),
          },
        },
      ],
    }).compile();

    orderRepository = module.get<OrderRepository>(OrderRepository);
    mockRepository = module.get<Repository<OrderEntity>>(getRepositoryToken(OrderEntity));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('findAll', () => {
    it('should find all orders ordered by date', async () => {
      const mockOrders: OrderEntity[] = [
        {
          orderId: 'order-1',
          clientOrderId: 'client-1',
          exchangeOrderId: 'exchange-1',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'LIMIT',
          quantity: 0.1,
          price: 50000,
          stopPrice: null,
          status: 'FILLED' as OrderStatus,
          venue: 'SPOT' as Venue,
          timeInForce: 'GTC' as const,
          filledQuantity: 0.1,
          averageFillPrice: 50000,
          commission: 0,
          commissionAsset: 'USDT',
          lastUpdateTime: new Date(),
          decisionId: null,
          reduceOnly: false,
          closePosition: false,
          postOnly: false,
          activationPrice: null,
          callbackRate: null,
          workingType: null,
          priceProtect: false,
          rejectReason: null,
          createdAt: new Date(),
          updatedAt: new Date(),
        },
      ];

      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      const result = await orderRepository.findAll();

      expect(mockRepository.createQueryBuilder).toHaveBeenCalledWith('order');
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('order.createdAt', 'DESC');
      expect(result).toEqual(mockOrders);
    });

    it('should filter by venue', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ venue: 'USD_M' as Venue });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.venue = :venue', {
        venue: 'USD_M' as Venue,
      });
    });

    it('should filter by symbol', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ symbol: 'ETHUSDT' });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.symbol = :symbol', {
        symbol: 'ETHUSDT',
      });
    });

    it('should filter by status', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ status: 'NEW' as OrderStatus });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.status = :status', {
        status: 'NEW' as OrderStatus,
      });
    });

    it('should apply limit', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ limit: 10 });

      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(10);
    });
  });

  describe('findActiveOrders', () => {
    it('should find active orders', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findActiveOrders();

      expect(mockQueryBuilder.where).toHaveBeenCalledWith('order.status IN (:...statuses)', {
        statuses: ['NEW', 'PARTIALLY_FILLED'],
      });
    });

    it('should filter active orders by venue and symbol', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findActiveOrders({ venue: 'SPOT' as Venue, symbol: 'BTCUSDT' });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.venue = :venue', {
        venue: 'SPOT' as Venue,
      });
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.symbol = :symbol', {
        symbol: 'BTCUSDT',
      });
    });
  });

  describe('findByClientOrderId', () => {
    it('should find order by client order ID', async () => {
      const mockOrder = { clientOrderId: 'client-1', venue: 'SPOT' as Venue } as OrderEntity;
      (mockRepository.findOne as jest.Mock).mockResolvedValue(mockOrder);

      const result = await orderRepository.findByClientOrderId('client-1', 'SPOT' as Venue);

      expect(mockRepository.findOne).toHaveBeenCalledWith({
        where: { clientOrderId: 'client-1', venue: 'SPOT' as Venue },
      });
      expect(result).toEqual(mockOrder);
    });
  });

  describe('findByExchangeOrderId', () => {
    it('should find order by exchange order ID', async () => {
      const mockOrder = { exchangeOrderId: 'exchange-1' } as OrderEntity;
      (mockRepository.findOne as jest.Mock).mockResolvedValue(mockOrder);

      const result = await orderRepository.findByExchangeOrderId('exchange-1');

      expect(mockRepository.findOne).toHaveBeenCalledWith({
        where: { exchangeOrderId: 'exchange-1' },
      });
      expect(result).toEqual(mockOrder);
    });
  });

  describe('findByOrderId', () => {
    it('should find order by BFF order ID and venue', async () => {
      const mockOrder = { orderId: 'order-1', venue: 'SPOT' as Venue } as OrderEntity;
      (mockRepository.findOne as jest.Mock).mockResolvedValue(mockOrder);

      const result = await orderRepository.findByOrderId('order-1', 'SPOT' as Venue);

      expect(mockRepository.findOne).toHaveBeenCalledWith({
        where: { orderId: 'order-1', venue: 'SPOT' as Venue },
      });
      expect(result).toEqual(mockOrder);
    });
  });

  describe('save', () => {
    it('should save order', async () => {
      const orderData = { symbol: 'BTCUSDT' } as Partial<OrderEntity>;
      const savedOrder = { ...orderData, orderId: 'order-1' } as OrderEntity;
      (mockRepository.save as jest.Mock).mockResolvedValue(savedOrder);

      const result = await orderRepository.save(orderData);

      expect(mockRepository.save).toHaveBeenCalledWith(orderData);
      expect(result).toEqual(savedOrder);
    });
  });

  describe('update', () => {
    it('should update order', async () => {
      const orderId = 'order-1';
      const updates = { status: 'FILLED' as OrderStatus };

      await orderRepository.update(orderId, updates);

      expect(mockRepository.update).toHaveBeenCalledWith({ orderId }, updates);
    });
  });
});
