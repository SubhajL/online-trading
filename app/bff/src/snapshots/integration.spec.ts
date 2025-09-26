import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Test, TestingModule } from '@nestjs/testing';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BullModule } from '@nestjs/bull';
import { ConfigModule } from '@nestjs/config';
import * as request from 'supertest';
import * as fs from 'fs/promises';
import * as path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { INestApplication } from '@nestjs/common';
import { Repository } from 'typeorm';

import { SnapshotsModule } from './snapshots.module';
import { AlertsModule } from '../alerts/alerts.module';
import { AlertSnapshot } from './entities/alert-snapshot.entity';
import { Alert } from '../alerts/entities/alert.entity';

describe('Snapshots Integration', () => {
  let app: INestApplication;
  let moduleRef: TestingModule;
  let snapshotRepo: Repository<AlertSnapshot>;
  let alertRepo: Repository<Alert>;

  const testDbPath = path.join(process.cwd(), 'test-snapshots.db');
  const uploadsDir = path.join(process.cwd(), 'test-uploads');

  beforeEach(async () => {
    // Clean up test directories
    await fs.rm(testDbPath, { force: true }).catch(() => {});
    await fs.rm(uploadsDir, { force: true, recursive: true }).catch(() => {});
    await fs.mkdir(uploadsDir, { recursive: true });

    // Create test module
    moduleRef = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          isGlobal: true,
          load: [
            () => ({
              NODE_ENV: 'test',
              UPLOADS_DIR: uploadsDir,
              DATABASE_URL: `sqlite:///${testDbPath}`,
              INTERNAL_API_KEY: 'test-key-123',
              REDIS_HOST: 'localhost',
              REDIS_PORT: 6379,
            }),
          ],
        }),
        TypeOrmModule.forRoot({
          type: 'sqlite',
          database: testDbPath,
          autoLoadEntities: true,
          synchronize: true,
          logging: false,
        }),
        BullModule.forRoot({
          redis: {
            host: 'localhost',
            port: 6379,
          },
        }),
        SnapshotsModule,
        AlertsModule,
      ],
    }).compile();

    app = moduleRef.createNestApplication();
    await app.init();

    snapshotRepo = moduleRef.get<Repository<AlertSnapshot>>('AlertSnapshotRepository');
    alertRepo = moduleRef.get<Repository<Alert>>('AlertRepository');
  });

  afterEach(async () => {
    await app?.close();
    await fs.rm(testDbPath, { force: true }).catch(() => {});
    await fs.rm(uploadsDir, { force: true, recursive: true }).catch(() => {});
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

      // Wait a bit for async processing
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Check database for alert
      const alerts = await alertRepo.find();
      expect(alerts).toHaveLength(1);
      expect(alerts[0]).toMatchObject({
        symbol: 'BTCUSDT',
        venue: 'SPOT',
        type: 'trading_signal',
        severity: 'high',
        signalId,
      });
    });

    it('should reject unauthorized requests', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .send({
          signalId: 'test-123',
          symbol: 'BTCUSDT',
          side: 'BUY',
        })
        .expect(401);

      expect(response.body).toMatchObject({
        statusCode: 401,
        message: 'Unauthorized',
      });
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

      expect(response.body.message).toContain('Bad Request');
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

      // First request
      await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      // Second request with same signalId
      await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      // Wait for processing
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Should only have one alert
      const alerts = await alertRepo.find();
      expect(alerts).toHaveLength(1);
    });
  });

  describe('GET /api/signals/:signalId/snapshot', () => {
    it('should return snapshot details', async () => {
      const signalId = `sig_${uuidv4().substring(0, 12)}`;

      // Create a snapshot directly
      const snapshot = await snapshotRepo.save({
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
        id: snapshot.id,
        signalId,
        symbol: 'BTCUSDT',
        timeframe: '15m',
        imageUrl: expect.stringContaining(`/uploads/snapshots/${signalId}.png`),
      });
    });

    it('should return 404 for non-existent signal', async () => {
      await request(app.getHttpServer())
        .get('/api/signals/nonexistent/snapshot')
        .set('Authorization', 'Bearer test-key-123')
        .expect(404);
    });
  });

  describe('Snapshot Generation', () => {
    it('should handle snapshot generation errors gracefully', async () => {
      // Mock the snapshot generator to fail
      const snapshotGenerator = moduleRef.get('SnapshotGeneratorService');
      vi.spyOn(snapshotGenerator, 'generateSnapshot').mockRejectedValue(
        new Error('Puppeteer error'),
      );

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

      // Should still return success (snapshot is best-effort)
      const response = await request(app.getHttpServer())
        .post('/api/signals/alert')
        .set('Authorization', 'Bearer test-key-123')
        .send(payload)
        .expect(201);

      expect(response.body.success).toBe(true);

      // Wait for processing
      await new Promise((resolve) => setTimeout(resolve, 1000));

      // Alert should still be created
      const alerts = await alertRepo.find();
      expect(alerts).toHaveLength(1);

      // But no snapshot
      const snapshots = await snapshotRepo.find();
      expect(snapshots).toHaveLength(0);
    });
  });
});
