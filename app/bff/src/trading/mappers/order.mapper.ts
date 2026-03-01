import { HttpException, HttpStatus } from '@nestjs/common';
import type { OrderRequest, OrderResponse } from '../../router-client/router-client.service';
import type { AxiosError } from 'axios';
import { v4 as uuidv4 } from 'uuid';

export type PlaceOrderDto = {
  symbol: string;
  side: 'BUY' | 'SELL';
  type: 'LIMIT' | 'MARKET' | 'STOP' | 'STOP_MARKET' | 'STOP_LIMIT';
  quantity: number;
  price?: number;
  stopPrice?: number;
  venue?: 'SPOT' | 'USD_M';
  clientOrderId?: string;
  reduceOnly?: boolean;
  timeInForce?: 'GTC' | 'IOC' | 'FOK';
};

export type OrderDto = {
  orderId: string;
  clientOrderId: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  type: string;
  quantity: number;
  price?: number;
  status: string;
  venue: 'SPOT' | 'USD_M';
  executedQty?: number;
  cummulativeQuoteQty?: number;
  createdAt: string;
  updatedAt: string;
};

export function generateClientOrderId(): string {
  return `cc-${uuidv4()}`;
}

export function mapPlaceOrderDtoToRouterRequest(dto: PlaceOrderDto): OrderRequest {
  return {
    symbol: dto.symbol,
    side: dto.side,
    type: dto.type === 'STOP_LIMIT' ? 'STOP' : dto.type,
    quantity: dto.quantity,
    price: dto.price,
    stopPrice: dto.stopPrice,
    venue: dto.venue || 'SPOT',
    reduceOnly: dto.reduceOnly,
    timeInForce: dto.timeInForce,
  };
}

export function mapRouterResponseToOrderDto(
  response: OrderResponse,
  clientOrderId: string,
  venue: 'SPOT' | 'USD_M',
): OrderDto {
  const now = new Date().toISOString();
  return {
    orderId: response.orderId,
    clientOrderId,
    symbol: response.symbol,
    side: response.side as 'BUY' | 'SELL',
    type: response.type,
    quantity: response.quantity,
    price: response.price,
    status: response.status,
    venue: response.venue || venue,
    executedQty: response.executedQty,
    cummulativeQuoteQty: response.cummulativeQuoteQty,
    createdAt: response.createdAt || now,
    updatedAt: response.updatedAt || now,
  };
}

type RouterErrorResponse = {
  code?: number;
  message?: string;
  error?: string;
};

export function mapRouterErrorToHttpException(error: unknown): HttpException {
  if (error instanceof HttpException) {
    return error;
  }

  const axiosError = error as AxiosError<RouterErrorResponse>;

  if (axiosError.response) {
    const status = axiosError.response.status;
    const data = axiosError.response.data;
    const message = data?.message || data?.error || 'Router request failed';

    if (status === 400) {
      return new HttpException(message, HttpStatus.BAD_REQUEST);
    }
    if (status === 401) {
      return new HttpException('Unauthorized: Invalid API credentials', HttpStatus.UNAUTHORIZED);
    }
    if (status === 403) {
      return new HttpException('Forbidden: Insufficient permissions', HttpStatus.FORBIDDEN);
    }
    if (status === 404) {
      return new HttpException('Order not found', HttpStatus.NOT_FOUND);
    }
    if (status === 429) {
      return new HttpException('Rate limit exceeded', HttpStatus.TOO_MANY_REQUESTS);
    }
    if (status >= 500) {
      return new HttpException('Router service unavailable', HttpStatus.SERVICE_UNAVAILABLE);
    }

    return new HttpException(message, status);
  }

  if (axiosError.code === 'ECONNABORTED' || axiosError.code === 'ETIMEDOUT') {
    return new HttpException('Router request timeout', HttpStatus.GATEWAY_TIMEOUT);
  }

  if (axiosError.code === 'ECONNREFUSED') {
    return new HttpException('Router service unavailable', HttpStatus.SERVICE_UNAVAILABLE);
  }

  const errorMessage = error instanceof Error ? error.message : 'Unknown error';
  return new HttpException(errorMessage, HttpStatus.INTERNAL_SERVER_ERROR);
}
