import { IsEnum, IsOptional, IsBoolean } from 'class-validator';

export type EmergencyCloseScope = 'ALL' | 'SPOT' | 'FUTURES';

export class EmergencyCloseDto {
  @IsEnum(['ALL', 'SPOT', 'FUTURES'])
  scope!: EmergencyCloseScope;

  @IsOptional()
  @IsBoolean()
  stopEngine?: boolean;
}

export type EmergencyCloseStepName = 'CANCEL_OPEN_ORDERS' | 'CLOSE_POSITIONS' | 'STOP_AUTO_TRADING';

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
  steps: EmergencyCloseStep[];
  executionTimeMs: number;
}
