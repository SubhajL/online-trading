import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GetSmcEventsHandler } from './get-smc-events.handler';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEventV1 } from '../../../database/entities/smc-events-v1.entity';

describe('GetSmcEventsHandler', () => {
  let handler: GetSmcEventsHandler;

  const mockSmcEventV1Repository = {
    createQueryBuilder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GetSmcEventsHandler,
        {
          provide: getRepositoryToken(SmcEventV1),
          useValue: mockSmcEventV1Repository,
        },
      ],
    }).compile();

    handler = module.get<GetSmcEventsHandler>(GetSmcEventsHandler);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('execute', () => {
    it('should query smc_events_v1 with event_time ordering', async () => {
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', undefined, undefined, undefined, 10);
      const mockEvents: SmcEventV1[] = [
        {
          venue: 'binance_spot',
          symbol: 'BTCUSDT',
          timeframe: '1h',
          event_time: new Date('2025-01-15T10:30:00Z'),
          event_type: 'CHOCH',
          direction: 'bearish',
          price_level: '49000.12345678',
          previous_pivot_price: '49500.00000000',
          previous_pivot_time: new Date('2025-01-15T09:00:00Z'),
          broken_pivot_price: '51500.00000000',
          broken_pivot_time: new Date('2025-01-15T08:00:00Z'),
          version: '1.0.0',
          created_at: new Date('2025-01-15T10:30:01Z'),
        },
      ];

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(mockEvents),
      };

      mockSmcEventV1Repository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      expect(result).toEqual(mockEvents);
      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'ev.symbol = :symbol AND ev.timeframe = :timeframe',
        { symbol: 'BTCUSDT', timeframe: '1h' },
      );
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('ev.event_time', 'DESC');
      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(10);
    });

    it('should filter by event types when provided', async () => {
      const eventTypes = ['CHOCH', 'BOS'];
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', eventTypes);

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockSmcEventV1Repository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('ev.event_type IN (:...eventTypes)', {
        eventTypes,
      });
    });

    it('should filter by time range using event_time', async () => {
      const startTime = new Date('2025-01-01T00:00:00Z');
      const endTime = new Date('2025-01-02T00:00:00Z');
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', undefined, startTime, endTime);

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockSmcEventV1Repository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('ev.event_time >= :startTime', {
        startTime,
      });
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('ev.event_time <= :endTime', {
        endTime,
      });
    });
  });
});
