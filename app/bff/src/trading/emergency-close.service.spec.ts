import { Test } from '@nestjs/testing';
import { ConflictException } from '@nestjs/common';
import { EmergencyCloseService } from './emergency-close.service';
import { TradingService } from './trading.service';
import { RouterClientService } from '../router-client/router-client.service';
import { EmergencyCloseOperationRepository } from './repositories/emergency-close-operation.repository';

describe('EmergencyCloseService', () => {
  const mockTradingService = {
    getPositions: jest.fn(),
    setAutoTrading: jest.fn(),
  };

  const mockRouterClient = {
    cancelOpenOrders: jest.fn(),
    closePositions: jest.fn(),
  };

  const mockRepository = {
    findByIdempotencyKey: jest.fn(),
    save: jest.fn(),
  };

  let service: EmergencyCloseService;

  beforeEach(async () => {
    jest.clearAllMocks();

    const module = await Test.createTestingModule({
      providers: [
        EmergencyCloseService,
        { provide: TradingService, useValue: mockTradingService },
        { provide: RouterClientService, useValue: mockRouterClient },
        { provide: EmergencyCloseOperationRepository, useValue: mockRepository },
      ],
    }).compile();

    service = module.get(EmergencyCloseService);
  });

  it('executes cancel→close→stopAutoTrading steps and persists response', async () => {
    mockRepository.findByIdempotencyKey.mockResolvedValue(null);
    mockTradingService.getPositions.mockResolvedValue([{ symbol: 'BTCUSDT' }]);
    mockRouterClient.cancelOpenOrders.mockResolvedValue({ canceled_orders: 2 });
    mockRouterClient.closePositions.mockResolvedValue({ closed_positions: 1 });
    mockTradingService.setAutoTrading.mockResolvedValue(undefined);
    mockRepository.save.mockImplementation(async (op: any) => op);

    const result = await service.execute({ scope: 'ALL', stopEngine: true }, 'idem-1');

    expect(result.idempotencyKey).toBe('idem-1');
    expect(result.scope).toBe('ALL');
    expect(result.stopEngine).toBe(true);
    expect(result.canceledOrders).toBe(2);
    expect(result.closedPositions).toBe(1);
    expect(result.autoTradingDisabled).toBe(true);
    expect(result.steps.map((s) => s.name)).toEqual([
      'CANCEL_OPEN_ORDERS',
      'CLOSE_POSITIONS',
      'STOP_AUTO_TRADING',
    ]);
    expect(mockRepository.save).toHaveBeenCalledTimes(1);
  });

  it('returns stored response when idempotency key is reused with same request', async () => {
    const stored = {
      idempotencyKey: 'idem-2',
      requestSignature: 'ALL:0',
      response: {
        success: true,
        scope: 'ALL',
        stopEngine: false,
        idempotencyKey: 'idem-2',
        canceledOrders: 0,
        closedPositions: 0,
        autoTradingDisabled: false,
        steps: [],
        executionTimeMs: 1,
      },
    };
    mockRepository.findByIdempotencyKey.mockResolvedValue(stored);

    const result = await service.execute({ scope: 'ALL', stopEngine: false }, 'idem-2');

    expect(result).toEqual(stored.response);
    expect(mockRouterClient.cancelOpenOrders).not.toHaveBeenCalled();
    expect(mockRepository.save).not.toHaveBeenCalled();
  });

  it('throws conflict when idempotency key is reused with different request', async () => {
    mockRepository.findByIdempotencyKey.mockResolvedValue({
      idempotencyKey: 'idem-3',
      requestSignature: 'ALL:0',
      response: {},
    });

    await expect(
      service.execute({ scope: 'ALL', stopEngine: true }, 'idem-3'),
    ).rejects.toBeInstanceOf(ConflictException);
  });

  it('marks response unsuccessful when router returns step errors', async () => {
    mockRepository.findByIdempotencyKey.mockResolvedValue(null);
    mockTradingService.getPositions.mockResolvedValue([{ symbol: 'BTCUSDT' }]);
    mockRouterClient.cancelOpenOrders.mockResolvedValue({
      canceled_orders: 0,
      errors: ['cancel failed'],
    });
    mockRouterClient.closePositions.mockResolvedValue({
      closed_positions: 0,
      errors: ['close failed'],
    });
    mockRepository.save.mockImplementation(async (op: any) => op);

    const result = await service.execute({ scope: 'ALL', stopEngine: false }, 'idem-4');

    expect(result.success).toBe(false);
    expect(result.steps.find((s) => s.name === 'CANCEL_OPEN_ORDERS')?.errors).toEqual([
      'cancel failed',
    ]);
    expect(result.steps.find((s) => s.name === 'CLOSE_POSITIONS')?.errors).toEqual([
      'close failed',
    ]);
  });
});
