import { Test, TestingModule } from '@nestjs/testing';
import { TradingController } from './trading.controller';
import { TradingService } from './trading.service';
import { OrderRequest } from '../router-client/router-client.service';

describe('TradingController', () => {
  let controller: TradingController;
  let service: TradingService;

  const mockTradingService = {
    placeOrder: jest.fn(),
    getOrderStatus: jest.fn(),
    cancelOrder: jest.fn(),
    getPositions: jest.fn(),
    getActiveOrders: jest.fn(),
    setAutoTrading: jest.fn(),
    isAutoTradingEnabled: jest.fn(),
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
      ],
    }).compile();

    controller = module.get<TradingController>(TradingController);
    service = module.get<TradingService>(TradingService);
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

      mockTradingService.placeOrder.mockResolvedValue(orderResponse);

      const result = await controller.placeOrder(orderRequest);

      expect(result).toEqual(orderResponse);
      expect(service.placeOrder).toHaveBeenCalledWith(orderRequest);
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

      mockTradingService.cancelOrder.mockResolvedValue(cancelResponse);

      const result = await controller.cancelOrder(orderId, cancelRequest);

      expect(result).toEqual(cancelResponse);
      expect(service.cancelOrder).toHaveBeenCalledWith(
        orderId,
        cancelRequest.symbol,
        cancelRequest.venue,
      );
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
      mockTradingService.isAutoTradingEnabled.mockReturnValue(true);

      const result = await controller.setAutoTrading({ enabled: true });

      expect(result).toEqual({ enabled: true, message: 'Auto trading enabled' });
      expect(service.setAutoTrading).toHaveBeenCalledWith(true);
    });

    it('should disable auto trading', async () => {
      mockTradingService.isAutoTradingEnabled.mockReturnValue(false);

      const result = await controller.setAutoTrading({ enabled: false });

      expect(result).toEqual({ enabled: false, message: 'Auto trading disabled' });
      expect(service.setAutoTrading).toHaveBeenCalledWith(false);
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
});
