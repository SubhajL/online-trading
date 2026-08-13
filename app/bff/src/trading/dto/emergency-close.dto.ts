import { IsEnum, IsOptional, IsBoolean } from 'class-validator';
import type {
  EmergencyExchangeState,
  EmergencySpotBalance,
} from '../../router-client/router-client.service';

export type EmergencyCloseScope = 'ALL' | 'SPOT' | 'FUTURES';

export class EmergencyCloseDto {
  @IsEnum(['ALL', 'SPOT', 'FUTURES'])
  scope!: EmergencyCloseScope;

  @IsOptional()
  @IsBoolean()
  stopEngine?: boolean;
}

export type EmergencyCloseStepName =
  | 'HALT_EXECUTION'
  | 'EXCHANGE_FLATTEN'
  | 'CANCEL_OPEN_ORDERS'
  | 'CLOSE_POSITIONS'
  | 'STOP_AUTO_TRADING';

export type EmergencyCloseStepStatus = 'SUCCESS' | 'FAILED' | 'SKIPPED';

export interface EmergencyCloseStep {
  name: EmergencyCloseStepName;
  status: EmergencyCloseStepStatus;
  startedAt: string;
  finishedAt: string;
  errors: string[];
  result: {
    canceledOrders?: number;
    closedPositions?: number;
    autoTradingDisabled?: boolean;
    executionHalted?: boolean;
    controlGeneration?: number;
    fullyFlattened?: boolean;
    residuals?: EmergencySpotBalance[];
  };
}

export interface EmergencyCloseResponse {
  success: boolean;
  scope: EmergencyCloseScope;
  stopEngine: boolean;
  idempotencyKey: string;
  canceledOrders: number;
  closedPositions: number;
  autoTradingDisabled: boolean;
  executionHalted: boolean;
  controlGeneration: number | null;
  fullyFlattened: boolean;
  residuals: EmergencySpotBalance[];
  startingState: EmergencyExchangeState | null;
  finalState: EmergencyExchangeState | null;
  steps: EmergencyCloseStep[];
  executionTimeMs: number;
}
