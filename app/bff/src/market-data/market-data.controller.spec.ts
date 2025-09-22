import { Test, TestingModule } from '@nestjs/testing';
import { QueryBus } from '@nestjs/cqrs';
import { MarketDataController } from './market-data.controller';
import { GetCandlesDto } from './dto/get-candles.dto';
import { GetCandlesQuery } from './queries/get-candles.query';
import { GetIndicatorsQuery } from './queries/get-indicators.query';
import { GetSmcEventsQuery } from './queries/get-smc-events.query';

describe('MarketDataController', () => {
  let controller: MarketDataController;
  let queryBus: QueryBus;

  const mockQueryBus = {
    execute: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [MarketDataController],
      providers: [
        {
          provide: QueryBus,
          useValue: mockQueryBus,
        },
      ],
    }).compile();

    controller = module.get<MarketDataController>(MarketDataController);
    queryBus = module.get<QueryBus>(QueryBus);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('getCandles', () => {
    it('should return candles for valid query', async () => {
      const dto: GetCandlesDto = {
        symbol: 'BTCUSDT',
        tf: '1h',
        limit: 10,
      };

      const mockCandles = [
        {
          symbol: 'BTCUSDT',
          tf: '1h',
          open_time: new Date(),
          close: 42000,
        },
      ];

      mockQueryBus.execute.mockResolvedValue(mockCandles);

      const result = await controller.getCandles(dto);

      expect(result).toEqual(mockCandles);
      expect(queryBus.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'BTCUSDT',
          tf: '1h',
          limit: 10,
        }),
      );
    });

    it('should parse dates when provided', async () => {
      const dto: GetCandlesDto = {
        symbol: 'BTCUSDT',
        tf: '1h',
        startTime: '2024-01-01T00:00:00Z',
        endTime: '2024-01-02T00:00:00Z',
      };

      mockQueryBus.execute.mockResolvedValue([]);

      await controller.getCandles(dto);

      const executedQuery = mockQueryBus.execute.mock.calls[0][0];
      expect(executedQuery.startTime).toBeInstanceOf(Date);
      expect(executedQuery.endTime).toBeInstanceOf(Date);
    });
  });

  describe('getIndicators', () => {
    it('should return indicators for valid query', async () => {
      const dto = {
        symbol: 'BTCUSDT',
        tf: '1h',
        limit: 10,
      };

      const mockIndicators = [
        {
          symbol: 'BTCUSDT',
          tf: '1h',
          candle_open_time: new Date(),
          rsi_14: 55.5,
        },
      ];

      mockQueryBus.execute.mockResolvedValue(mockIndicators);

      const result = await controller.getIndicators(dto);

      expect(result).toEqual(mockIndicators);
      expect(queryBus.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'BTCUSDT',
          tf: '1h',
          limit: 10,
        }),
      );
    });
  });

  describe('getSmcEvents', () => {
    it('should return SMC events for valid query', async () => {
      const dto = {
        symbol: 'BTCUSDT',
        tf: '1h',
        eventTypes: ['CHOCH', 'BOS'],
        limit: 10,
      };

      const mockEvents = [
        {
          symbol: 'BTCUSDT',
          tf: '1h',
          event_type: 'CHOCH',
          direction: 'bullish',
        },
      ];

      mockQueryBus.execute.mockResolvedValue(mockEvents);

      const result = await controller.getSmcEvents(dto);

      expect(result).toEqual(mockEvents);
      expect(queryBus.execute).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: 'BTCUSDT',
          tf: '1h',
          eventTypes: ['CHOCH', 'BOS'],
          limit: 10,
        }),
      );
    });
  });
});