import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { SnapshotsService } from './snapshots.service';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { v4 as uuidv4 } from 'uuid';
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
    it('writes PNG to disk with UUID name', async () => {
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
        Promise.resolve({ ...entity, id: uuidv4(), createdAt: new Date() } as AlertSnapshot),
      );
      (fs.mkdir as jest.Mock).mockResolvedValue(undefined);
      (fs.writeFile as jest.Mock).mockResolvedValue(undefined);

      const result = await service.saveSnapshot(signalId, imageBuffer, metadata);

      expect(fs.writeFile).toHaveBeenCalledWith(
        expect.stringMatching(/\/var\/app\/snapshots\/.*\.png$/),
        imageBuffer,
      );
      expect(result.imagePath).toMatch(/\/var\/app\/snapshots\/.*\.png$/);
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
          id: uuidv4(),
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

    it('returns snapshot with imageUrl', async () => {
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
      expect(result?.imageUrl).toBe('/snapshots/test-id.png');
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
