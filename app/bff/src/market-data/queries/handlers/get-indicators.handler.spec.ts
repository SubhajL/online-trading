import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { GetIndicatorsHandler } from './get-indicators.handler';
import { GetIndicatorsQuery } from '../get-indicators.query';
import { Indicators } from '../../../database/entities/indicators.entity';

describe('GetIndicatorsHandler', () => {
  let handler: GetIndicatorsHandler;

  const mockIndicatorsRepository = {
    createQueryBuilder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GetIndicatorsHandler,
        {
          provide: getRepositoryToken(Indicators),
          useValue: mockIndicatorsRepository,
        },
      ],
    }).compile();

    handler = module.get<GetIndicatorsHandler>(GetIndicatorsHandler);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('execute', () => {
    it('should return indicators for given symbol and timeframe', async () => {
      const query = new GetIndicatorsQuery('BTCUSDT', '1h', undefined, undefined, 10);
      const mockIndicators = [
        {
          venue: 'binance',
          symbol: 'BTCUSDT',
          tf: '1h',
          candle_open_time: new Date('2024-01-01T00:00:00Z'),
          ema_9: 42100,
          ema_21: 42000,
          ema_50: 41900,
          rsi_14: 55.5,
          macd_line: 100,
          macd_signal: 90,
          macd_histogram: 10,
        },
      ];

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(mockIndicators),
      };

      mockIndicatorsRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      const result = await handler.execute(query);

      expect(result).toEqual(mockIndicators);
      expect(mockQueryBuilder.where).toHaveBeenCalledWith(
        'indicators.symbol = :symbol AND indicators.tf = :tf',
        { symbol: 'BTCUSDT', tf: '1h' },
      );
      expect(mockQueryBuilder.orderBy).toHaveBeenCalledWith('indicators.candle_open_time', 'DESC');
      expect(mockQueryBuilder.limit).toHaveBeenCalledWith(10);
    });

    it('should filter by time range when provided', async () => {
      const startTime = new Date('2024-01-01T00:00:00Z');
      const endTime = new Date('2024-01-02T00:00:00Z');
      const query = new GetIndicatorsQuery('BTCUSDT', '1h', startTime, endTime);

      const mockQueryBuilder = {
        where: jest.fn().mockReturnThis(),
        andWhere: jest.fn().mockReturnThis(),
        orderBy: jest.fn().mockReturnThis(),
        limit: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue([]),
      };

      mockIndicatorsRepository.createQueryBuilder.mockReturnValue(mockQueryBuilder);

      await handler.execute(query);

      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith(
        'indicators.candle_open_time >= :startTime',
        { startTime },
      );
      expect(mockQueryBuilder.andWhere).toHaveBeenCalledWith(
        'indicators.candle_open_time <= :endTime',
        { endTime },
      );
    });
  });
});
