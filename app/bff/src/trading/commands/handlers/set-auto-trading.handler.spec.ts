import { Test, TestingModule } from '@nestjs/testing';
import { SetAutoTradingHandler } from './set-auto-trading.handler';
import { SetAutoTradingCommand } from '../set-auto-trading.command';
import { TradingService } from '../../trading.service';

describe('SetAutoTradingHandler', () => {
  let handler: SetAutoTradingHandler;
  let tradingService: TradingService;

  const mockTradingService = {
    setAutoTrading: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SetAutoTradingHandler,
        {
          provide: TradingService,
          useValue: mockTradingService,
        },
      ],
    }).compile();

    handler = module.get<SetAutoTradingHandler>(SetAutoTradingHandler);
    tradingService = module.get<TradingService>(TradingService);
    jest.clearAllMocks();
  });

  describe('execute', () => {
    it('should enable auto-trading successfully', async () => {
      mockTradingService.setAutoTrading.mockResolvedValue(undefined);

      const command = new SetAutoTradingCommand('user-123', true);
      await handler.execute(command);

      expect(tradingService.setAutoTrading).toHaveBeenCalledWith(true);
    });

    it('should disable auto-trading successfully', async () => {
      mockTradingService.setAutoTrading.mockResolvedValue(undefined);

      const command = new SetAutoTradingCommand('user-123', false);
      await handler.execute(command);

      expect(tradingService.setAutoTrading).toHaveBeenCalledWith(false);
    });

    it('should handle errors when setting auto-trading', async () => {
      mockTradingService.setAutoTrading.mockRejectedValue(new Error('Service error'));

      const command = new SetAutoTradingCommand('user-123', true);
      await expect(handler.execute(command)).rejects.toThrow('Service error');
    });
  });
});
