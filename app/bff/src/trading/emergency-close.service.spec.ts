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
    haltExecution: jest.fn(),
    getExecutionControl: jest.fn(),
    emergencyFlatten: jest.fn(),
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
    mockRouterClient.haltExecution.mockResolvedValue({
      state: 'HALTED',
      generation: 2,
    });
    mockRouterClient.getExecutionControl.mockResolvedValue({
      state: 'HALTED',
      generation: 2,
    });
    mockRouterClient.emergencyFlatten.mockResolvedValue({
      starting: { open_orders: [{ order_id: 1 }], futures_positions: [], spot_balances: [] },
      final: { open_orders: [], futures_positions: [], spot_balances: [] },
      canceled_orders: 2,
      closed_futures_positions: 1,
      flattened_spot_assets: 0,
      residuals: [],
      fully_flattened: true,
      passes: 1,
    });
    mockTradingService.setAutoTrading.mockResolvedValue(undefined);
    mockRepository.save.mockImplementation(async (op: any) => op);

    const result = await service.execute({ scope: 'ALL', stopEngine: true }, 'idem-1');

    expect(result.idempotencyKey).toBe('idem-1');
    expect(result.scope).toBe('ALL');
    expect(result.stopEngine).toBe(true);
    expect(result.canceledOrders).toBe(2);
    expect(result.closedPositions).toBe(1);
    expect(result.autoTradingDisabled).toBe(true);
    expect(result.executionHalted).toBe(true);
    expect(result.controlGeneration).toBe(2);
    expect(result.steps.map((s) => s.name)).toEqual([
      'HALT_EXECUTION',
      'EXCHANGE_FLATTEN',
      'STOP_AUTO_TRADING',
    ]);
    expect(mockRepository.save).toHaveBeenCalledTimes(1);
    expect(mockRouterClient.haltExecution).toHaveBeenCalledWith({
      reason: 'emergency-close:ALL',
      requested_by: 'bff-emergency-close',
      idempotency_key: 'idem-1:halt',
    });
    expect(mockRouterClient.haltExecution.mock.invocationCallOrder[0]).toBeLessThan(
      mockRouterClient.emergencyFlatten.mock.invocationCallOrder[0],
    );
  });

  it('does not cancel or close when the durable halt cannot be confirmed', async () => {
    mockRepository.findByIdempotencyKey.mockResolvedValue(null);
    mockRouterClient.haltExecution.mockResolvedValue({ state: 'HALTED', generation: 3 });
    mockRouterClient.getExecutionControl.mockResolvedValue({ state: 'RUNNING', generation: 2 });
    mockRepository.save.mockImplementation(async (op: any) => op);

    const result = await service.execute({ scope: 'ALL', stopEngine: true }, 'idem-halt-fails');

    expect(result.success).toBe(false);
    expect(result.executionHalted).toBe(false);
    expect(result.steps).toHaveLength(1);
    expect(result.steps[0].name).toBe('HALT_EXECUTION');
    expect(mockRouterClient.emergencyFlatten).not.toHaveBeenCalled();
    expect(mockTradingService.setAutoTrading).not.toHaveBeenCalled();
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
    mockRouterClient.haltExecution.mockResolvedValue({ state: 'HALTED', generation: 2 });
    mockRouterClient.getExecutionControl.mockResolvedValue({ state: 'HALTED', generation: 2 });
    mockRouterClient.emergencyFlatten.mockResolvedValue({
      starting: { open_orders: [], futures_positions: [], spot_balances: [] },
      final: {
        open_orders: [],
        futures_positions: [],
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
      canceled_orders: 0,
      closed_futures_positions: 0,
      flattened_spot_assets: 0,
      residuals: [
        {
          asset: 'BTC',
          symbol: 'BTCUSDT',
          quantity: '0.01',
          notional_usdt: '500',
          dust: false,
        },
      ],
      fully_flattened: false,
      passes: 3,
      errors: ['spot flatten failed'],
    });
    mockRepository.save.mockImplementation(async (op: any) => op);

    const result = await service.execute({ scope: 'ALL', stopEngine: false }, 'idem-4');

    expect(result.success).toBe(false);
    expect(result.fullyFlattened).toBe(false);
    expect(result.executionHalted).toBe(true);
    expect(result.residuals).toHaveLength(1);
    expect(result.steps.find((s) => s.name === 'EXCHANGE_FLATTEN')?.errors).toEqual([
      'spot flatten failed',
    ]);
  });
});
