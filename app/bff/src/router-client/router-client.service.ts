import { Injectable, Logger } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { AxiosRequestConfig } from 'axios';
import { firstValueFrom } from 'rxjs';
import { retry } from 'rxjs/operators';

export interface OrderRequest {
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET' | 'STOP' | 'STOP_MARKET';
  quantity: number;
  price?: number;
  stopPrice?: number;
  venue: 'SPOT' | 'USD_M';
  reduceOnly?: boolean;
  timeInForce?: 'GTC' | 'IOC' | 'FOK';
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

export interface HealthCheckResult {
  status: 'up' | 'down';
  details: {
    url: string;
    response?: unknown;
    error?: string;
  };
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
  private readonly timeout: number;
  private readonly retryAttempts: number;
  private readonly retryDelay: number;

  constructor(
    private readonly httpService: HttpService,
    private readonly configService: ConfigService,
  ) {
    // Use flat env var names since ConfigModule doesn't load nested config
    this.baseUrl = this.configService.get<string>('ROUTER_URL') || 'http://localhost:8001';
    this.timeout = this.configService.get<number>('ROUTER_TIMEOUT') || 5000;
    this.retryAttempts = this.configService.get<number>('ROUTER_RETRY_ATTEMPTS') || 3;
    this.retryDelay = this.configService.get<number>('ROUTER_RETRY_DELAY') || 1000;
  }

  async placeOrder(orderRequest: OrderRequest): Promise<OrderResponse> {
    const venue = orderRequest.venue === 'USD_M' ? 'futures' : orderRequest.venue.toLowerCase();
    const url = `${this.baseUrl}/api/orders/${venue}`;

    this.logger.log(`Placing ${orderRequest.venue} order: ${JSON.stringify(orderRequest)}`);

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    try {
      const response = await firstValueFrom(
        this.httpService.post<OrderResponse>(url, orderRequest, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      this.logger.log(`Order placed successfully: ${response.data.orderId}`);
      return response.data;
    } catch (error) {
      this.logger.error(`Failed to place order: ${error}`);
      throw error;
    }
  }

  async getOrderStatus(orderId: string, venue: 'SPOT' | 'USD_M'): Promise<OrderResponse> {
    const venueParam = venue === 'USD_M' ? 'futures' : venue.toLowerCase();
    const url = `${this.baseUrl}/api/orders/${venueParam}/${orderId}`;

    this.logger.log(`Getting order status for ${orderId} on ${venue}`);

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
    };

    try {
      const response = await firstValueFrom(
        this.httpService.get<OrderResponse>(url, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      return response.data;
    } catch (error) {
      this.logger.error(`Failed to get order status: ${error}`);
      throw error;
    }
  }

  async cancelOrder(
    orderId: string,
    symbol: string,
    venue: 'SPOT' | 'USD_M',
  ): Promise<OrderResponse> {
    const venueParam = venue === 'USD_M' ? 'futures' : venue.toLowerCase();
    const url = `${this.baseUrl}/api/orders/${venueParam}/${orderId}/cancel`;

    this.logger.log(`Canceling order ${orderId} for ${symbol} on ${venue}`);

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    const body = { symbol };

    try {
      const response = await firstValueFrom(
        this.httpService.post<OrderResponse>(url, body, config).pipe(
          retry({
            count: this.retryAttempts - 1,
            delay: this.retryDelay,
          }),
        ),
      );

      this.logger.log(`Order canceled successfully: ${orderId}`);
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

  async closeAllPositions(request: CloseAllRequest): Promise<CloseAllResponse> {
    const url = `${this.baseUrl}/close_all`;

    this.logger.log(
      `Closing positions: symbol=${request.symbol || 'ALL'}, is_futures=${request.is_futures}`,
    );

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    };

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

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    };

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

    const config: AxiosRequestConfig = {
      timeout: this.timeout,
      headers: {
        'Content-Type': 'application/json',
      },
    };

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
