import { Injectable, ConflictException, BadRequestException, Logger } from '@nestjs/common';
import { TradingService } from './trading.service';
import { RouterClientService } from '../router-client/router-client.service';
import type {
  EmergencyCloseDto,
  EmergencyCloseResponse,
  EmergencyCloseScope,
  EmergencyCloseStep,
  EmergencyCloseStepName,
} from './dto/emergency-close.dto';
import { EmergencyCloseOperationRepository } from './repositories/emergency-close-operation.repository';
import { EmergencyCloseOperationEntity } from './entities/emergency-close-operation.entity';

type RouterCancelOpenOrdersResponse = { canceled_orders: number; errors?: string[] };
type RouterClosePositionsResponse = { closed_positions: number; errors?: string[] };

function buildRequestSignature(scope: EmergencyCloseScope, stopEngine: boolean): string {
  return `${scope}:${stopEngine ? '1' : '0'}`;
}

function createStep(
  name: EmergencyCloseStepName,
  startedAt: Date,
  finishedAt: Date,
  errors: string[],
  result: EmergencyCloseStep['result'],
): EmergencyCloseStep {
  const status: EmergencyCloseStep['status'] =
    errors.length > 0 ? 'FAILED' : result.autoTradingDisabled === false ? 'FAILED' : 'SUCCESS';

  return {
    name,
    status,
    startedAt: startedAt.toISOString(),
    finishedAt: finishedAt.toISOString(),
    errors,
    result,
  };
}

@Injectable()
export class EmergencyCloseService {
  private readonly logger = new Logger(EmergencyCloseService.name);

  constructor(
    private readonly tradingService: TradingService,
    private readonly routerClient: RouterClientService,
    private readonly repository: EmergencyCloseOperationRepository,
  ) {}

  async execute(dto: EmergencyCloseDto, idempotencyKey: string): Promise<EmergencyCloseResponse> {
    if (!idempotencyKey) {
      throw new BadRequestException('X-Idempotency-Key header is required');
    }

    const stopEngine = dto.stopEngine ?? false;
    const requestSignature = buildRequestSignature(dto.scope, stopEngine);

    const existing = await this.repository.findByIdempotencyKey(idempotencyKey);
    if (existing) {
      if (existing.requestSignature !== requestSignature) {
        throw new ConflictException('Idempotency key reuse with different request');
      }
      return existing.response;
    }

    const startedAt = Date.now();

    const steps: EmergencyCloseStep[] = [];
    let canceledOrders = 0;
    let closedPositions = 0;
    let autoTradingDisabled = false;

    const symbols = await this.getKnownSymbols();

    // Step 1: cancel open orders
    {
      const stepStart = new Date();
      const errors: string[] = [];

      try {
        const response: RouterCancelOpenOrdersResponse = await this.routerClient.cancelOpenOrders({
          scope: dto.scope,
          symbols,
        });
        canceledOrders = response.canceled_orders;
        if (response.errors?.length) errors.push(...response.errors);
      } catch (error) {
        errors.push(error instanceof Error ? error.message : 'Unknown error canceling open orders');
      }

      const stepEnd = new Date();
      steps.push(
        createStep('CANCEL_OPEN_ORDERS', stepStart, stepEnd, errors, {
          canceledOrders,
        }),
      );
    }

    // Step 2: close positions
    {
      const stepStart = new Date();
      const errors: string[] = [];

      try {
        const response: RouterClosePositionsResponse = await this.routerClient.closePositions({
          scope: dto.scope,
          symbols,
        });
        closedPositions = response.closed_positions;
        if (response.errors?.length) errors.push(...response.errors);
      } catch (error) {
        errors.push(error instanceof Error ? error.message : 'Unknown error closing positions');
      }

      const stepEnd = new Date();
      steps.push(
        createStep('CLOSE_POSITIONS', stepStart, stepEnd, errors, {
          closedPositions,
        }),
      );
    }

    // Step 3: stop auto-trading (optional)
    if (stopEngine) {
      const stepStart = new Date();
      const errors: string[] = [];

      try {
        await this.tradingService.setAutoTrading(false);
        autoTradingDisabled = true;
      } catch (error) {
        autoTradingDisabled = false;
        errors.push(
          error instanceof Error ? error.message : 'Unknown error disabling auto trading',
        );
      }

      const stepEnd = new Date();
      steps.push(
        createStep('STOP_AUTO_TRADING', stepStart, stepEnd, errors, {
          autoTradingDisabled,
        }),
      );
    } else {
      const now = new Date();
      steps.push({
        name: 'STOP_AUTO_TRADING',
        status: 'SKIPPED',
        startedAt: now.toISOString(),
        finishedAt: now.toISOString(),
        errors: [],
        result: { autoTradingDisabled: false },
      });
    }

    const success = steps.every((s) => s.status !== 'FAILED');

    const response: EmergencyCloseResponse = {
      success,
      scope: dto.scope,
      stopEngine,
      idempotencyKey,
      canceledOrders,
      closedPositions,
      autoTradingDisabled,
      steps,
      executionTimeMs: Date.now() - startedAt,
    };

    const operation = new EmergencyCloseOperationEntity();
    operation.idempotencyKey = idempotencyKey;
    operation.scope = dto.scope;
    operation.stopEngine = stopEngine;
    operation.requestSignature = requestSignature;
    operation.response = response;

    await this.repository.save(operation);

    this.logger.warn(
      `Emergency close executed: scope=${dto.scope} stopEngine=${stopEngine} success=${success} canceledOrders=${canceledOrders} closedPositions=${closedPositions}`,
    );

    return response;
  }

  private async getKnownSymbols(): Promise<string[]> {
    try {
      const positions = await this.tradingService.getPositions();
      const symbols = new Set<string>();
      for (const p of positions) {
        if (p.symbol) symbols.add(p.symbol);
      }
      return Array.from(symbols);
    } catch {
      return [];
    }
  }
}
