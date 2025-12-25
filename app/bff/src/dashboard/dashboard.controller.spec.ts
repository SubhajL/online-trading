import { Test } from '@nestjs/testing';
import { GUARDS_METADATA } from '@nestjs/common/constants';
import { DashboardController } from './dashboard.controller';
import { DashboardService } from './dashboard.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import type { DashboardSnapshotDto } from './dto/dashboard.dto';

describe('DashboardController', () => {
  it('is protected by JwtAuthGuard', () => {
    const guards = Reflect.getMetadata(GUARDS_METADATA, DashboardController) as unknown[];
    expect(guards).toEqual(expect.arrayContaining([JwtAuthGuard]));
  });

  it('returns dashboard snapshot from DashboardService', async () => {
    const snapshot: DashboardSnapshotDto = {
      guardStatus: {
        engineState: 'ACTIVE',
        guards: {
          drawdownGuard: { status: 'OK', blockedReason: null },
          maxPositionsGuard: { status: 'OK', blockedReason: null },
          newsGuard: { status: 'OK', blockedReason: null },
          volatilityGuard: { status: 'OK', blockedReason: null },
          correlationGuard: { status: 'OK', blockedReason: null },
        },
        overallStatus: 'OK',
        lastChecked: new Date().toISOString(),
      },
      pipelineHealth: {
        symbols: [],
        lastDecision: null,
        averageLagMs: 0,
        status: 'HEALTHY',
      },
      equityCurve: [],
      balances: [],
      positions: [],
      recentOrders: [],
      kpis: {
        winRate: null,
        profitFactor: null,
        sharpeRatio: null,
        maxDrawdown: null,
        tradeCount: 0,
        tradingDays: 0,
        totalPnL: 0,
        dailyPnL: 0,
      },
      exposure: {
        totalNotional: 0,
        spotNotional: 0,
        futuresNotional: 0,
        unrealizedPnl: 0,
        realizedPnlToday: 0,
        totalEquity: 0,
        availableMargin: 0,
        marginUsagePercent: 0,
        positionCount: 0,
        spotPositionCount: 0,
        futuresPositionCount: 0,
      },
      engineStatus: {
        state: 'ACTIVE',
        autoTrading: false,
        lastDecisionAt: null,
        lastDecisionReason: null,
      },
      updatedAt: new Date().toISOString(),
    };

    const dashboardService = {
      getSnapshot: jest.fn().mockResolvedValue(snapshot),
    };

    const moduleRef = await Test.createTestingModule({
      controllers: [DashboardController],
      providers: [{ provide: DashboardService, useValue: dashboardService }],
    }).compile();

    const controller = moduleRef.get(DashboardController);

    await expect(controller.getSnapshot()).resolves.toEqual(snapshot);
    expect(dashboardService.getSnapshot).toHaveBeenCalledTimes(1);
  });
});
