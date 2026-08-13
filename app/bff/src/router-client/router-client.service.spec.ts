import { Test, TestingModule } from '@nestjs/testing';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import {
  RouterClientService,
  validateEmergencyFlattenResponse,
  validateExecutionControlResponse,
  validateRouterBracketPlacement,
} from './router-client.service';
import { Observable, of, throwError } from 'rxjs';
import { AxiosResponse } from 'axios';
import { createRouterPlacementIdentity } from '../trading/placement-identity';

describe('RouterClientService', () => {
  let service: RouterClientService;
  let httpService: HttpService;
  let configService: ConfigService;

  const validExecutionControl = {
    scope: 'GLOBAL',
    state: 'HALTED',
    generation: 4,
    reason: 'operator request',
    requested_by: 'operator-1',
    idempotency_key: 'halt-key',
    requested_at: '2026-08-13T09:00:00Z',
    updated_at: '2026-08-13T09:00:00Z',
  };

  const emptyExchangeState = {
    open_orders: [],
    futures_positions: [],
    spot_balances: [],
    errors: [],
  };

  const validEmergencyFlatten = {
    scope: 'ALL',
    idempotency_key: 'flatten-key',
    starting: emptyExchangeState,
    final: emptyExchangeState,
    canceled_orders: 0,
    closed_futures_positions: 0,
    flattened_spot_assets: 0,
    residuals: [],
    fully_flattened: true,
    passes: 1,
    errors: [],
  };

  it.each([
    [{ ...validExecutionControl, generation: -1 }, 'generation'],
    [{ ...validExecutionControl, scope: 'ACCOUNT' }, 'scope'],
    [{ ...validExecutionControl, requested_at: '2026-08-13T09:00:00' }, 'requested_at'],
    [{ ...validExecutionControl, idempotency_key: 'wrong-key' }, 'idempotency_key'],
  ])('rejects malformed execution-control response field %s', (payload, field) => {
    expect(() => validateExecutionControlResponse(payload, 'halt-key')).toThrow(field);
  });

  it.each([
    [{ ...validEmergencyFlatten, fully_flattened: 'true' }, 'fully_flattened'],
    [{ ...validEmergencyFlatten, final: undefined }, 'final'],
    [{ ...validEmergencyFlatten, scope: 'SPOT' }, 'scope'],
    [{ ...validEmergencyFlatten, idempotency_key: 'wrong-key' }, 'idempotency_key'],
    [{ ...validEmergencyFlatten, passes: Number.NaN }, 'passes'],
  ])('rejects malformed emergency-flatten response field %s', (payload, field) => {
    expect(() => validateEmergencyFlattenResponse(payload, 'ALL', 'flatten-key')).toThrow(field);
  });

  it.each([
    [
      {
        ...validEmergencyFlatten,
        final: {
          ...emptyExchangeState,
          futures_positions: [{ symbol: 'BTCUSDT', quantity: '1', position_side: 'LONG' }],
        },
      },
      'fully_flattened',
    ],
    [
      {
        ...validEmergencyFlatten,
        fully_flattened: false,
        final: {
          ...emptyExchangeState,
          spot_balances: [
            {
              asset: 'BTC',
              symbol: 'BTCUSDT',
              quantity: '0.01',
              notional_usdt: '500',
              dust: false,
            },
          ],
        },
        residuals: [],
      },
      'residuals',
    ],
  ])('rejects contradictory emergency-flatten response field %s', (payload, field) => {
    expect(() => validateEmergencyFlattenResponse(payload, 'ALL', 'flatten-key')).toThrow(field);
  });

  it('accepts dust residuals and historical errors after a later successful pass', () => {
    const dustBalance = {
      asset: 'BTC',
      symbol: 'BTCUSDT',
      quantity: '0.000001',
      notional_usdt: '0.05',
      dust: true,
    };
    const payload = {
      ...validEmergencyFlatten,
      final: { ...emptyExchangeState, spot_balances: [dustBalance] },
      residuals: [dustBalance],
      errors: ['pass 1: temporary exchange timeout'],
      passes: 2,
    };

    expect(validateEmergencyFlattenResponse(payload, 'ALL', 'flatten-key')).toEqual(payload);
  });

  const mockConfigService = {
    get: jest.fn((key: string) => {
      const config: any = {
        ROUTER_URL: 'http://localhost:8080',
        ROUTER_API_KEY: 'router-secret',
        ROUTER_TIMEOUT: 5000,
        ROUTER_RETRY_ATTEMPTS: 3,
        ROUTER_RETRY_DELAY: 10, // Very short delay for tests
      };
      return config[key];
    }),
  };

  it.each([
    ['partial_failure', undefined],
    ['partial_failure', 'true'],
    ['legs_pending_trigger', undefined],
    ['legs_pending_trigger', 'false'],
    ['errors', undefined],
    ['created_at', 'not-a-timestamp'],
    ['created_at', '2026-08-13T09:00:00'],
    ['quantity', '0.01'],
    ['quantity', 'Infinity'],
    ['quantity', 0.0005],
  ])('rejects malformed placement field %s', (field, value) => {
    const request = {
      symbol: 'BTCUSDT',
      side: 'BUY' as const,
      type: 'LIMIT' as const,
      quantity: 0.001,
      price: 45000,
      stopLossPrice: 44000,
      takeProfitPrice: 47000,
      venue: 'SPOT' as const,
    };
    const identity = createRouterPlacementIdentity('user-1', 'malformed-field', 1);
    const response = {
      bracket_order_id: 'bracket-1',
      symbol: 'BTCUSDT',
      side: 'BUY',
      quantity: '0.001',
      created_at: '2026-08-13T09:00:00Z',
      partial_failure: false,
      legs_pending_trigger: false,
      errors: [],
      client_order_ids: {
        main: identity.clientOrderIds.main,
        take_profits: identity.clientOrderIds.takeProfits,
        stop_loss: identity.clientOrderIds.stopLoss,
      },
      [field]: value,
    };

    expect(() => validateRouterBracketPlacement(response, request, identity)).toThrow(
      `invalid ${field}`,
    );
  });

  const mockHttpService = {
    post: jest.fn(),
    get: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    // Reset mocks to default behavior
    mockHttpService.post.mockClear();
    mockHttpService.get.mockClear();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        RouterClientService,
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
        {
          provide: HttpService,
          useValue: mockHttpService,
        },
      ],
    }).compile();

    service = module.get<RouterClientService>(RouterClientService);
    httpService = module.get<HttpService>(HttpService);
    configService = module.get<ConfigService>(ConfigService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('placeOrder', () => {
    const placementIdentity = createRouterPlacementIdentity('user-123', 'click-456', 1);

    it('should place a spot order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 45000,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'SPOT' as const,
      };

      const mockResponse: AxiosResponse = {
        data: {
          bracket_order_id: '123456',
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.001,
          created_at: '2026-03-21T20:00:00Z',
          partial_failure: false,
          errors: [],
          legs_pending_trigger: false,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest, placementIdentity);

      expect(result).toEqual(mockResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/place_bracket',
        {
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.001,
          entry_price: 45000,
          take_profit_prices: [47000],
          stop_loss_price: 44000,
          order_type: 'LIMIT',
          is_futures: false,
          idempotency_key: placementIdentity.idempotencyKey,
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
        },
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer router-secret',
          }),
        }),
      );
    });

    it('should place a futures order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'USD_M' as const,
      };

      const mockResponse: AxiosResponse = {
        data: {
          bracket_order_id: '789012',
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.01,
          created_at: '2026-03-21T20:01:00Z',
          partial_failure: false,
          errors: [],
          legs_pending_trigger: false,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest, placementIdentity);

      expect(result).toEqual(mockResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/place_bracket',
        {
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.01,
          entry_price: undefined,
          take_profit_prices: [47000],
          stop_loss_price: 44000,
          order_type: 'MARKET',
          is_futures: true,
          idempotency_key: placementIdentity.idempotencyKey,
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
        },
        expect.any(Object),
      );
    });

    it('should accept a complete router placement response', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'SELL' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 50000,
        stopLossPrice: 51000,
        takeProfitPrice: 48000,
        venue: 'SPOT' as const,
      };

      const mockResponse: AxiosResponse = {
        data: {
          bracket_order_id: '345678',
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
          symbol: 'BTCUSDT',
          side: 'SELL',
          quantity: 0.001,
          created_at: '2026-08-13T09:00:00Z',
          partial_failure: false,
          errors: [],
          legs_pending_trigger: true,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest, placementIdentity);

      expect(result).toEqual(mockResponse.data);
      expect(configService.get).toHaveBeenCalledWith('ROUTER_RETRY_ATTEMPTS');
      expect(configService.get).toHaveBeenCalledWith('ROUTER_RETRY_DELAY');
    });

    it('should reject partial placement responses', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 45000,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'SPOT' as const,
      };
      mockHttpService.post.mockReturnValue(
        of({
          data: {
            bracket_order_id: 'partial-1',
            client_order_ids: {
              main: placementIdentity.clientOrderIds.main,
              take_profits: placementIdentity.clientOrderIds.takeProfits,
              stop_loss: placementIdentity.clientOrderIds.stopLoss,
            },
            symbol: 'BTCUSDT',
            side: 'BUY',
            quantity: 0.001,
            created_at: '2026-08-13T09:00:00Z',
            partial_failure: true,
            errors: ['stop placement failed'],
            legs_pending_trigger: false,
          },
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as AxiosResponse),
      );

      await expect(service.placeOrder(orderRequest, placementIdentity)).rejects.toThrow(
        'Router returned partial bracket placement',
      );
    });

    it('should reject malformed successful responses', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 45000,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'SPOT' as const,
      };
      mockHttpService.post.mockReturnValue(
        of({
          data: { bracket_order_id: '' },
          status: 200,
          statusText: 'OK',
          headers: {},
          config: {},
        } as AxiosResponse),
      );

      await expect(service.placeOrder(orderRequest, placementIdentity)).rejects.toThrow(
        'Router placement response missing bracket_order_id',
      );
    });

    it('reuses the exact stable body across an ambiguous transport retry', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 45000,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'SPOT' as const,
      };
      let subscriptions = 0;
      mockHttpService.post.mockReturnValue(
        new Observable((subscriber) => {
          subscriptions += 1;
          if (subscriptions < 3) {
            subscriber.error(new Error('connection reset'));
            return;
          }
          subscriber.next({
            data: {
              bracket_order_id: 'replayed-bracket',
              client_order_ids: {
                main: placementIdentity.clientOrderIds.main,
                take_profits: placementIdentity.clientOrderIds.takeProfits,
                stop_loss: placementIdentity.clientOrderIds.stopLoss,
              },
              symbol: 'BTCUSDT',
              side: 'BUY',
              quantity: 0.001,
              created_at: '2026-08-13T09:00:00Z',
              partial_failure: false,
              errors: [],
              legs_pending_trigger: false,
            },
          } as AxiosResponse);
          subscriber.complete();
        }),
      );

      await expect(service.placeOrder(orderRequest, placementIdentity)).resolves.toEqual(
        expect.objectContaining({ bracket_order_id: 'replayed-bracket' }),
      );
      expect(subscriptions).toBe(3);
      expect(httpService.post).toHaveBeenCalledTimes(1);
      expect(mockHttpService.post.mock.calls[0][1]).toEqual(
        expect.objectContaining({
          idempotency_key: placementIdentity.idempotencyKey,
          client_order_ids: {
            main: placementIdentity.clientOrderIds.main,
            take_profits: placementIdentity.clientOrderIds.takeProfits,
            stop_loss: placementIdentity.clientOrderIds.stopLoss,
          },
        }),
      );
    });

    it('should throw error on failure', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'LIMIT' as const,
        quantity: 0.001,
        price: 45000,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'SPOT' as const,
      };

      const error = new Error('Network error');
      mockHttpService.post.mockReturnValue(throwError(() => error));

      await expect(service.placeOrder(orderRequest, placementIdentity)).rejects.toThrow(
        'Network error',
      );
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/place_bracket',
        expect.any(Object),
        expect.any(Object),
      );
    });
  });

  describe('cancelOrder', () => {
    it('should cancel order successfully', async () => {
      const cancelRequest = {
        symbol: 'BTCUSDT',
        venue: 'USD_M' as const,
        orderId: '123456',
        exchangeOrderId: '987654',
      };

      const cancelResponse: AxiosResponse = {
        data: {
          success: true,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValueOnce(of(cancelResponse));

      const result = await service.cancelOrder(cancelRequest);

      expect(result).toEqual(cancelResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/cancel',
        {
          symbol: 'BTCUSDT',
          order_id: 987654,
        },
        expect.any(Object),
      );
    });

    it('should fall back to client_order_id when exchange order id is unavailable', async () => {
      const cancelRequest = {
        symbol: 'ETHUSDT',
        venue: 'SPOT' as const,
        orderId: 'abc-123',
        clientOrderId: 'main-spot-1',
      };

      const cancelResponse: AxiosResponse = {
        data: {
          success: true,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValueOnce(of(cancelResponse));

      const result = await service.cancelOrder(cancelRequest);

      expect(result).toEqual(cancelResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/cancel',
        {
          symbol: 'ETHUSDT',
          client_order_id: 'main-spot-1',
        },
        expect.any(Object),
      );
    });
  });

  describe('closeAllPositions', () => {
    it('should close all positions successfully', async () => {
      const request = {
        is_futures: false,
      };

      const mockResponse: AxiosResponse = {
        data: {
          success: true,
          message: 'All positions closed',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.closeAllPositions(request);

      expect(result).toEqual(mockResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/close_all',
        request,
        expect.any(Object),
      );
    });

    it('should close futures positions', async () => {
      const request = {
        is_futures: true,
      };

      const mockResponse: AxiosResponse = {
        data: {
          success: true,
          message: 'All futures positions closed',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.closeAllPositions(request);

      expect(result).toEqual(mockResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/close_all',
        request,
        expect.any(Object),
      );
    });

    it('should throw error on failure', async () => {
      const request = {
        is_futures: false,
      };

      const error = new Error('Connection refused');
      mockHttpService.post.mockReturnValue(throwError(() => error));

      await expect(service.closeAllPositions(request)).rejects.toThrow('Connection refused');
    });
  });

  describe('health check', () => {
    it('should check router health successfully', async () => {
      const mockResponse: AxiosResponse = {
        data: {
          status: 'healthy',
          timestamp: new Date().toISOString(),
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.get.mockReturnValue(of(mockResponse));

      const result = await service.checkHealth();

      expect(mockHttpService.get).toHaveBeenCalledWith('http://localhost:8080/healthz', {
        timeout: 3000,
      });
      expect(result).toEqual({
        status: 'up',
        details: {
          url: 'http://localhost:8080',
          response: mockResponse.data,
        },
      });
    });

    it('should report unhealthy on error', async () => {
      mockHttpService.get.mockReturnValue(throwError(() => new Error('Connection refused')));

      const result = await service.checkHealth();

      expect(mockHttpService.get).toHaveBeenCalledWith('http://localhost:8080/healthz', {
        timeout: 3000,
      });
      expect(result).toEqual({
        status: 'down',
        details: {
          url: 'http://localhost:8080',
          error: 'Connection refused',
        },
      });
    });
  });

  describe('getReadiness', () => {
    const readyResponse = (status: number, body: unknown): AxiosResponse =>
      ({ data: body, status, statusText: '', headers: {}, config: {} }) as any;

    it('reports ready on 200', async () => {
      mockHttpService.get.mockReturnValue(of(readyResponse(200, { status: 'ready' })));

      const result = await service.getReadiness();

      expect(mockHttpService.get).toHaveBeenCalledWith('http://localhost:8080/readyz', {
        timeout: 3000,
        validateStatus: expect.any(Function),
      });
      expect(result).toEqual({ ready: true, status: 'ready' });
    });

    it('treats 503 as reconciling, not an error', async () => {
      mockHttpService.get.mockReturnValue(of(readyResponse(503, { status: 'reconciling' })));

      const result = await service.getReadiness();

      expect(result).toEqual({ ready: false, status: 'reconciling' });
    });

    it('reports unreachable on transport failure', async () => {
      mockHttpService.get.mockReturnValue(throwError(() => new Error('ECONNREFUSED')));

      const result = await service.getReadiness();

      expect(result).toEqual({ ready: false, status: 'unreachable', error: 'ECONNREFUSED' });
    });

    it('maps a non-503 error status to unreachable, not reconciling', async () => {
      // A proxy 502 with no JSON status must not read as "reconciling"
      mockHttpService.get.mockReturnValue(of(readyResponse(502, {})));

      const result = await service.getReadiness();

      expect(result).toEqual({ ready: false, status: 'unreachable' });
    });
  });

  describe('getReconcileStatus', () => {
    it('GETs the read-only reconcile status with the auth header', async () => {
      const status = {
        has_run: true,
        last_run_at: '2026-07-06T00:00:00Z',
        summary: {
          brackets_swept: 2,
          entries_checked: 1,
          legs_resolved: 0,
          exit_legs_updated: 1,
          brackets_closed: 1,
          stale_reserved: 0,
          unrepaired_legs: 0,
          errors: 0,
        },
      };
      mockHttpService.get.mockReturnValue(
        of({ data: status, status: 200, statusText: 'OK', headers: {}, config: {} } as any),
      );

      const result = await service.getReconcileStatus();

      const [url, config] = mockHttpService.get.mock.calls[0];
      expect(url).toBe('http://localhost:8080/internal/reconcile');
      expect(config.headers.Authorization).toBe('Bearer router-secret');
      expect(result).toEqual(status);
    });
  });
});
