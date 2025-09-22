import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { OrderRepository } from './order.repository';
import { OrderEntity, OrderStatus, Venue } from '../entities/order-entity';
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
          quantity: '0.1',
          price: '50000',
          status: OrderStatus.FILLED,
          venue: Venue.SPOT,
          executedQuantity: '0.1',
          avgPrice: '50000',
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

      await orderRepository.findAll({ venue: Venue.USD_M });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.venue = :venue', { venue: Venue.USD_M });
    });

    it('should filter by symbol', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ symbol: 'ETHUSDT' });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.symbol = :symbol', { symbol: 'ETHUSDT' });
    });

    it('should filter by status', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findAll({ status: OrderStatus.NEW });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.status = :status', { status: OrderStatus.NEW });
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

      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'order.status IN (:...statuses)',
        { statuses: ['NEW', 'PARTIALLY_FILLED'] }
      );
    });

    it('should filter active orders by venue and symbol', async () => {
      const mockOrders: OrderEntity[] = [];
      mockQueryBuilder.getMany.mockResolvedValue(mockOrders);

      await orderRepository.findActiveOrders({ venue: Venue.SPOT, symbol: 'BTCUSDT' });

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.venue = :venue', { venue: Venue.SPOT });
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('order.symbol = :symbol', { symbol: 'BTCUSDT' });
    });
  });

  describe('findByClientOrderId', () => {
    it('should find order by client order ID', async () => {
      const mockOrder = { clientOrderId: 'client-1', venue: Venue.SPOT } as OrderEntity;
      (mockRepository.findOne as jest.Mock).mockResolvedValue(mockOrder);

      const result = await orderRepository.findByClientOrderId('client-1', Venue.SPOT);

      expect(mockRepository.findOne).toHaveBeenCalledWith({
        where: { clientOrderId: 'client-1', venue: Venue.SPOT },
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
      const updates = { status: OrderStatus.FILLED };

      await orderRepository.update(orderId, updates);

      expect(mockRepository.update).toHaveBeenCalledWith({ orderId }, updates);
    });
  });
});