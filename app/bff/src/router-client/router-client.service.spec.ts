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
        venue: 'SPOT' as const,
      };

      const mockResponse: AxiosResponse = {
        data: {
          orderId: '123456',
          status: 'NEW',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'LIMIT',
          quantity: 0.001,
          price: 45000,
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
        'http://localhost:8080/api/orders/spot',
        orderRequest,
        expect.any(Object),
      );
    });

    it('should place a futures order successfully', async () => {
      const orderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY' as const,
        type: 'MARKET' as const,
        quantity: 0.01,
        venue: 'USD_M' as const,
      };

      const mockResponse: AxiosResponse = {
        data: {
          orderId: '789012',
          status: 'NEW',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'MARKET',
          quantity: 0.01,
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
        'http://localhost:8080/api/orders/futures',
        orderRequest,
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
        venue: 'SPOT' as const,
      };

      const error = new Error('Network error');
      mockHttpService.post.mockReturnValue(throwError(() => error));

      await expect(service.placeOrder(orderRequest)).rejects.toThrow('Network error');
      expect(httpService.post).toHaveBeenCalledWith(
        'http://localhost:8080/api/orders/spot',
        orderRequest,
        expect.any(Object),
      );
    });
  });

  describe('getOrderStatus', () => {
    it('should get order status successfully', async () => {
      const orderId = '123456';
      const venue = 'SPOT' as const;

      const mockResponse: AxiosResponse = {
        data: {
          orderId: '123456',
          status: 'FILLED',
          executedQty: 0.001,
          cummulativeQuoteQty: 45,
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.get.mockReturnValue(of(mockResponse));

      const result = await service.getOrderStatus(orderId, venue);

      expect(result).toEqual(mockResponse.data);
      expect(httpService.get).toHaveBeenCalledWith(
        `http://localhost:8080/api/orders/spot/${orderId}`,
        expect.any(Object),
      );
    });
  });

  describe('cancelOrder', () => {
    it('should cancel order successfully', async () => {
      const orderId = '123456';
      const symbol = 'BTCUSDT';
      const venue = 'USD_M' as const;

      const cancelResponse: AxiosResponse = {
        data: {
          orderId: '123456',
          status: 'CANCELED',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: {},
      } as any;

      mockHttpService.post.mockReturnValueOnce(of(cancelResponse));

      const result = await service.cancelOrder(orderId, symbol, venue);

      expect(result).toEqual(cancelResponse.data);
      expect(httpService.post).toHaveBeenCalledWith(
        `http://localhost:8080/api/orders/futures/${orderId}/cancel`,
        { symbol },
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
