import { Test, TestingModule } from '@nestjs/testing';
import { TradingController } from './trading.controller';
import { TradingService } from './trading.service';
import { OrderRequest } from '../router-client/router-client.service';
import { CommandBus } from '@nestjs/cqrs';
import { EmergencyCloseService } from './emergency-close.service';
import type { AuthenticatedRequest } from '../auth/interfaces/authenticated-request.interface';

describe('TradingController', () => {
  let controller: TradingController;
  let service: TradingService;
  let commandBus: CommandBus;

  const mockTradingService = {
    placeOrder: jest.fn(),
    getOrderStatus: jest.fn(),
    cancelOrder: jest.fn(),
    getPositions: jest.fn(),
    getActiveOrders: jest.fn(),
    setAutoTrading: jest.fn(),
    isAutoTradingEnabled: jest.fn(),
    emergencyClose: jest.fn(),
  };

  const mockEmergencyCloseService = {
    execute: jest.fn(),
  };

  const mockCommandBus = {
    execute: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [TradingController],
      providers: [
        {
          provide: TradingService,
          useValue: mockTradingService,
        },
        {
          provide: CommandBus,
          useValue: mockCommandBus,
        },
        {
          provide: EmergencyCloseService,
          useValue: mockEmergencyCloseService,
        },
      ],
    }).compile();

    controller = module.get<TradingController>(TradingController);
    service = module.get<TradingService>(TradingService);
    commandBus = module.get<CommandBus>(CommandBus);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('POST /orders', () => {
    it('should place an order', async () => {
      const orderRequest: OrderRequest = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
        stopLossPrice: 44000,
        takeProfitPrice: 47000,
        venue: 'USD_M',
      };

      const orderResponse = {
        orderId: '123456',
        status: 'NEW',
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.01,
      };

      mockCommandBus.execute.mockResolvedValue(orderResponse);

      const mockRequest = { user: { sub: 'user-123' } } as unknown as AuthenticatedRequest;
      const result = await controller.placeOrder(mockRequest, orderRequest);

      expect(result).toEqual(orderResponse);
      expect(commandBus.execute).toHaveBeenCalledTimes(1);
    });
  });

  describe('GET /orders/:orderId', () => {
    it('should get order status', async () => {
      const orderId = '123456';
      const venue = 'USD_M';

      const orderStatus = {
        orderId: '123456',
        status: 'FILLED',
        executedQty: 0.01,
        cummulativeQuoteQty: 450,
      };

      mockTradingService.getOrderStatus.mockResolvedValue(orderStatus);

      const result = await controller.getOrderStatus(orderId, venue);

      expect(result).toEqual(orderStatus);
      expect(service.getOrderStatus).toHaveBeenCalledWith(orderId, venue);
    });
  });

  describe('DELETE /orders/:orderId', () => {
    it('should cancel an order', async () => {
      const orderId = '123456';
      const cancelRequest = {
        symbol: 'BTCUSDT',
        venue: 'USD_M' as const,
      };

      const cancelResponse = {
        orderId: '123456',
        status: 'CANCELED',
      };

      mockCommandBus.execute.mockResolvedValue(cancelResponse);

      const mockRequest = { user: { sub: 'user-123' } } as unknown as AuthenticatedRequest;
      const result = await controller.cancelOrder(mockRequest, orderId, cancelRequest);

      expect(result).toEqual(cancelResponse);
      expect(commandBus.execute).toHaveBeenCalledTimes(1);
    });
  });

  describe('GET /positions', () => {
    it('should get current positions', async () => {
      const positions = [
        {
          symbol: 'BTCUSDT',
          side: 'LONG',
          quantity: 0.01,
          entryPrice: 45000,
          currentPrice: 46000,
          pnl: 10,
          pnlPercent: 2.22,
        },
      ];

      mockTradingService.getPositions.mockResolvedValue(positions);

      const result = await controller.getPositions();

      expect(result).toEqual(positions);
      expect(service.getPositions).toHaveBeenCalled();
    });
  });

  describe('GET /orders', () => {
    it('should get active orders', async () => {
      const orders = [
        {
          orderId: '123456',
          status: 'NEW',
          symbol: 'BTCUSDT',
          side: 'BUY',
          type: 'LIMIT',
          quantity: 0.01,
          price: 45000,
        },
      ];

      mockTradingService.getActiveOrders.mockResolvedValue(orders);

      const result = await controller.getActiveOrders();

      expect(result).toEqual(orders);
      expect(service.getActiveOrders).toHaveBeenCalled();
    });
  });

  describe('POST /auto-trading', () => {
    it('should enable auto trading', async () => {
      mockCommandBus.execute.mockResolvedValue(undefined);

      const mockRequest = { user: { sub: 'user-123' } } as unknown as AuthenticatedRequest;
      const result = await controller.setAutoTrading(mockRequest, { enabled: true });

      expect(result).toEqual({ enabled: true, message: 'Auto trading enabled' });
      expect(commandBus.execute).toHaveBeenCalledTimes(1);
    });

    it('should disable auto trading', async () => {
      mockCommandBus.execute.mockResolvedValue(undefined);

      const mockRequest = { user: { sub: 'user-123' } } as unknown as AuthenticatedRequest;
      const result = await controller.setAutoTrading(mockRequest, { enabled: false });

      expect(result).toEqual({ enabled: false, message: 'Auto trading disabled' });
      expect(commandBus.execute).toHaveBeenCalledTimes(1);
    });
  });

  describe('GET /auto-trading', () => {
    it('should get auto trading status', () => {
      mockTradingService.isAutoTradingEnabled.mockReturnValue(true);

      const result = controller.getAutoTradingStatus();

      expect(result).toEqual({ enabled: true });
      expect(service.isAutoTradingEnabled).toHaveBeenCalled();
    });
  });

  describe('POST /emergency-close', () => {
    it('should close all positions successfully', async () => {
      const dto = { scope: 'ALL' as const };
      const idempotencyKey = 'test-key-123';

      mockEmergencyCloseService.execute.mockResolvedValue({
        success: true,
        scope: 'ALL',
        stopEngine: false,
        idempotencyKey,
        canceledOrders: 0,
        closedPositions: 2,
        autoTradingDisabled: false,
        steps: [],
        executionTimeMs: 1,
      });

      const result = await controller.emergencyClose(dto, idempotencyKey);

      expect(result.success).toBe(true);
      expect(result.closedPositions).toBe(2);
      expect(mockEmergencyCloseService.execute).toHaveBeenCalledWith(dto, idempotencyKey);
    });

    it('should close SPOT positions only', async () => {
      const dto = { scope: 'SPOT' as const };
      const idempotencyKey = 'test-key-456';

      mockEmergencyCloseService.execute.mockResolvedValue({
        success: true,
        scope: 'SPOT',
        stopEngine: false,
        idempotencyKey,
        canceledOrders: 0,
        closedPositions: 0,
        autoTradingDisabled: false,
        steps: [],
        executionTimeMs: 1,
      });

      const result = await controller.emergencyClose(dto, idempotencyKey);

      expect(result.success).toBe(true);
      expect(mockEmergencyCloseService.execute).toHaveBeenCalledWith(dto, idempotencyKey);
    });

    it('should close FUTURES positions only', async () => {
      const dto = { scope: 'FUTURES' as const };
      const idempotencyKey = 'test-key-789';

      mockEmergencyCloseService.execute.mockResolvedValue({
        success: true,
        scope: 'FUTURES',
        stopEngine: false,
        idempotencyKey,
        canceledOrders: 0,
        closedPositions: 1,
        autoTradingDisabled: false,
        steps: [],
        executionTimeMs: 1,
      });

      const result = await controller.emergencyClose(dto, idempotencyKey);

      expect(result.success).toBe(true);
      expect(mockEmergencyCloseService.execute).toHaveBeenCalledWith(dto, idempotencyKey);
    });

    it('should stop engine when requested', async () => {
      const dto = { scope: 'ALL' as const, stopEngine: true };
      const idempotencyKey = 'test-key-stop';

      mockEmergencyCloseService.execute.mockResolvedValue({
        success: true,
        scope: 'ALL',
        stopEngine: true,
        idempotencyKey,
        canceledOrders: 0,
        closedPositions: 2,
        autoTradingDisabled: true,
        steps: [],
        executionTimeMs: 1,
      });

      await controller.emergencyClose(dto, idempotencyKey);

      expect(mockEmergencyCloseService.execute).toHaveBeenCalledWith(dto, idempotencyKey);
    });

    it('should handle errors gracefully', async () => {
      const dto = { scope: 'ALL' as const };
      const idempotencyKey = 'test-key-error';

      mockEmergencyCloseService.execute.mockRejectedValue(new Error('Connection failed'));

      await expect(controller.emergencyClose(dto, idempotencyKey)).rejects.toThrow(
        'Connection failed',
      );
    });
  });
});
