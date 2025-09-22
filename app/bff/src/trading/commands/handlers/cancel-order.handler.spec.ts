import { Test, TestingModule } from '@nestjs/testing';
import { CancelOrderHandler } from './cancel-order.handler';
import { CancelOrderCommand } from '../cancel-order.command';
import { TradingService } from '../../trading.service';
import type { OrderResponse } from '../../../router-client/router-client.service';

describe('CancelOrderHandler', () => {
  let handler: CancelOrderHandler;
  let tradingService: TradingService;

  const mockTradingService = {
    cancelOrder: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        CancelOrderHandler,
        {
          provide: TradingService,
          useValue: mockTradingService,
        },
      ],
    }).compile();

    handler = module.get<CancelOrderHandler>(CancelOrderHandler);
    tradingService = module.get<TradingService>(TradingService);
    jest.clearAllMocks();
  });

  const mockCanceledOrder: OrderResponse = {
    orderId: 'order-123',
    symbol: 'BTCUSDT',
    side: 'BUY',
    type: 'MARKET',
    status: 'CANCELED',
    quantity: 0.001,
  };

  describe('execute', () => {
    it('should cancel order successfully', async () => {
      mockTradingService.cancelOrder.mockResolvedValue(mockCanceledOrder);

      const command = new CancelOrderCommand('user-123', 'order-123', 'BTCUSDT', 'SPOT');
      const result = await handler.execute(command);

      expect(result).toEqual(mockCanceledOrder);
      expect(tradingService.cancelOrder).toHaveBeenCalledWith('order-123', 'BTCUSDT', 'SPOT');
    });

    it('should handle cancellation errors', async () => {
      mockTradingService.cancelOrder.mockRejectedValue(new Error('Order not found'));

      const command = new CancelOrderCommand('user-123', 'order-123', 'BTCUSDT', 'SPOT');
      await expect(handler.execute(command)).rejects.toThrow('Order not found');
    });

    it('should work for USD_M futures orders', async () => {
      mockTradingService.cancelOrder.mockResolvedValue(mockCanceledOrder);

      const command = new CancelOrderCommand('user-123', 'order-123', 'BTCUSDT', 'USD_M');
      const result = await handler.execute(command);

      expect(result).toEqual(mockCanceledOrder);
      expect(tradingService.cancelOrder).toHaveBeenCalledWith('order-123', 'BTCUSDT', 'USD_M');
    });
  });
});
