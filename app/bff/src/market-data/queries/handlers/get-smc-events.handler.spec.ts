import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GetSmcEventsHandler } from './get-smc-events.handler';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEventV1 } from '../../../database/entities/smc-events-v1.entity';
import type { SmcEventsV1 } from '@/contracts/gen/index';

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
      const row: SmcEventV1 = {
        venue: 'binance_spot',
        symbol: 'BTCUSDT',
        timeframe: '1h',
        event_time: new Date('2025-01-15T10:30:00.000Z'),
        event_type: 'CHOCH',
        direction: 'bearish',
        price_level: '49000.12345678',
        previous_pivot_price: '49500.00000000',
        previous_pivot_time: new Date('2025-01-15T09:00:00.000Z'),
        broken_pivot_price: '51500.00000000',
        broken_pivot_time: new Date('2025-01-15T08:00:00.000Z'),
        version: '1.0.0',
        created_at: new Date('2025-01-15T10:30:01.000Z'),
      };

      const expected: SmcEventsV1[] = [
        {
          version: '1.0.0',
          venue: 'binance_spot',
          symbol: 'BTCUSDT',
          timeframe: '1h',
          event_time: '2025-01-15T10:30:00.000Z',
          event_type: 'choch',
          direction: 'bearish',
          price_level: '49000.12345678',
          previous_pivot_price: '49500.00000000',
          previous_pivot_time: '2025-01-15T09:00:00.000Z',
          broken_pivot_price: '51500.00000000',
          broken_pivot_time: '2025-01-15T08:00:00.000Z',
        },
      ];

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([row]),
      };

      mockSmcEventV1Repository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      expect(result).toEqual(expected);
      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'ev.symbol = :symbol AND ev.timeframe = :timeframe',
        { symbol: 'BTCUSDT', timeframe: '1h' },
      );
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('ev.event_time', 'DESC');
      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(10);
    });

    it('should normalize event types to uppercase when filtering', async () => {
      const eventTypes = ['choch', 'bos'];
      const normalizedEventTypes = ['CHOCH', 'BOS'];
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
        eventTypes: normalizedEventTypes,
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

    it('should return strict smc_events.v1 contract shape', async () => {
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', undefined, undefined, undefined, 10);
      const row: SmcEventV1 = {
        venue: 'binance_spot',
        symbol: 'BTCUSDT',
        timeframe: '1h',
        event_time: new Date('2025-01-15T10:30:00.000Z'),
        event_type: 'CHOCH',
        direction: 'bearish',
        price_level: '49000.12345678',
        previous_pivot_price: '49500.00000000',
        previous_pivot_time: new Date('2025-01-15T09:00:00.000Z'),
        broken_pivot_price: '51500.00000000',
        broken_pivot_time: new Date('2025-01-15T08:00:00.000Z'),
        version: '1.0.0',
        created_at: new Date('2025-01-15T10:30:01.000Z'),
      };

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([row]),
      };

      mockSmcEventV1Repository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      const ev = result[0] as unknown as Record<string, unknown>;
      expect(ev).toBeDefined();
      expect(ev.event_type).toBe('choch');
      expect(typeof ev.event_time).toBe('string');
      expect(String(ev.event_time)).toMatch(/Z$/);
      expect(typeof ev.previous_pivot_time).toBe('string');
      expect(String(ev.previous_pivot_time)).toMatch(/Z$/);
      expect(typeof ev.broken_pivot_time).toBe('string');
      expect(String(ev.broken_pivot_time)).toMatch(/Z$/);
      expect('created_at' in ev).toBe(false);

      const expectedKeys = [
        'broken_pivot_price',
        'broken_pivot_time',
        'direction',
        'event_time',
        'event_type',
        'previous_pivot_price',
        'previous_pivot_time',
        'price_level',
        'symbol',
        'timeframe',
        'venue',
        'version',
      ].sort();
      expect(Object.keys(ev).sort()).toEqual(expectedKeys);

      const typed = result as unknown as SmcEventsV1[];
      expect(typed[0].event_type).toBe('choch');
    });
  });
});
