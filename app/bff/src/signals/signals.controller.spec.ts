import { Test, TestingModule } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { SignalsController } from './signals.controller';
import { SignalsService } from './signals.service';
import { InternalApiGuard } from '../auth/guards/internal-api.guard';
import { SignalPayloadDto, SignalSide } from '../alerts/dto/signal-payload.dto';

describe('SignalsController', () => {
  let controller: SignalsController;
  let signalsService: jest.Mocked<SignalsService>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [SignalsController],
      providers: [
        {
          provide: SignalsService,
          useValue: {
            getSnapshotUrl: jest.fn(),
            createSignalAlert: jest.fn(),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn().mockReturnValue('test-token'),
          },
        },
        InternalApiGuard,
      ],
    }).compile();

    controller = module.get<SignalsController>(SignalsController);
    signalsService = module.get(SignalsService);
  });

  describe('GET /signals/:signalId/snapshot', () => {
    it('returns imageUrl for existing signalId', async () => {
      const signalId = 'signal-abc';
      const expectedUrl = '/snapshots/snapshot-uuid.png';

      signalsService.getSnapshotUrl.mockResolvedValue(expectedUrl);

      const result = await controller.getSnapshot(signalId);

      expect(result).toEqual({ imageUrl: expectedUrl });
      expect(signalsService.getSnapshotUrl).toHaveBeenCalledWith(signalId);
    });

    it('throws NotFoundException for non-existent signalId', async () => {
      const signalId = 'non-existent';

      signalsService.getSnapshotUrl.mockResolvedValue(null);

      await expect(controller.getSnapshot(signalId)).rejects.toThrow(NotFoundException);
    });

    it('returns correct imageUrl format', async () => {
      const signalId = 'test-signal';
      const snapshotId = 'uuid-123';
      const expectedUrl = `/snapshots/${snapshotId}.png`;

      signalsService.getSnapshotUrl.mockResolvedValue(expectedUrl);

      const result = await controller.getSnapshot(signalId);

      expect(result.imageUrl).toMatch(/^\/snapshots\/.*\.png$/);
    });
  });

  describe('POST /signals/alert', () => {
    const validPayload: SignalPayloadDto = {
      signalId: 'sig_abc123',
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      side: SignalSide.BUY,
      entry: 50000,
      stopLoss: 49000,
      takeProfit: 52000,
      confidence: 0.85,
      reasons: ['SMC Breaker', 'Bullish OB'],
      timeframe: '15m',
      signalTime: '2025-01-01T00:00:00Z',
    };

    it('creates signal alert and returns ok with snapshot', async () => {
      const expectedResponse = {
        ok: true,
        snapshot: {
          id: 'sig_abc123',
          imageUrl: '/snapshots/sig_abc123.png',
        },
      };

      signalsService.createSignalAlert.mockResolvedValue(expectedResponse);

      const result = await controller.createSignalAlert(validPayload);

      expect(result).toEqual(expectedResponse);
      expect(signalsService.createSignalAlert).toHaveBeenCalledWith(validPayload);
    });

    it('is idempotent - returns existing snapshot on duplicate', async () => {
      const existingResponse = {
        ok: true,
        snapshot: {
          id: 'existing-id',
          imageUrl: '/snapshots/existing-id.png',
        },
      };

      signalsService.createSignalAlert.mockResolvedValue(existingResponse);

      const result = await controller.createSignalAlert(validPayload);

      expect(result.ok).toBe(true);
      expect(result.snapshot).toBeDefined();
    });
  });
});
