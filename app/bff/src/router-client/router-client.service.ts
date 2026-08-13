import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { isAxiosError } from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { firstValueFrom, timer } from 'rxjs';
import { retry } from 'rxjs/operators';
import type { RouterPlacementIdentity } from '../trading/placement-identity';

export interface OrderRequest {
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET';
  quantity: number;
  price?: number;
  stopLossPrice: number;
  takeProfitPrice: number;
  venue: 'SPOT' | 'USD_M';
}

export interface OrderResponse {
  orderId: string;
  status: string;
  symbol: string;
  side: string;
  type: string;
  quantity: number;
  price?: number;
  executedQty?: number;
  cummulativeQuoteQty?: number;
  venue?: 'SPOT' | 'USD_M';
  createdAt?: string;
  updatedAt?: string;
}

export interface RouterBracketPlacementResponse {
  bracket_order_id: string;
  client_order_ids: {
    main: string;
    take_profits: string[];
    stop_loss: string;
  };
  symbol: string;
  side: string;
  quantity: number;
  stop_loss_limit_price?: number;
  created_at: string;
  partial_failure: boolean;
  errors: string[];
  legs_pending_trigger: boolean;
}

export class RouterPlacementProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = RouterPlacementProtocolError.name;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requireNonEmptyString(record: Record<string, unknown>, field: string): string {
  const value = record[field];
  if (typeof value !== 'string' || value.trim() === '') {
    throw new RouterPlacementProtocolError(`Router placement response missing ${field}`);
  }
  return value;
}

function requireTimestamp(record: Record<string, unknown>, field: string): string {
  const value = requireNonEmptyString(record, field);
  if (!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) || Number.isNaN(Date.parse(value))) {
    throw new RouterPlacementProtocolError(`Router response has invalid ${field}`);
  }
  return value;
}

function requireNonNegativeInteger(record: Record<string, unknown>, field: string): number {
  const value = record[field];
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) {
    throw new RouterPlacementProtocolError(`Router response has invalid ${field}`);
  }
  return value;
}

function requireStringArray(record: Record<string, unknown>, field: string): string[] {
  const value = record[field];
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
    throw new RouterPlacementProtocolError(`Router response has invalid ${field}`);
  }
  return value;
}

export function validateRouterBracketPlacement(
  payload: unknown,
  request: OrderRequest,
  identity?: RouterPlacementIdentity,
): RouterBracketPlacementResponse {
  if (!isRecord(payload)) {
    throw new RouterPlacementProtocolError('Router placement response must be an object');
  }
  requireNonEmptyString(payload, 'bracket_order_id');
  const symbol = requireNonEmptyString(payload, 'symbol');
  const side = requireNonEmptyString(payload, 'side');
  if (symbol !== request.symbol || side !== request.side) {
    throw new RouterPlacementProtocolError(
      'Router placement symbol or side does not match the request',
    );
  }

  const rawQuantity = payload.quantity;
  const quantity = typeof rawQuantity === 'number' ? rawQuantity : Number(rawQuantity);
  if (!Number.isFinite(quantity) || quantity <= 0 || quantity !== request.quantity) {
    throw new RouterPlacementProtocolError('Router placement response has invalid quantity');
  }
  requireTimestamp(payload, 'created_at');
  for (const field of ['partial_failure', 'legs_pending_trigger'] as const) {
    if (typeof payload[field] !== 'boolean') {
      throw new RouterPlacementProtocolError(`Router placement response has invalid ${field}`);
    }
  }

  if (!isRecord(payload.client_order_ids)) {
    throw new RouterPlacementProtocolError('Router placement response missing client_order_ids');
  }
  const main = requireNonEmptyString(payload.client_order_ids, 'main');
  const stopLoss = requireNonEmptyString(payload.client_order_ids, 'stop_loss');
  const takeProfits = payload.client_order_ids.take_profits;
  if (
    !Array.isArray(takeProfits) ||
    takeProfits.length !== 1 ||
    takeProfits.some((value) => typeof value !== 'string' || value.trim() === '')
  ) {
    throw new RouterPlacementProtocolError(
      'Router placement response has invalid take-profit client IDs',
    );
  }
  if (
    identity &&
    (main !== identity.clientOrderIds.main ||
      stopLoss !== identity.clientOrderIds.stopLoss ||
      takeProfits.some((value, index) => value !== identity.clientOrderIds.takeProfits[index]))
  ) {
    throw new RouterPlacementProtocolError('Router placement client IDs do not match the request');
  }

  const errors = payload.errors;
  if (!Array.isArray(errors) || errors.some((value) => typeof value !== 'string')) {
    throw new RouterPlacementProtocolError('Router placement response has invalid errors');
  }
  if (payload.partial_failure === true || errors.length > 0) {
    throw new RouterPlacementProtocolError(
      `Router returned partial bracket placement: ${
        errors.length > 0 ? errors.join(', ') : 'unknown'
      }`,
    );
  }

  return { ...payload, quantity } as unknown as RouterBracketPlacementResponse;
}

export interface CancelOrderRequest {
  symbol: string;
  venue: 'SPOT' | 'USD_M';
  orderId: string;
  exchangeOrderId?: string | null;
  clientOrderId?: string | null;
}

export interface RouterCancelResponse {
  success: boolean;
}

export interface HealthCheckResult {
  status: 'up' | 'down';
  details: {
    url: string;
    response?: unknown;
    error?: string;
  };
}

export interface RouterReadiness {
  ready: boolean;
  // 'ready' | 'reconciling' | 'unreachable'
  status: string;
  error?: string;
}

// Mirrors the router's orders.ReconcileSummary (startup_reconciler.go).
export interface ReconcileSummary {
  brackets_swept: number;
  entries_checked: number;
  legs_resolved: number;
  exit_legs_updated: number;
  brackets_closed: number;
  stale_reserved: number;
  unrepaired_legs: number;
  errors: number;
}

// Mirrors the router's orders.ReconcileStatus.
export interface ReconcileStatus {
  has_run: boolean;
  last_run_at?: string;
  summary?: ReconcileSummary;
}

export interface CloseAllRequest {
  symbol?: string;
  is_futures: boolean;
}

export interface CloseAllResponse {
  success: boolean;
  message: string;
}

export interface CancelOpenOrdersRequest {
  scope: 'ALL' | 'SPOT' | 'FUTURES';
  symbols: string[];
}

export interface CancelOpenOrdersResponse {
  canceled_orders: number;
  errors?: string[];
}

export interface ClosePositionsRequest {
  scope: 'ALL' | 'SPOT' | 'FUTURES';
  symbols: string[];
}

export interface ClosePositionsResponse {
  closed_positions: number;
  errors?: string[];
}

export interface ExecutionControlRequest {
  reason: string;
  requested_by: string;
  idempotency_key: string;
  confirm_safe?: boolean;
}

export interface ExecutionControlResponse {
  scope: 'GLOBAL';
  state: 'RUNNING' | 'HALTED';
  generation: number;
  reason: string;
  requested_by: string;
  idempotency_key: string;
  requested_at: string;
  updated_at: string;
}

export interface EmergencyOpenOrder {
  venue: string;
  symbol: string;
  order_id: number;
  client_order_id: string;
  kind: 'ENTRY' | 'EXIT';
}

export interface EmergencyFuturesPosition {
  symbol: string;
  quantity: string;
  position_side: 'BOTH' | 'LONG' | 'SHORT';
}

export interface EmergencySpotBalance {
  asset: string;
  symbol?: string;
  quantity: string;
  notional_usdt: string;
  dust: boolean;
}

export interface EmergencyExchangeState {
  open_orders: EmergencyOpenOrder[];
  futures_positions: EmergencyFuturesPosition[];
  spot_balances: EmergencySpotBalance[];
  errors?: string[];
}

export interface EmergencyFlattenResponse {
  scope: 'ALL' | 'SPOT' | 'FUTURES';
  idempotency_key: string;
  starting: EmergencyExchangeState;
  final: EmergencyExchangeState;
  canceled_orders: number;
  closed_futures_positions: number;
  flattened_spot_assets: number;
  residuals: EmergencySpotBalance[];
  fully_flattened: boolean;
  passes: number;
  errors?: string[];
}

export function validateExecutionControlResponse(
  payload: unknown,
  expectedIdempotencyKey?: string,
): ExecutionControlResponse {
  if (!isRecord(payload)) {
    throw new RouterPlacementProtocolError('Router execution-control response must be an object');
  }
  if (payload.scope !== 'GLOBAL') {
    throw new RouterPlacementProtocolError('Router execution-control response has invalid scope');
  }
  if (payload.state !== 'RUNNING' && payload.state !== 'HALTED') {
    throw new RouterPlacementProtocolError('Router execution-control response has invalid state');
  }
  requireNonNegativeInteger(payload, 'generation');
  requireNonEmptyString(payload, 'reason');
  requireNonEmptyString(payload, 'requested_by');
  const idempotencyKey = requireNonEmptyString(payload, 'idempotency_key');
  if (expectedIdempotencyKey !== undefined && idempotencyKey !== expectedIdempotencyKey) {
    throw new RouterPlacementProtocolError(
      'Router execution-control response has invalid idempotency_key',
    );
  }
  requireTimestamp(payload, 'requested_at');
  requireTimestamp(payload, 'updated_at');
  return payload as unknown as ExecutionControlResponse;
}

function validateEmergencyExchangeState(payload: unknown, field: string): EmergencyExchangeState {
  if (!isRecord(payload)) {
    throw new RouterPlacementProtocolError(
      `Router emergency-flatten response has invalid ${field}`,
    );
  }
  for (const arrayField of ['open_orders', 'futures_positions', 'spot_balances'] as const) {
    if (!Array.isArray(payload[arrayField])) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.${arrayField}`,
      );
    }
  }
  requireStringArray(payload, 'errors');
  for (const order of payload.open_orders as unknown[]) {
    if (!isRecord(order)) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.open_orders`,
      );
    }
    if (order.venue !== 'SPOT' && order.venue !== 'USD_M') {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.open_orders.venue`,
      );
    }
    if (order.kind !== 'ENTRY' && order.kind !== 'EXIT') {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.open_orders.kind`,
      );
    }
    requireNonEmptyString(order, 'symbol');
    requireNonEmptyString(order, 'client_order_id');
    if (requireNonNegativeInteger(order, 'order_id') === 0) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.open_orders.order_id`,
      );
    }
  }
  for (const position of payload.futures_positions as unknown[]) {
    if (!isRecord(position)) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.futures_positions`,
      );
    }
    requireNonEmptyString(position, 'symbol');
    const quantity = Number(requireNonEmptyString(position, 'quantity'));
    if (!Number.isFinite(quantity) || quantity === 0) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.futures_positions.quantity`,
      );
    }
    if (!['BOTH', 'LONG', 'SHORT'].includes(String(position.position_side))) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.futures_positions.position_side`,
      );
    }
  }
  for (const balance of payload.spot_balances as unknown[]) {
    if (!isRecord(balance)) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.spot_balances`,
      );
    }
    requireNonEmptyString(balance, 'asset');
    const quantity = Number(requireNonEmptyString(balance, 'quantity'));
    const notional = Number(requireNonEmptyString(balance, 'notional_usdt'));
    if (!Number.isFinite(quantity) || quantity < 0 || !Number.isFinite(notional) || notional < 0) {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.spot_balances quantity`,
      );
    }
    if (typeof balance.dust !== 'boolean') {
      throw new RouterPlacementProtocolError(
        `Router emergency-flatten response has invalid ${field}.spot_balances.dust`,
      );
    }
  }
  return payload as unknown as EmergencyExchangeState;
}

export function validateEmergencyFlattenResponse(
  payload: unknown,
  expectedScope: 'ALL' | 'SPOT' | 'FUTURES',
  expectedIdempotencyKey: string,
): EmergencyFlattenResponse {
  if (!isRecord(payload)) {
    throw new RouterPlacementProtocolError('Router emergency-flatten response must be an object');
  }
  if (payload.scope !== expectedScope) {
    throw new RouterPlacementProtocolError('Router emergency-flatten response has invalid scope');
  }
  if (payload.idempotency_key !== expectedIdempotencyKey) {
    throw new RouterPlacementProtocolError(
      'Router emergency-flatten response has invalid idempotency_key',
    );
  }
  validateEmergencyExchangeState(payload.starting, 'starting');
  const finalState = validateEmergencyExchangeState(payload.final, 'final');
  for (const field of [
    'canceled_orders',
    'closed_futures_positions',
    'flattened_spot_assets',
  ] as const) {
    requireNonNegativeInteger(payload, field);
  }
  const passes = requireNonNegativeInteger(payload, 'passes');
  if (passes < 1) {
    throw new RouterPlacementProtocolError('Router emergency-flatten response has invalid passes');
  }
  if (!Array.isArray(payload.residuals)) {
    throw new RouterPlacementProtocolError(
      'Router emergency-flatten response has invalid residuals',
    );
  }
  const residualState = validateEmergencyExchangeState(
    { open_orders: [], futures_positions: [], spot_balances: payload.residuals, errors: [] },
    'residuals',
  );
  if (typeof payload.fully_flattened !== 'boolean') {
    throw new RouterPlacementProtocolError(
      'Router emergency-flatten response has invalid fully_flattened',
    );
  }
  requireStringArray(payload, 'errors');
  const canonicalBalances = (balances: EmergencySpotBalance[]) =>
    balances
      .map((balance) =>
        JSON.stringify([
          balance.asset,
          balance.symbol ?? null,
          balance.quantity,
          balance.notional_usdt,
          balance.dust,
        ]),
      )
      .sort();
  const expectedResiduals = canonicalBalances(finalState.spot_balances);
  const actualResiduals = canonicalBalances(residualState.spot_balances);
  if (JSON.stringify(expectedResiduals) !== JSON.stringify(actualResiduals)) {
    throw new RouterPlacementProtocolError(
      'Router emergency-flatten response has residuals inconsistent with final spot_balances',
    );
  }
  if (
    payload.fully_flattened &&
    (finalState.open_orders.length > 0 ||
      finalState.futures_positions.length > 0 ||
      finalState.spot_balances.some((balance) => !balance.dust) ||
      (finalState.errors?.length ?? 0) > 0)
  ) {
    throw new RouterPlacementProtocolError(
      'Router emergency-flatten response has contradictory fully_flattened state',
    );
  }
  return payload as unknown as EmergencyFlattenResponse;
}

@Injectable()
export class RouterClientService {
  private readonly logger = new Logger(RouterClientService.name);
  private readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeout: number;
  private readonly retryAttempts: number;
  private readonly retryDelay: number;

  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {
    // Use flat env var names since ConfigModule doesn't load nested config
    this.baseUrl = this.configService.get<string>('ROUTER_URL') || 'http://localhost:8001';
    this.apiKey = this.configService.get<string>('ROUTER_API_KEY') || undefined;
    this.timeout = this.configService.get<number>('ROUTER_TIMEOUT') || 5000;
    this.retryAttempts = this.configService.get<number>('ROUTER_RETRY_ATTEMPTS') || 3;
    this.retryDelay = this.configService.get<number>('ROUTER_RETRY_DELAY') || 1000;
  }

  private requestConfig(overrides: AxiosRequestConfig = {}): AxiosRequestConfig {
    return {
      timeout: this.timeout,
      ...overrides,
      headers: {
        'Content-Type': 'application/json',
        ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
        ...(overrides.headers || {}),
      },
    };
  }

  async placeOrder(
    orderRequest: OrderRequest,
    identity: RouterPlacementIdentity,
  ): Promise<RouterBracketPlacementResponse> {
    const url = `${this.baseUrl}/place_bracket`;

    this.logger.log(`Placing ${orderRequest.venue} order: ${JSON.stringify(orderRequest)}`);

    const config = this.requestConfig();
    const body = {
      symbol: orderRequest.symbol,
      side: orderRequest.side,
      quantity: orderRequest.quantity,
      entry_price: orderRequest.price,
      take_profit_prices: [orderRequest.takeProfitPrice],
      stop_loss_price: orderRequest.stopLossPrice,
      order_type: orderRequest.type,
      is_futures: orderRequest.venue === 'USD_M',
      idempotency_key: identity.idempotencyKey,
      client_order_ids: {
        main: identity.clientOrderIds.main,
        take_profits: identity.clientOrderIds.takeProfits,
        stop_loss: identity.clientOrderIds.stopLoss,
      },
    };

    try {
      const response = await firstValueFrom(
        this.httpService.post<RouterBracketPlacementResponse>(url, body, config).pipe(
          retry({
            count: Math.max(0, this.retryAttempts - 1),
            delay: (error) => {
              const status = isAxiosError(error) ? error.response?.status : undefined;
              if (status !== undefined && status !== 429 && status < 500) {
                throw error;
              }
              return timer(this.retryDelay);
            },
          }),
        ),
      );

      const placement = validateRouterBracketPlacement(response.data, orderRequest, identity);
      this.logger.log(`Bracket order placed successfully: ${placement.bracket_order_id}`);
      return placement;
    } catch (error) {
      this.logger.error(`Failed to place order: ${error}`);
      throw error;
    }
  }

  async cancelOrder(request: CancelOrderRequest): Promise<RouterCancelResponse> {
    const url = `${this.baseUrl}/cancel`;

    this.logger.log(`Canceling order ${request.orderId} for ${request.symbol} on ${request.venue}`);

    const config = this.requestConfig();
    const exchangeOrderId = request.exchangeOrderId?.trim();
    const body = exchangeOrderId
      ? {
          symbol: request.symbol,
          order_id: Number(exchangeOrderId),
        }
      : {
          symbol: request.symbol,
          client_order_id: request.clientOrderId,
        };

    try {
      const response = await firstValueFrom(
        this.httpService.post<RouterCancelResponse>(url, body, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      this.logger.log(`Order canceled successfully: ${request.orderId}`);
      return response.data;
    } catch (error) {
      this.logger.error(`Failed to cancel order: ${error}`);
      throw error;
    }
  }

  async haltExecution(request: ExecutionControlRequest): Promise<ExecutionControlResponse> {
    return this.postExecutionControl('halt', request);
  }

  async resumeExecution(request: ExecutionControlRequest): Promise<ExecutionControlResponse> {
    return this.postExecutionControl('resume', request);
  }

  async getExecutionControl(): Promise<ExecutionControlResponse> {
    const response = await firstValueFrom(
      this.httpService.get<ExecutionControlResponse>(
        `${this.baseUrl}/internal/execution-control`,
        this.requestConfig(),
      ),
    );
    return validateExecutionControlResponse(response.data);
  }

  async emergencyFlatten(
    scope: 'ALL' | 'SPOT' | 'FUTURES',
    idempotencyKey: string,
  ): Promise<EmergencyFlattenResponse> {
    const response = await firstValueFrom(
      this.httpService
        .post<EmergencyFlattenResponse>(
          `${this.baseUrl}/emergency_flatten`,
          { scope, idempotency_key: idempotencyKey },
          this.requestConfig(),
        )
        .pipe(
          retry({
            count: Math.max(0, this.retryAttempts - 1),
            delay: (error) => {
              const status = isAxiosError(error) ? error.response?.status : undefined;
              if (status !== undefined && status !== 429 && status < 500) {
                throw error;
              }
              return timer(this.retryDelay);
            },
          }),
        ),
    );
    return validateEmergencyFlattenResponse(response.data, scope, idempotencyKey);
  }

  private async postExecutionControl(
    action: 'halt' | 'resume',
    request: ExecutionControlRequest,
  ): Promise<ExecutionControlResponse> {
    const response = await firstValueFrom(
      this.httpService
        .post<ExecutionControlResponse>(
          `${this.baseUrl}/internal/execution-control/${action}`,
          request,
          this.requestConfig(),
        )
        .pipe(
          retry({
            count: Math.max(0, this.retryAttempts - 1),
            delay: this.retryDelay,
          }),
        ),
    );
    return validateExecutionControlResponse(response.data, request.idempotency_key);
  }

  async checkHealth(): Promise<HealthCheckResult> {
    const url = `${this.baseUrl}/healthz`;

    try {
      const response = await firstValueFrom(this.httpService.get(url, { timeout: 3000 }));

      return {
        status: 'up',
        details: {
          url: this.baseUrl,
          response: response.data,
        },
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      return {
        status: 'down',
        details: {
          url: this.baseUrl,
          error: errorMessage,
        },
      };
    }
  }

  async getReadiness(): Promise<RouterReadiness> {
    const url = `${this.baseUrl}/readyz`;

    try {
      // /readyz returns 503 while the startup reconciler runs; treat that as
      // a valid "reconciling" state, not a transport error.
      const response = await firstValueFrom(
        this.httpService.get<{ status?: string }>(url, {
          timeout: 3000,
          validateStatus: () => true,
        }),
      );
      const ready = response.status >= 200 && response.status < 300;
      // 200 -> ready, 503 -> reconciling; any other status is the router (or
      // a proxy) misbehaving, which is not a "reconciling" state.
      const fallback = ready ? 'ready' : response.status === 503 ? 'reconciling' : 'unreachable';
      return {
        ready,
        status: response.data?.status ?? fallback,
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      return { ready: false, status: 'unreachable', error: errorMessage };
    }
  }

  async getReconcileStatus(): Promise<ReconcileStatus> {
    const url = `${this.baseUrl}/internal/reconcile`;

    // GET is the router's read-only view of the last pass — no side effects.
    const response = await firstValueFrom(
      this.httpService.get<ReconcileStatus>(url, this.requestConfig({ timeout: 3000 })),
    );
    return response.data;
  }

  async closeAllPositions(request: CloseAllRequest): Promise<CloseAllResponse> {
    const url = `${this.baseUrl}/close_all`;

    this.logger.log(
      `Closing positions: symbol=${request.symbol || 'ALL'}, is_futures=${request.is_futures}`,
    );

    const config = this.requestConfig();

    try {
      const response = await firstValueFrom(
        this.httpService.post<CloseAllResponse>(url, request, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      this.logger.log(`Positions closed successfully`);
      return response.data;
    } catch (error) {
      this.logger.error(`Failed to close positions: ${error}`);
      throw error;
    }
  }

  async cancelOpenOrders(request: CancelOpenOrdersRequest): Promise<CancelOpenOrdersResponse> {
    const url = `${this.baseUrl}/cancel_open_orders`;

    const config = this.requestConfig();

    const response = await firstValueFrom(
      this.httpService.post<CancelOpenOrdersResponse>(url, request, config).pipe(
        retry({
          count: this.retryAttempts - 1,
          delay: this.retryDelay,
        }),
      ),
    );

    return response.data;
  }

  async closePositions(request: ClosePositionsRequest): Promise<ClosePositionsResponse> {
    const url = `${this.baseUrl}/close_positions`;

    const config = this.requestConfig();

    const response = await firstValueFrom(
      this.httpService.post<ClosePositionsResponse>(url, request, config).pipe(
        retry({
          count: this.retryAttempts - 1,
          delay: this.retryDelay,
        }),
      ),
    );

    return response.data;
  }
}
