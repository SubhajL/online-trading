import { Test, TestingModule } from '@nestjs/testing';
import { getQueueToken } from '@nestjs/bull';
import { SignalsService } from './signals.service';
import { SnapshotsService } from '../snapshots/snapshots.service';
import { SignalPayloadDto, SignalSide } from '../alerts/dto/signal-payload.dto';

describe('SignalsService', () => {
  let service: SignalsService;
  let snapshotsService: jest.Mocked<SnapshotsService>;
  let mockQueue: { add: jest.Mock };

  beforeEach(async () => {
    mockQueue = { add: jest.fn().mockResolvedValue({ id: 'job-123' }) };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SignalsService,
        {
          provide: SnapshotsService,
          useValue: {
            getSnapshotBySignalId: jest.fn(),
          },
        },
        {
          provide: getQueueToken('snapshot'),
          useValue: mockQueue,
        },
      ],
    }).compile();

    service = module.get<SignalsService>(SignalsService);
    snapshotsService = module.get(SnapshotsService);
  });

  describe('getSnapshotUrl', () => {
    it('returns imageUrl when snapshot exists', async () => {
      const signalId = 'signal-123';
      const expectedUrl = '/snapshots/snapshot-uuid.png';

      snapshotsService.getSnapshotBySignalId.mockResolvedValue({
        id: 'snapshot-uuid',
        signalId,
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imagePath: '/var/app/snapshots/snapshot-uuid.png',
        imageUrl: expectedUrl,
        meta: {
          entry: 50000,
          stopLoss: 49000,
          takeProfit: 51000,
          signalTime: '2025-01-01T00:00:00Z',
          side: 'BUY' as const,
        },
        createdAt: new Date(),
      });

      const result = await service.getSnapshotUrl(signalId);

      expect(result).toBe(expectedUrl);
      expect(snapshotsService.getSnapshotBySignalId).toHaveBeenCalledWith(signalId);
    });

    it('returns null when snapshot does not exist', async () => {
      const signalId = 'non-existent';

      snapshotsService.getSnapshotBySignalId.mockResolvedValue(null);

      const result = await service.getSnapshotUrl(signalId);

      expect(result).toBeNull();
    });

    it('extracts imageUrl from snapshot dto', async () => {
      const signalId = 'test-signal';

      snapshotsService.getSnapshotBySignalId.mockResolvedValue({
        id: 'id-123',
        signalId,
        symbol: 'ETHUSDT',
        timeframe: '1h',
        imagePath: '/var/app/snapshots/id-123.png',
        imageUrl: '/snapshots/id-123.png',
        meta: {
          entry: 3000,
          stopLoss: 2900,
          takeProfit: 3100,
          signalTime: '2025-01-01T00:00:00Z',
          side: 'BUY' as const,
        },
        createdAt: new Date(),
      });

      const result = await service.getSnapshotUrl(signalId);

      expect(result).toBe('/snapshots/id-123.png');
    });
  });

  describe('createSignalAlert', () => {
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

    it('returns existing snapshot if already exists', async () => {
      snapshotsService.getSnapshotBySignalId.mockResolvedValue({
        id: 'existing-snapshot-id',
        signalId: 'sig_abc123',
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imagePath: '/var/app/snapshots/existing.png',
        imageUrl: '/snapshots/existing.png',
        meta: {
          entry: 50000,
          stopLoss: 49000,
          takeProfit: 52000,
          signalTime: '2025-01-01T00:00:00Z',
          side: 'BUY' as const,
        },
        createdAt: new Date(),
      });

      const result = await service.createSignalAlert(validPayload);

      expect(result.ok).toBe(true);
      expect(result.snapshot?.id).toBe('existing-snapshot-id');
      expect(result.snapshot?.imageUrl).toBe('/snapshots/existing.png');
      expect(mockQueue.add).not.toHaveBeenCalled();
    });

    it('queues snapshot generation for new signal', async () => {
      snapshotsService.getSnapshotBySignalId.mockResolvedValue(null);

      const result = await service.createSignalAlert(validPayload);

      expect(result.ok).toBe(true);
      expect(result.snapshot?.id).toBe('sig_abc123');
      expect(result.snapshot?.imageUrl).toBe('/api/snapshots/sig_abc123.png');
      expect(mockQueue.add).toHaveBeenCalledWith(
        'generate',
        validPayload,
        expect.objectContaining({ attempts: 3, jobId: 'sig_abc123' }),
      );
    });

    it('returns predicted imageUrl with /api prefix before generation completes', async () => {
      snapshotsService.getSnapshotBySignalId.mockResolvedValue(null);

      const result = await service.createSignalAlert(validPayload);

      expect(result.snapshot?.imageUrl).toBe(`/api/snapshots/${validPayload.signalId}.png`);
    });
  });
});
