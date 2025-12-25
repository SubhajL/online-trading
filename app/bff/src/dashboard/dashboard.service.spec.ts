import { Test } from '@nestjs/testing';
import { DashboardService } from './dashboard.service';
import { BalancesService } from '../balances/balances.service';
import { TradingService } from '../trading/trading.service';
import { EngineClientService } from '../engine-client/engine-client.service';
import { EquitySampleRepository } from './repositories/equity-sample.repository';

describe('DashboardService', () => {
  const mockBalancesService = {
    getBalances: jest.fn(),
  };

  const mockTradingService = {
    getPositions: jest.fn(),
    getActiveOrders: jest.fn(),
    isAutoTradingEnabled: jest.fn(),
  };

  const mockEngineClient = {
    checkHealth: jest.fn(),
  };

  const mockEquitySampleRepository = {
    findLatest: jest.fn(),
    insertSample: jest.fn(),
    findSince: jest.fn(),
  };

  let service: DashboardService;

  beforeEach(async () => {
    jest.clearAllMocks();

    const module = await Test.createTestingModule({
      providers: [
        DashboardService,
        { provide: BalancesService, useValue: mockBalancesService },
        { provide: TradingService, useValue: mockTradingService },
        { provide: EngineClientService, useValue: mockEngineClient },
        { provide: EquitySampleRepository, useValue: mockEquitySampleRepository },
      ],
    }).compile();

    service = module.get(DashboardService);
  });

  it('returns snapshot with equity curve from repository', async () => {
    mockBalancesService.getBalances.mockResolvedValue([
      { asset: 'USDT', free: 10, locked: 0, total: 10, venue: 'SPOT', usdValue: 10 },
    ]);
    mockTradingService.getPositions.mockResolvedValue([]);
    mockTradingService.getActiveOrders.mockResolvedValue([]);
    mockTradingService.isAutoTradingEnabled.mockReturnValue(false);
    mockEngineClient.checkHealth.mockResolvedValue({ status: 'up' });
    mockEquitySampleRepository.findLatest.mockResolvedValue({
      timestamp: new Date(Date.now() - 120_000),
    });
    mockEquitySampleRepository.insertSample.mockResolvedValue(undefined);
    mockEquitySampleRepository.findSince.mockResolvedValue([
      { timestamp: new Date('2025-01-01T00:00:00.000Z'), equity: '10' },
    ]);

    const snapshot = await service.getSnapshot();

    expect(snapshot.exposure.totalEquity).toBe(10);
    expect(snapshot.equityCurve).toEqual([{ timestamp: '2025-01-01T00:00:00.000Z', equity: 10 }]);
  });

  it('inserts equity sample when latest is stale', async () => {
    mockBalancesService.getBalances.mockResolvedValue([
      { asset: 'USDT', free: 10, locked: 0, total: 10, venue: 'SPOT', usdValue: 10 },
    ]);
    mockTradingService.getPositions.mockResolvedValue([]);
    mockTradingService.getActiveOrders.mockResolvedValue([]);
    mockTradingService.isAutoTradingEnabled.mockReturnValue(false);
    mockEngineClient.checkHealth.mockResolvedValue({ status: 'up' });
    mockEquitySampleRepository.findLatest.mockResolvedValue({
      timestamp: new Date(Date.now() - 120_000),
    });
    mockEquitySampleRepository.findSince.mockResolvedValue([]);

    await service.getSnapshot();

    expect(mockEquitySampleRepository.insertSample).toHaveBeenCalledTimes(1);
    expect(mockEquitySampleRepository.insertSample).toHaveBeenCalledWith(expect.any(Date), 10);
  });

  it('does not insert equity sample when latest is recent', async () => {
    mockBalancesService.getBalances.mockResolvedValue([
      { asset: 'USDT', free: 10, locked: 0, total: 10, venue: 'SPOT', usdValue: 10 },
    ]);
    mockTradingService.getPositions.mockResolvedValue([]);
    mockTradingService.getActiveOrders.mockResolvedValue([]);
    mockTradingService.isAutoTradingEnabled.mockReturnValue(false);
    mockEngineClient.checkHealth.mockResolvedValue({ status: 'up' });
    mockEquitySampleRepository.findLatest.mockResolvedValue({
      timestamp: new Date(),
    });
    mockEquitySampleRepository.findSince.mockResolvedValue([]);

    await service.getSnapshot();

    expect(mockEquitySampleRepository.insertSample).not.toHaveBeenCalled();
  });
});
