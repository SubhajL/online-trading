import { Injectable, Logger } from '@nestjs/common';
import { BalancesService } from '../balances/balances.service';
import { TradingService } from '../trading/trading.service';
import { EngineClientService } from '../engine-client/engine-client.service';
import { EquitySampleRepository } from './repositories/equity-sample.repository';
import {
  DashboardSnapshotDto,
  TradingKPIsDto,
  ExposureSummaryDto,
  GuardStatusResponseDto,
  EngineStatusDto,
  PipelineHealthResponseDto,
  EquityPointDto,
  PositionDto,
} from './dto/dashboard.dto';

@Injectable()
export class DashboardService {
  private readonly logger = new Logger(DashboardService.name);

  constructor(
    private readonly balancesService: BalancesService,
    private readonly tradingService: TradingService,
    private readonly engineClient: EngineClientService,
    private readonly equitySampleRepository: EquitySampleRepository,
  ) {}

  async getSnapshot(): Promise<DashboardSnapshotDto> {
    const [balances, positions, orders] = await Promise.all([
      this.balancesService.getBalances(),
      this.tradingService.getPositions(),
      this.tradingService.getActiveOrders(),
    ]);

    const mappedPositions: PositionDto[] = positions.map((p) => ({
      symbol: p.symbol,
      side: p.side as 'LONG' | 'SHORT',
      quantity: p.quantity,
      entryPrice: p.entryPrice,
      markPrice: p.currentPrice,
      pnl: p.pnl,
      pnlPercent: p.pnlPercent,
      venue: p.venue || 'SPOT',
    }));

    const exposure = this.calculateExposure(mappedPositions, balances);
    const [kpis, guardStatus, pipelineHealth, equityCurve] = await Promise.all([
      this.buildKPIs(),
      this.buildGuardStatus(),
      this.buildPipelineHealth(),
      this.buildEquityCurve(exposure.totalEquity),
    ]);
    const engineStatus = this.buildEngineStatus();

    return {
      balances: balances.map((b) => ({
        asset: b.asset,
        free: b.free,
        locked: b.locked,
        total: b.total,
        venue: b.venue,
        usdValue: b.usdValue,
      })),
      positions: mappedPositions,
      recentOrders: orders.slice(0, 20).map((o) => ({
        orderId: o.orderId,
        symbol: o.symbol,
        side: o.side as 'BUY' | 'SELL',
        type: o.type,
        status: o.status,
        quantity: o.quantity,
        price: o.price ?? null,
        executedQuantity: o.executedQty ?? 0,
        createdAt: o.createdAt ?? new Date().toISOString(),
      })),
      kpis,
      exposure,
      guardStatus,
      engineStatus,
      pipelineHealth,
      equityCurve,
      updatedAt: new Date().toISOString(),
    };
  }

  private async buildGuardStatus(): Promise<GuardStatusResponseDto> {
    const engineHealth = await this.engineClient.checkHealth();

    return {
      engineState: engineHealth.status === 'up' ? 'ACTIVE' : 'STOPPED',
      guards: {
        drawdownGuard: { status: 'OK', blockedReason: null },
        maxPositionsGuard: { status: 'OK', blockedReason: null },
        newsGuard: { status: 'OK', blockedReason: null },
        volatilityGuard: { status: 'OK', blockedReason: null },
        correlationGuard: { status: 'OK', blockedReason: null },
      },
      overallStatus: 'OK',
      lastChecked: new Date().toISOString(),
    };
  }

  private buildEngineStatus(): EngineStatusDto {
    return {
      state: 'ACTIVE',
      autoTrading: this.tradingService.isAutoTradingEnabled(),
      lastDecisionAt: null,
      lastDecisionReason: null,
    };
  }

  private async buildKPIs(): Promise<TradingKPIsDto> {
    return {
      winRate: null,
      profitFactor: null,
      sharpeRatio: null,
      maxDrawdown: null,
      tradeCount: 0,
      tradingDays: 0,
      totalPnL: 0,
      dailyPnL: 0,
    };
  }

  private async buildPipelineHealth(): Promise<PipelineHealthResponseDto> {
    return {
      symbols: [],
      lastDecision: null,
      averageLagMs: 0,
      status: 'HEALTHY',
    };
  }

  private async buildEquityCurve(totalEquity: number): Promise<EquityPointDto[]> {
    const now = new Date();
    const sampleIntervalMs = 60_000;
    const retentionDays = 30;
    const limit = 2_000;

    const latest = await this.equitySampleRepository.findLatest();
    const shouldInsert = !latest || now.getTime() - latest.timestamp.getTime() >= sampleIntervalMs;

    if (shouldInsert) {
      try {
        await this.equitySampleRepository.insertSample(now, totalEquity);
      } catch (error) {
        this.logger.warn(
          `Failed to insert equity sample: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    const since = new Date(now.getTime() - retentionDays * 24 * 60 * 60 * 1000);
    const samples = await this.equitySampleRepository.findSince(since, limit);

    return samples.map((s) => ({
      timestamp: s.timestamp.toISOString(),
      equity: Number(s.equity),
    }));
  }

  private calculateExposure(
    positions: PositionDto[],
    balances: { free: number; locked: number; total: number }[],
  ): ExposureSummaryDto {
    const spotPositions = positions.filter((p) => p.venue === 'SPOT');
    const futuresPositions = positions.filter((p) => p.venue === 'USD_M');

    const spotNotional = spotPositions.reduce((sum, p) => sum + p.quantity * p.markPrice, 0);
    const futuresNotional = futuresPositions.reduce(
      (sum, p) => sum + Math.abs(p.quantity) * p.markPrice,
      0,
    );

    const unrealizedPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
    const totalEquity = balances.reduce((sum, b) => sum + b.total, 0);
    const availableMargin = balances.reduce((sum, b) => sum + b.free, 0);
    const usedMargin = balances.reduce((sum, b) => sum + b.locked, 0);

    return {
      totalNotional: spotNotional + futuresNotional,
      spotNotional,
      futuresNotional,
      unrealizedPnl,
      realizedPnlToday: 0,
      totalEquity,
      availableMargin,
      marginUsagePercent: totalEquity > 0 ? (usedMargin / totalEquity) * 100 : 0,
      positionCount: positions.length,
      spotPositionCount: spotPositions.length,
      futuresPositionCount: futuresPositions.length,
    };
  }
}
