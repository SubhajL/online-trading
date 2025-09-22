import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetSmcEventsHandler } from './get-smc-events.handler';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEvent } from '../../../database/entities/smc-events.entity';

describe('GetSmcEventsHandler', () => {
  let handler: GetSmcEventsHandler;
  let smcEventRepository: Repository<SmcEvent>;

  const mockSmcEventRepository = {
    createQueryBuilder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GetSmcEventsHandler,
        {
          provide: getRepositoryToken(SmcEvent),
          useValue: mockSmcEventRepository,
        },
      ],
    }).compile();

    handler = module.get<GetSmcEventsHandler>(GetSmcEventsHandler);
    smcEventRepository = module.get<Repository<SmcEvent>>(getRepositoryToken(SmcEvent));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('execute', () => {
    it('should return SMC events for given symbol and timeframe', async () => {
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', undefined, undefined, undefined, 10);
      const mockEvents = [
        {
          id: 1,
          venue: 'binance',
          symbol: 'BTCUSDT',
          tf: '1h',
          candle_open_time: new Date('2024-01-01T00:00:00Z'),
          event_type: 'CHOCH',
          direction: 'bullish',
          price: 42000,
        },
      ];

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(mockEvents),
      };

      mockSmcEventRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      expect(result).toEqual(mockEvents);
      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'smc_event.symbol = :symbol AND smc_event.tf = :tf',
        { symbol: 'BTCUSDT', tf: '1h' },
      );
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('smc_event.candle_open_time', 'DESC');
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

      mockSmcEventRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith(
        'smc_event.event_type IN (:...eventTypes)',
        { eventTypes },
      );
    });

    it('should filter by time range when provided', async () => {
      const startTime = new Date('2024-01-01T00:00:00Z');
      const endTime = new Date('2024-01-02T00:00:00Z');
      const query = new GetSmcEventsQuery('BTCUSDT', '1h', undefined, startTime, endTime);

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockSmcEventRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith(
        'smc_event.candle_open_time >= :startTime',
        { startTime },
      );
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith(
        'smc_event.candle_open_time <= :endTime',
        { endTime },
      );
    });
  });
});
