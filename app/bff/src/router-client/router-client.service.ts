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
}

export interface HealthCheckResult {
  status: 'up' | 'down';
  details: {
    url: string;
    response?: any;
    error?: string;
  };
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
    this.baseUrl = this.configService.get<string>('router.url')!;
    this.timeout = this.configService.get<number>('router.timeout') || 5000;
    this.retryAttempts = this.configService.get<number>('router.retryAttempts') || 3;
    this.retryDelay = this.configService.get<number>('router.retryDelay') || 1000;
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
    const url = `${this.baseUrl}/health`;

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
}
