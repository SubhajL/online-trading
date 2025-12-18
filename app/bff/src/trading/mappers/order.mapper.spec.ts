import { HttpException, HttpStatus } from '@nestjs/common';
import { AxiosError, AxiosHeaders } from 'axios';
import {
  generateClientOrderId,
  mapPlaceOrderDtoToRouterRequest,
  mapRouterResponseToOrderDto,
  mapRouterErrorToHttpException,
  PlaceOrderDto,
} from './order.mapper';
import type { OrderResponse } from '../../router-client/router-client.service';

describe('order.mapper', () => {
  describe('generateClientOrderId', () => {
    it('generates unique IDs with cc- prefix', () => {
      const id1 = generateClientOrderId();
      const id2 = generateClientOrderId();

      expect(id1).toMatch(/^cc-[a-f0-9-]{36}$/);
      expect(id2).toMatch(/^cc-[a-f0-9-]{36}$/);
      expect(id1).not.toBe(id2);
    });
  });

  describe('mapPlaceOrderDtoToRouterRequest', () => {
    const baseDto: PlaceOrderDto = {
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    };

    it('maps all required fields correctly', () => {
      const result = mapPlaceOrderDtoToRouterRequest(baseDto);

      expect(result).toEqual({
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.001,
        price: undefined,
        stopPrice: undefined,
        venue: 'SPOT',
        reduceOnly: undefined,
        timeInForce: undefined,
      });
    });

    it('defaults venue to SPOT when not provided', () => {
      const result = mapPlaceOrderDtoToRouterRequest(baseDto);
      expect(result.venue).toBe('SPOT');
    });

    it('uses provided venue when specified', () => {
      const dto: PlaceOrderDto = { ...baseDto, venue: 'USD_M' };
      const result = mapPlaceOrderDtoToRouterRequest(dto);
      expect(result.venue).toBe('USD_M');
    });

    it('maps LIMIT order with price', () => {
      const dto: PlaceOrderDto = {
        ...baseDto,
        type: 'LIMIT',
        price: 50000.0,
        timeInForce: 'GTC',
      };
      const result = mapPlaceOrderDtoToRouterRequest(dto);

      expect(result.type).toBe('LIMIT');
      expect(result.price).toBe(50000.0);
      expect(result.timeInForce).toBe('GTC');
    });

    it('maps STOP_LIMIT to STOP type', () => {
      const dto: PlaceOrderDto = {
        ...baseDto,
        type: 'STOP_LIMIT',
        price: 49000.0,
        stopPrice: 50000.0,
      };
      const result = mapPlaceOrderDtoToRouterRequest(dto);

      expect(result.type).toBe('STOP');
      expect(result.price).toBe(49000.0);
      expect(result.stopPrice).toBe(50000.0);
    });

    it('maps STOP_MARKET order', () => {
      const dto: PlaceOrderDto = {
        ...baseDto,
        type: 'STOP_MARKET',
        stopPrice: 48000.0,
      };
      const result = mapPlaceOrderDtoToRouterRequest(dto);

      expect(result.type).toBe('STOP_MARKET');
      expect(result.stopPrice).toBe(48000.0);
    });

    it('maps reduceOnly for futures', () => {
      const dto: PlaceOrderDto = {
        ...baseDto,
        venue: 'USD_M',
        reduceOnly: true,
      };
      const result = mapPlaceOrderDtoToRouterRequest(dto);
      expect(result.reduceOnly).toBe(true);
    });
  });

  describe('mapRouterResponseToOrderDto', () => {
    const baseResponse: OrderResponse = {
      orderId: '12345',
      status: 'NEW',
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.001,
    };
    const clientOrderId = 'cc-test-123';
    const venue: 'SPOT' | 'USD_M' = 'SPOT';

    it('maps all fields correctly', () => {
      const result = mapRouterResponseToOrderDto(baseResponse, clientOrderId, venue);

      expect(result.orderId).toBe('12345');
      expect(result.clientOrderId).toBe(clientOrderId);
      expect(result.symbol).toBe('BTCUSDT');
      expect(result.side).toBe('BUY');
      expect(result.type).toBe('MARKET');
      expect(result.quantity).toBe(0.001);
      expect(result.status).toBe('NEW');
      expect(result.venue).toBe('SPOT');
    });

    it('uses venue from response when available', () => {
      const responseWithVenue: OrderResponse = {
        ...baseResponse,
        venue: 'USD_M',
      };
      const result = mapRouterResponseToOrderDto(responseWithVenue, clientOrderId, 'SPOT');
      expect(result.venue).toBe('USD_M');
    });

    it('falls back to provided venue when response has no venue', () => {
      const result = mapRouterResponseToOrderDto(baseResponse, clientOrderId, 'USD_M');
      expect(result.venue).toBe('USD_M');
    });

    it('includes price and executedQty when present', () => {
      const responseWithDetails: OrderResponse = {
        ...baseResponse,
        price: 50000.0,
        executedQty: 0.0005,
        cummulativeQuoteQty: 25.0,
      };
      const result = mapRouterResponseToOrderDto(responseWithDetails, clientOrderId, venue);

      expect(result.price).toBe(50000.0);
      expect(result.executedQty).toBe(0.0005);
      expect(result.cummulativeQuoteQty).toBe(25.0);
    });

    it('uses response timestamps when available', () => {
      const responseWithTimestamps: OrderResponse = {
        ...baseResponse,
        createdAt: '2024-01-01T00:00:00Z',
        updatedAt: '2024-01-01T00:00:01Z',
      };
      const result = mapRouterResponseToOrderDto(responseWithTimestamps, clientOrderId, venue);

      expect(result.createdAt).toBe('2024-01-01T00:00:00Z');
      expect(result.updatedAt).toBe('2024-01-01T00:00:01Z');
    });

    it('generates timestamps when not in response', () => {
      const result = mapRouterResponseToOrderDto(baseResponse, clientOrderId, venue);

      expect(result.createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
      expect(result.updatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    });
  });

  describe('mapRouterErrorToHttpException', () => {
    function createAxiosError(status: number, data: unknown, code?: string): AxiosError {
      const error = new Error('Request failed') as AxiosError;
      error.isAxiosError = true;
      error.code = code;
      if (status) {
        error.response = {
          status,
          data,
          statusText: 'Error',
          headers: {},
          config: { headers: new AxiosHeaders() },
        };
      }
      return error;
    }

    it('returns existing HttpException unchanged', () => {
      const original = new HttpException('Original error', HttpStatus.BAD_REQUEST);
      const result = mapRouterErrorToHttpException(original);

      expect(result).toBe(original);
    });

    it('maps 400 to BAD_REQUEST', () => {
      const error = createAxiosError(400, { message: 'Invalid symbol' });
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.BAD_REQUEST);
      expect(result.message).toBe('Invalid symbol');
    });

    it('maps 401 to UNAUTHORIZED', () => {
      const error = createAxiosError(401, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.UNAUTHORIZED);
      expect(result.message).toBe('Unauthorized: Invalid API credentials');
    });

    it('maps 403 to FORBIDDEN', () => {
      const error = createAxiosError(403, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.FORBIDDEN);
      expect(result.message).toBe('Forbidden: Insufficient permissions');
    });

    it('maps 404 to NOT_FOUND', () => {
      const error = createAxiosError(404, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.NOT_FOUND);
      expect(result.message).toBe('Order not found');
    });

    it('maps 429 to TOO_MANY_REQUESTS', () => {
      const error = createAxiosError(429, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.TOO_MANY_REQUESTS);
      expect(result.message).toBe('Rate limit exceeded');
    });

    it('maps 5xx to SERVICE_UNAVAILABLE', () => {
      const error = createAxiosError(503, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.SERVICE_UNAVAILABLE);
      expect(result.message).toBe('Router service unavailable');
    });

    it('maps timeout error to GATEWAY_TIMEOUT', () => {
      const error = createAxiosError(0, null, 'ECONNABORTED');
      error.response = undefined;
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.GATEWAY_TIMEOUT);
      expect(result.message).toBe('Router request timeout');
    });

    it('maps connection refused to SERVICE_UNAVAILABLE', () => {
      const error = createAxiosError(0, null, 'ECONNREFUSED');
      error.response = undefined;
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.SERVICE_UNAVAILABLE);
      expect(result.message).toBe('Router service unavailable');
    });

    it('maps unknown Error to INTERNAL_SERVER_ERROR with message', () => {
      const error = new Error('Something went wrong');
      const result = mapRouterErrorToHttpException(error);

      expect(result.getStatus()).toBe(HttpStatus.INTERNAL_SERVER_ERROR);
      expect(result.message).toBe('Something went wrong');
    });

    it('uses error field when message is not present', () => {
      const error = createAxiosError(400, { error: 'Validation failed' });
      const result = mapRouterErrorToHttpException(error);

      expect(result.message).toBe('Validation failed');
    });

    it('uses default message when response has no message or error', () => {
      const error = createAxiosError(400, {});
      const result = mapRouterErrorToHttpException(error);

      expect(result.message).toBe('Router request failed');
    });
  });
});
