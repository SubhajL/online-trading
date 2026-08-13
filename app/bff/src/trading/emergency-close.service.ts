import { Injectable, ConflictException, BadRequestException, Logger } from '@nestjs/common';
import { TradingService } from './trading.service';
import { RouterClientService } from '../router-client/router-client.service';
import type {
  EmergencyExchangeState,
  EmergencySpotBalance,
} from '../router-client/router-client.service';
import type {
  EmergencyCloseDto,
  EmergencyCloseResponse,
  EmergencyCloseScope,
  EmergencyCloseStep,
  EmergencyCloseStepName,
} from './dto/emergency-close.dto';
import { EmergencyCloseOperationRepository } from './repositories/emergency-close-operation.repository';
import { EmergencyCloseOperationEntity } from './entities/emergency-close-operation.entity';

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
    let executionHalted = false;
    let controlGeneration: number | null = null;
    let fullyFlattened = false;
    let residuals: EmergencySpotBalance[] = [];
    let startingState: EmergencyExchangeState | null = null;
    let finalState: EmergencyExchangeState | null = null;

    {
      const stepStart = new Date();
      const errors: string[] = [];

      try {
        const acknowledged = await this.routerClient.haltExecution({
          reason: `emergency-close:${dto.scope}`,
          requested_by: 'bff-emergency-close',
          idempotency_key: `${idempotencyKey}:halt`,
        });
        const confirmed = await this.routerClient.getExecutionControl();
        if (
          acknowledged.state !== 'HALTED' ||
          confirmed.state !== 'HALTED' ||
          confirmed.generation < acknowledged.generation
        ) {
          throw new Error('Router execution halt was not durably confirmed');
        }
        executionHalted = true;
        controlGeneration = confirmed.generation;
      } catch (error) {
        errors.push(error instanceof Error ? error.message : 'Unknown error halting execution');
      }

      steps.push(
        createStep('HALT_EXECUTION', stepStart, new Date(), errors, {
          executionHalted,
          ...(controlGeneration === null ? {} : { controlGeneration }),
        }),
      );
    }

    if (!executionHalted) {
      const response: EmergencyCloseResponse = {
        success: false,
        scope: dto.scope,
        stopEngine,
        idempotencyKey,
        canceledOrders,
        closedPositions,
        autoTradingDisabled,
        executionHalted,
        controlGeneration,
        fullyFlattened,
        residuals,
        startingState,
        finalState,
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
      return response;
    }

    // The router owns exchange enumeration, cleanup ordering, and the residual verdict.
    {
      const stepStart = new Date();
      const errors: string[] = [];

      try {
        const response = await this.routerClient.emergencyFlatten(
          dto.scope,
          `${idempotencyKey}:flatten`,
        );
        canceledOrders = response.canceled_orders;
        closedPositions = response.closed_futures_positions + response.flattened_spot_assets;
        fullyFlattened = response.fully_flattened;
        residuals = response.residuals;
        startingState = response.starting;
        finalState = response.final;
        if (response.errors?.length) errors.push(...response.errors);
      } catch (error) {
        errors.push(error instanceof Error ? error.message : 'Unknown error flattening exposure');
      }

      const stepEnd = new Date();
      steps.push({
        name: 'EXCHANGE_FLATTEN',
        status: fullyFlattened ? 'SUCCESS' : 'FAILED',
        startedAt: stepStart.toISOString(),
        finishedAt: stepEnd.toISOString(),
        errors,
        result: {
          canceledOrders,
          closedPositions,
          fullyFlattened,
          residuals,
        },
      });
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
      executionHalted,
      controlGeneration,
      fullyFlattened,
      residuals,
      startingState,
      finalState,
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
}
