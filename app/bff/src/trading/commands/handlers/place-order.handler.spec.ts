import { Test, TestingModule } from '@nestjs/testing';
import { PlaceOrderHandler } from './place-order.handler';
import { PlaceOrderCommand } from '../place-order.command';
import { TradingService } from '../../trading.service';
import { BadRequestException } from '@nestjs/common';
import type { OrderRequest, OrderResponse } from '../../../router-client/router-client.service';

describe('PlaceOrderHandler', () => {
  let handler: PlaceOrderHandler;
  let tradingService: TradingService;

  const mockTradingService = {
    placeOrder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        PlaceOrderHandler,
        {
          provide: TradingService,
          useValue: mockTradingService,
        },
      ],
    }).compile();

    handler = module.get<PlaceOrderHandler>(PlaceOrderHandler);
    tradingService = module.get<TradingService>(TradingService);
    jest.clearAllMocks();
  });

  const validOrderRequest: OrderRequest = {
    symbol: 'BTCUSDT',
    side: 'BUY',
    type: 'MARKET',
    quantity: 0.001,
    stopLossPrice: 44000,
    takeProfitPrice: 47000,
    venue: 'SPOT',
  };

  const mockOrderResponse: OrderResponse = {
    orderId: 'order-123',
    symbol: 'BTCUSDT',
    side: 'BUY',
    type: 'MARKET',
    status: 'NEW',
    quantity: 0.001,
    executedQty: 0,
  };

  describe('execute', () => {
    it('should place order successfully', async () => {
      mockTradingService.placeOrder.mockResolvedValue(mockOrderResponse);

      const command = new PlaceOrderCommand('user-123', validOrderRequest);
      const result = await handler.execute(command);

      expect(result).toEqual(mockOrderResponse);
      expect(tradingService.placeOrder).toHaveBeenCalledWith(validOrderRequest);
    });

    it('should validate required order fields', async () => {
      const invalidOrder = { ...validOrderRequest, quantity: 0 };
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should validate minimum order quantity', async () => {
      const invalidOrder = { ...validOrderRequest, quantity: 0.00001 };
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should validate order side is BUY or SELL', async () => {
      const invalidOrder = { ...validOrderRequest, side: 'INVALID' as any };
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should validate order type is MARKET or LIMIT', async () => {
      const invalidOrder = { ...validOrderRequest, type: 'STOP' as any };
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should require price for LIMIT orders', async () => {
      const limitOrder = { ...validOrderRequest, type: 'LIMIT' as const, price: undefined };
      const command = new PlaceOrderCommand('user-123', limitOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should require stop loss price', async () => {
      const invalidOrder = {
        ...validOrderRequest,
        stopLossPrice: undefined,
      } as unknown as OrderRequest;
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should require take profit price', async () => {
      const invalidOrder = {
        ...validOrderRequest,
        takeProfitPrice: undefined,
      } as unknown as OrderRequest;
      const command = new PlaceOrderCommand('user-123', invalidOrder);

      await expect(handler.execute(command)).rejects.toThrow(BadRequestException);
      expect(tradingService.placeOrder).not.toHaveBeenCalled();
    });

    it('should handle service errors gracefully', async () => {
      mockTradingService.placeOrder.mockRejectedValue(new Error('Service error'));

      const command = new PlaceOrderCommand('user-123', validOrderRequest);
      await expect(handler.execute(command)).rejects.toThrow('Service error');
    });

    it('should log user action for audit', async () => {
      mockTradingService.placeOrder.mockResolvedValue(mockOrderResponse);

      const command = new PlaceOrderCommand('user-123', validOrderRequest);
      await handler.execute(command);

      expect(tradingService.placeOrder).toHaveBeenCalledWith(validOrderRequest);
    });
  });
});
