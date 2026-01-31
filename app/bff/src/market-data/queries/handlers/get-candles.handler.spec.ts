import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GetCandlesHandler } from './get-candles.handler';
import { GetCandlesQuery } from '../get-candles.query';
import { Candle } from '../../../database/entities/candle.entity';

describe('GetCandlesHandler', () => {
  let handler: GetCandlesHandler;

  const mockCandleRepository = {
    createQueryBuilder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GetCandlesHandler,
        {
          provide: getRepositoryToken(Candle),
          useValue: mockCandleRepository,
        },
      ],
    }).compile();

    handler = module.get<GetCandlesHandler>(GetCandlesHandler);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('execute', () => {
    it('should return candles for given symbol and timeframe', async () => {
      const query = new GetCandlesQuery('BTCUSDT', '1h', undefined, undefined, 10);
      const mockCandles = [
        {
          venue: 'binance',
          symbol: 'BTCUSDT',
          tf: '1h',
          open_time: new Date('2024-01-01T00:00:00Z'),
          close_time: new Date('2024-01-01T01:00:00Z'),
          open: 42000,
          high: 42500,
          low: 41800,
          close: 42300,
          volume: 100,
          trades: 1000,
        },
      ];

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(mockCandles),
      };

      mockCandleRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      expect(result).toEqual(mockCandles);
      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'candle.symbol = :symbol AND candle.timeframe = :timeframe',
        { symbol: 'BTCUSDT', timeframe: '1h' },
      );
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('candle.open_time', 'DESC');
      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(10);
    });

    it('should filter by time range when provided', async () => {
      const startTime = new Date('2024-01-01T00:00:00Z');
      const endTime = new Date('2024-01-02T00:00:00Z');
      const query = new GetCandlesQuery('BTCUSDT', '1h', startTime, endTime);

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockCandleRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('candle.open_time >= :startTime', {
        startTime,
      });
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith('candle.open_time <= :endTime', {
        endTime,
      });
    });

    it('should use default limit when not provided', async () => {
      const query = new GetCandlesQuery('BTCUSDT', '1h');

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockCandleRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(100);
    });
  });
});
