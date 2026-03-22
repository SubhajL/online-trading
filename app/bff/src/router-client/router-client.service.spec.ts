import { Test, TestingModule } from '@nestjs/testing';
import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { RouterClientService } from './router-client.service';
import { of, throwError } from 'rxjs';
import { AxiosResponse } from 'axios';

describe('RouterClientService', () => {
  let service: RouterClientService;
  let httpService: HttpService;
  let configService: ConfigService;

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
            main: 'main-1',
            take_profits: ['tp-1'],
            stop_loss: 'sl-1',
          },
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.001,
          created_at: '2026-03-21T20:00:00Z',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest);

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
            main: 'main-2',
            take_profits: ['tp-2'],
            stop_loss: 'sl-2',
          },
          symbol: 'BTCUSDT',
          side: 'BUY',
          quantity: 0.01,
          created_at: '2026-03-21T20:01:00Z',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest);

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
        },
        expect.any(Object),
      );
    });

    it('should use retry configuration', async () => {
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
        data: { orderId: '345678', status: 'NEW' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValue(of(mockResponse));

      const result = await service.placeOrder(orderRequest);

      expect(result).toEqual(mockResponse.data);
      // Verify that retry configuration is loaded
      expect(configService.get).toHaveBeenCalledWith('ROUTER_RETRY_ATTEMPTS');
      expect(configService.get).toHaveBeenCalledWith('ROUTER_RETRY_DELAY');
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

      await expect(service.placeOrder(orderRequest)).rejects.toThrow('Network error');
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
});
