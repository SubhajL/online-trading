import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { AxiosRequestConfig } from 'axios';
import { firstValueFrom } from 'rxjs';
import { retry } from 'rxjs/operators';

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
  created_at?: string;
  partial_failure?: boolean;
  errors?: string[];
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

  async placeOrder(orderRequest: OrderRequest): Promise<RouterBracketPlacementResponse> {
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
    };

    try {
      const response = await firstValueFrom(
        this.httpService.post<RouterBracketPlacementResponse>(url, body, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      this.logger.log(`Bracket order placed successfully: ${response.data.bracket_order_id}`);
      return response.data;
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
