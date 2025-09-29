import { describe, it, expect, jest, beforeEach, afterEach } from '@jest/globals';
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { getQueueToken } from '@nestjs/bull';
import request from 'supertest';
import * as fs from 'fs/promises';
import { v4 as uuidv4 } from 'uuid';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Repository } from 'typeorm';

import { SignalsController } from '../signals/signals.controller';
import { SignalsService } from '../signals/signals.service';
import { SnapshotsService } from './snapshots.service';
import { SnapshotGeneratorService } from './snapshot-generator.service';
import { AlertsService } from '../alerts/alerts.service';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { Alert } from '../alerts/entities/alert.entity';
import { ConfigService } from '@nestjs/config';
import { AuthGuard } from '@nestjs/passport';

// Mock the auth guard
const mockAuthGuard = {
  canActivate: jest.fn(() => true),
};

jest.mock('fs/promises');

describe('Snapshots Integration', () => {
  let app: INestApplication;
  let moduleRef: TestingModule;
  let signalsService: SignalsService;
  let snapshotsService: SnapshotsService;
  let alertsService: AlertsService;
  let snapshotGenerator: SnapshotGeneratorService;

  const mockSnapshotRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
    find: jest.fn(),
  };

  const mockAlertRepository = {
    create: jest.fn(),
    save: jest.fn(),
    find: jest.fn(),
    findOne: jest.fn(),
  };

  const mockQueue = {
    add: jest.fn(),
    process: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    // Create test module with mocked dependencies
    moduleRef = await Test.createTestingModule({
      controllers: [SignalsController],
      providers: [
        SignalsService,
        SnapshotsService,
        AlertsService,
        SnapshotGeneratorService,
        {
          provide: getRepositoryToken(AlertSnapshot),
          useValue: mockSnapshotRepository,
        },
        {
          provide: getRepositoryToken(Alert),
          useValue: mockAlertRepository,
        },
        {
          provide: getQueueToken('signal-alerts'),
          useValue: mockQueue,
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config: Record<string, any> = {
                NODE_ENV: 'test',
                UPLOADS_DIR: '/test-uploads',
                INTERNAL_API_KEY: 'test-key-123',
              };
              return config[key];
            }),
          },
        },
      ],
    })
      .overrideGuard(AuthGuard('api-key'))
      .useValue(mockAuthGuard)
      .compile();

    app = moduleRef.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
        forbidNonWhitelisted: true,
      }),
    );
    await app.init();

    signalsService = moduleRef.get<SignalsService>(SignalsService);
    snapshotsService = moduleRef.get<SnapshotsService>(SnapshotsService);
    alertsService = moduleRef.get<AlertsService>(AlertsService);
    snapshotGenerator = moduleRef.get<SnapshotGeneratorService>(SnapshotGeneratorService);
  });

  afterEach(async () => {
    await app?.close();
  });

  describe('POST /api/signals/alert', () => {
    it('should create snapshot and alert for valid signal', async () => {
      const signalId = `sig_${uuidv4().substring(0, 12)}`;
      const payload = {
        signalId,
        symbol: 'BTCUSDT',
        venue: 'SPOT',
        side: 'BUY',
        entry: 50000,
        stopLoss: 49000,
        takeProfit: 52000,
        confidence: 0.85,
        reasons: ['SMC Break', 'Trend Alignment'],
        timeframe: '15m',
        signalTime: new Date().toISOString(),
      };

      // Mock queue processing
      mockQueue.add.mockResolvedValue({ id: 'job-123' });

      // Mock alert creation
      mockAlertRepository.create.mockReturnValue({
        id: 'alert-123',
        type: 'smc',
        priority: 'high',
        title: `Signal: ${payload.side} ${payload.symbol}`,
        message: `Trading signal for ${payload.symbol}`,
        data: payload,
        read: false,
      });
      mockAlertRepository.save.mockResolvedValue({
        id: 'alert-123',
        type: 'smc',
        priority: 'high',
        title: `Signal: ${payload.side} ${payload.symbol}`,
        message: `Trading signal for ${payload.symbol}`,
        data: payload,
        read: false,
      });
      mockAlertRepository.find.mockResolvedValue([
        {
          id: 'alert-123',
          type: 'smc',
          priority: 'high',
          title: `Signal: ${payload.side} ${payload.symbol}`,
          message: `Trading signal for ${payload.symbol}`,
          data: payload,
          read: false,
        },
      ]);

      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      expect(response.body).toMatchObject({
        success: true,
        signalId,
        message: 'Signal alert queued for processing',
      });

      // Verify queue was called
      expect(mockQueue.add).toHaveBeenCalledWith(
        'process-signal',
        expect.objectContaining({
          signalId,
          symbol: 'BTCUSDT',
        }),
      );
    });

    it('should reject unauthorized requests', async () => {
      mockAuthGuard.canActivate.mockReturnValueOnce(false);

      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .send({
          signalId: 'test-123',
          symbol: 'BTCUSDT',
          side: 'BUY',
        })
        .expect(403);
    });

    it('should validate request payload', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send({
          // Missing required fields
          symbol: 'BTCUSDT',
        })
        .expect(400);

      expect(response.body.message).toBeDefined();
    });

    it('should be idempotent for same signalId', async () => {
      const signalId = `sig_${uuidv4().substring(0, 12)}`;
      const payload = {
        signalId,
        symbol: 'BTCUSDT',
        venue: 'SPOT',
        side: 'BUY',
        entry: 50000,
        stopLoss: 49000,
        takeProfit: 52000,
        confidence: 0.85,
        reasons: ['Test'],
        timeframe: '15m',
        signalTime: new Date().toISOString(),
      };

      // Mock queue add for first request
      mockQueue.add.mockResolvedValue({ id: 'job-123' });

      // First request
      await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      // Mock existing alert for second request
      mockAlertRepository.findOne.mockResolvedValue({
        id: 'existing-alert',
        data: { signalId },
      });

      // Second request with same signalId
      await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      // Queue should only be called once due to idempotency
      expect(mockQueue.add).toHaveBeenCalledTimes(1);
    });
  });

  describe('GET /api/signals/:signalId/snapshot', () => {
    it('should return snapshot details', async () => {
      const signalId = `sig_${uuidv4().substring(0, 12)}`;

      // Mock snapshot
      mockSnapshotRepository.findOne.mockResolvedValue({
        id: 'snapshot-123',
        signalId,
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imagePath: `snapshots/${signalId}.png`,
        meta: {
          side: 'BUY',
          entry: 50000,
          reasons: ['Test'],
        },
      });

      const response = await request(app.getHttpServer())
        .get(`/api/signals/${signalId}/snapshot`)
        .set('Authorization', 'Bearer test-key-123')
        .expect(200);

      expect(response.body).toMatchObject({
        id: 'snapshot-123',
        signalId,
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imageUrl: expect.stringContaining(`/uploads/snapshots/${signalId}.png`),
      });
    });

    it('should return 404 for non-existent signal', async () => {
      mockSnapshotRepository.findOne.mockResolvedValue(null);

      await request(app.getHttpServer())
        .get('/api/signals/nonexistent/snapshot')
        .set('Authorization', 'Bearer test-key-123')
        .expect(404);
    });
  });

  describe('Snapshot Generation', () => {
    it('should handle snapshot generation errors gracefully', async () => {
      // Mock the snapshot generator to fail
      jest
        .spyOn(snapshotGenerator, 'generateSnapshot')
        .mockRejectedValue(new Error('Puppeteer error'));

      const signalId = `sig_${uuidv4().substring(0, 12)}`;
      const payload = {
        signalId,
        symbol: 'BTCUSDT',
        venue: 'SPOT',
        side: 'BUY',
        entry: 50000,
        stopLoss: 49000,
        takeProfit: 52000,
        confidence: 0.85,
        reasons: ['Test'],
        timeframe: '15m',
        signalTime: new Date().toISOString(),
      };

      mockQueue.add.mockResolvedValue({ id: 'job-123' });

      // Should still return success (snapshot is best-effort)
      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      expect(response.body.success).toBe(true);
    });
  });
});
