import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { SnapshotsService } from './snapshots.service';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import * as fs from 'fs/promises';

jest.mock('fs/promises');

describe('SnapshotsService', () => {
  let service: SnapshotsService;
  let repository: jest.Mocked<Repository<AlertSnapshot>>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        SnapshotsService,
        {
          provide: getRepositoryToken(AlertSnapshot),
          useValue: {
            create: jest.fn((entity) => entity),
            findOne: jest.fn(),
            save: jest.fn(),
            delete: jest.fn(),
            find: jest.fn(),
            createQueryBuilder: jest.fn(() => ({
              where: jest.fn().mockReturnThis(),
              getMany: jest.fn(),
              delete: jest.fn().mockReturnThis(),
              execute: jest.fn(),
            })),
          },
        },
      ],
    }).compile();

    service = module.get<SnapshotsService>(SnapshotsService);
    repository = module.get(getRepositoryToken(AlertSnapshot));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('saveSnapshot', () => {
    it('writes PNG to disk with signalId-based filename', async () => {
      const signalId = 'signal-123';
      const imageBuffer = Buffer.from('fake-png-data');
      const metadata = {
        symbol: 'BTCUSDT',
        timeframe: '15m',
        entry: 52000,
        stopLoss: 51000,
        takeProfit: 53000,
        signalTime: '2025-01-26T10:00:00Z',
        side: 'BUY' as const,
        reasons: ['SMC Breaker', 'BOS'],
      };

      repository.findOne.mockResolvedValue(null);
      repository.save.mockImplementation((entity) =>
        Promise.resolve({
          ...entity,
          id: 'generated-id-123',
          createdAt: new Date(),
        } as AlertSnapshot),
      );
      (fs.mkdir as jest.Mock).mockResolvedValue(undefined);
      (fs.writeFile as jest.Mock).mockResolvedValue(undefined);

      const result = await service.saveSnapshot(signalId, imageBuffer, metadata);

      expect(fs.writeFile).toHaveBeenCalledWith('/var/app/snapshots/signal-123.png', imageBuffer);
      expect(result.imagePath).toBe('/var/app/snapshots/signal-123.png');
    });

    it('creates database record with metadata', async () => {
      const signalId = 'signal-456';
      const imageBuffer = Buffer.from('fake-png-data');
      const metadata = {
        symbol: 'ETHUSDT',
        timeframe: '1h',
        entry: 3200,
        stopLoss: 3100,
        takeProfit: 3300,
        signalTime: '2025-01-26T11:00:00Z',
        side: 'SELL' as const,
      };

      repository.findOne.mockResolvedValue(null);
      repository.save.mockImplementation((entity) =>
        Promise.resolve({
          ...entity,
          id: 'generated-id-456',
          createdAt: new Date(),
        } as AlertSnapshot),
      );
      (fs.mkdir as jest.Mock).mockResolvedValue(undefined);
      (fs.writeFile as jest.Mock).mockResolvedValue(undefined);

      const result = await service.saveSnapshot(signalId, imageBuffer, metadata);

      expect(repository.save).toHaveBeenCalledWith(
        expect.objectContaining({
          signalId,
          symbol: metadata.symbol,
          timeframe: metadata.timeframe,
          meta: metadata,
        }),
      );
      expect(result.meta).toEqual(metadata);
    });

    it('sanitizes signalId to prevent path traversal', async () => {
      const signalId = '../../../etc/passwd';
      const imageBuffer = Buffer.from('fake-png-data');
      const metadata = { symbol: 'BTCUSDT', timeframe: '15m' };

      repository.findOne.mockResolvedValue(null);
      repository.save.mockImplementation((entity) =>
        Promise.resolve({
          ...entity,
          id: 'generated-id-789',
          createdAt: new Date(),
        } as AlertSnapshot),
      );
      (fs.mkdir as jest.Mock).mockResolvedValue(undefined);
      (fs.writeFile as jest.Mock).mockResolvedValue(undefined);

      await service.saveSnapshot(signalId, imageBuffer, metadata);

      // Dangerous characters (including dots and slashes) should be replaced with underscores
      expect(fs.writeFile).toHaveBeenCalledWith(
        '/var/app/snapshots/_________etc_passwd.png',
        imageBuffer,
      );
    });

    it('is idempotent for same signalId', async () => {
      const signalId = 'signal-789';
      const imageBuffer = Buffer.from('fake-png-data');
      const metadata = { symbol: 'BTCUSDT', timeframe: '15m' };

      const existingSnapshot = {
        id: 'existing-id',
        signalId,
        imagePath: '/var/app/snapshots/existing.png',
        meta: metadata,
        createdAt: new Date(),
      } as AlertSnapshot;

      repository.findOne.mockResolvedValue(existingSnapshot);

      const result1 = await service.saveSnapshot(signalId, imageBuffer, metadata);
      const result2 = await service.saveSnapshot(signalId, imageBuffer, metadata);

      expect(result1.id).toBe(result2.id);
      expect(fs.writeFile).not.toHaveBeenCalled();
    });
  });

  describe('getSnapshot', () => {
    it('returns null for non-existent ID', async () => {
      repository.findOne.mockResolvedValue(null);

      const result = await service.getSnapshot('non-existent');

      expect(result).toBeNull();
    });

    it('returns snapshot with imageUrl using signalId', async () => {
      const snapshot = {
        id: 'test-id',
        signalId: 'signal-123',
        imagePath: '/var/app/snapshots/test.png',
        meta: { symbol: 'BTCUSDT' },
        createdAt: new Date(),
      } as AlertSnapshot;

      repository.findOne.mockResolvedValue(snapshot);

      const result = await service.getSnapshot('test-id');

      expect(result).not.toBeNull();
      expect(result?.imageUrl).toBe('/api/snapshots/signal-123.png');
    });
  });

  describe('getSnapshotBySignalId', () => {
    it('returns null for non-existent signalId', async () => {
      repository.findOne.mockResolvedValue(null);

      const result = await service.getSnapshotBySignalId('non-existent-signal');

      expect(result).toBeNull();
      expect(repository.findOne).toHaveBeenCalledWith({
        where: { signalId: 'non-existent-signal' },
      });
    });

    it('returns snapshot with imageUrl using signalId', async () => {
      const snapshot = {
        id: 'snapshot-uuid',
        signalId: 'signal-abc',
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imagePath: '/var/app/snapshots/snapshot-uuid.png',
        meta: { entry: 50000 },
        createdAt: new Date(),
      } as AlertSnapshot;

      repository.findOne.mockResolvedValue(snapshot);

      const result = await service.getSnapshotBySignalId('signal-abc');

      expect(result).not.toBeNull();
      expect(result?.signalId).toBe('signal-abc');
      expect(result?.imageUrl).toBe('/api/snapshots/signal-abc.png');
    });

    it('queries by signalId field not id field', async () => {
      repository.findOne.mockResolvedValue(null);

      await service.getSnapshotBySignalId('my-signal-id');

      expect(repository.findOne).toHaveBeenCalledWith({
        where: { signalId: 'my-signal-id' },
      });
    });
  });

  describe('deleteOldSnapshots', () => {
    it('removes files older than 30 days', async () => {
      const oldSnapshots = [
        { id: 'old-1', imagePath: '/var/app/snapshots/old-1.png' } as AlertSnapshot,
        { id: 'old-2', imagePath: '/var/app/snapshots/old-2.png' } as AlertSnapshot,
      ];

      const queryBuilder = {
        where: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(oldSnapshots),
        delete: jest.fn().mockReturnThis(),
        execute: jest.fn().mockResolvedValue({ affected: 2 }),
      };
      repository.createQueryBuilder.mockReturnValue(queryBuilder as any);

      (fs.unlink as jest.Mock).mockResolvedValue(undefined);

      const count = await service.deleteOldSnapshots(30);

      expect(count).toBe(2);
      expect(fs.unlink).toHaveBeenCalledTimes(2);
      expect(fs.unlink).toHaveBeenCalledWith('/var/app/snapshots/old-1.png');
      expect(fs.unlink).toHaveBeenCalledWith('/var/app/snapshots/old-2.png');
    });

    it('continues on file deletion errors', async () => {
      const oldSnapshots = [
        { id: 'old-1', imagePath: '/var/app/snapshots/old-1.png' } as AlertSnapshot,
        { id: 'old-2', imagePath: '/var/app/snapshots/old-2.png' } as AlertSnapshot,
      ];

      const queryBuilder = {
        where: jest.fn().mockReturnThis(),
        getMany: jest.fn().mockResolvedValue(oldSnapshots),
        delete: jest.fn().mockReturnThis(),
        execute: jest.fn().mockResolvedValue({ affected: 2 }),
      };
      repository.createQueryBuilder.mockReturnValue(queryBuilder as any);

      (fs.unlink as jest.Mock)
        .mockRejectedValueOnce(new Error('File not found'))
        .mockResolvedValueOnce(undefined);

      const count = await service.deleteOldSnapshots(30);

      expect(count).toBe(2); // DB records still deleted
      expect(fs.unlink).toHaveBeenCalledTimes(2);
    });
  });
});
