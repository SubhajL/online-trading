import { Test, TestingModule } from '@nestjs/testing';
import { HealthCheckService, HttpHealthIndicator } from '@nestjs/terminus';
import { ConfigService } from '@nestjs/config';
import { EnhancedHealthController } from './health.controller.enhanced';
import { EngineClientService } from '../engine-client/engine-client.service';
import { TypeOrmHealthIndicator } from '@nestjs/terminus';
import { RedisHealthIndicator } from './indicators/redis.health';
import { WebSocketHealthIndicator } from './indicators/websocket.health';
import { DiskHealthIndicator } from './indicators/disk.health';

describe('EnhancedHealthController', () => {
  let controller: EnhancedHealthController;
  let healthCheckService: HealthCheckService;
  let httpHealthIndicator: HttpHealthIndicator;
  let engineClientService: EngineClientService;
  let databaseHealthIndicator: TypeOrmHealthIndicator;
  let redisHealthIndicator: RedisHealthIndicator;
  let wsHealthIndicator: WebSocketHealthIndicator;
  let diskHealthIndicator: DiskHealthIndicator;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [EnhancedHealthController],
      providers: [
        {
          provide: HealthCheckService,
          useValue: {
            check: jest.fn(),
          },
        },
        {
          provide: HttpHealthIndicator,
          useValue: {
            pingCheck: jest.fn(),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn().mockImplementation((key: string) => {
              const config: Record<string, any> = {
                'router.url': 'http://localhost:8080',
                'engine.url': 'http://localhost:8000',
                'redis.host': 'localhost',
                'redis.port': 6379,
              };
              return config[key];
            }),
          },
        },
        {
          provide: EngineClientService,
          useValue: {
            checkHealth: jest.fn(),
          },
        },
        {
          provide: TypeOrmHealthIndicator,
          useValue: {
            pingCheck: jest.fn(),
          },
        },
        {
          provide: RedisHealthIndicator,
          useValue: {
            isHealthy: jest.fn(),
          },
        },
        {
          provide: WebSocketHealthIndicator,
          useValue: {
            isHealthy: jest.fn(),
          },
        },
        {
          provide: DiskHealthIndicator,
          useValue: {
            checkStorage: jest.fn(),
          },
        },
      ],
    }).compile();

    controller = module.get<EnhancedHealthController>(EnhancedHealthController);
    healthCheckService = module.get<HealthCheckService>(HealthCheckService);
    httpHealthIndicator = module.get<HttpHealthIndicator>(HttpHealthIndicator);
    engineClientService = module.get<EngineClientService>(EngineClientService);
    databaseHealthIndicator = module.get<TypeOrmHealthIndicator>(TypeOrmHealthIndicator);
    redisHealthIndicator = module.get<RedisHealthIndicator>(RedisHealthIndicator);
    wsHealthIndicator = module.get<WebSocketHealthIndicator>(WebSocketHealthIndicator);
    diskHealthIndicator = module.get<DiskHealthIndicator>(DiskHealthIndicator);
  });

  describe('comprehensive health check', () => {
    it('should check all critical dependencies', async () => {
      const mockHealthResult = {
        status: 'ok' as const,
        info: {
          router: { status: 'up' },
          engine: { status: 'up' },
          database: { status: 'up' },
          redis: { status: 'up' },
        },
        error: {},
        details: {
          router: { status: 'up' },
          engine: { status: 'up' },
          database: { status: 'up' },
          redis: { status: 'up' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockHealthResult as any);

      await controller.checkComprehensive();

      expect(healthCheckService.check).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.any(Function), // router check
          expect.any(Function), // engine check
          expect.any(Function), // database check
          expect.any(Function), // redis check
          expect.any(Function), // websocket check
          expect.any(Function), // disk check
        ]),
      );
    });
  });

  describe('dependency health checks', () => {
    it('should report degraded status when router has high latency', async () => {
      jest.spyOn(httpHealthIndicator, 'pingCheck').mockResolvedValue({
        router: { status: 'up' },
      });
      const nowSpy = jest.spyOn(Date, 'now').mockReturnValueOnce(1000).mockReturnValueOnce(1301);

      const result = await controller.checkRouter();
      nowSpy.mockRestore();

      expect(result.router.status).toBe('degraded');
      expect(result.router.message).toContain('high latency');
    });

    it('should check database connection pool status', async () => {
      jest.spyOn(databaseHealthIndicator, 'pingCheck').mockResolvedValue({
        database: {
          status: 'up',
          connections: {
            active: 5,
            idle: 10,
            total: 15,
            max: 20,
          },
        },
      });

      const result = await controller.checkDatabase();

      expect(result.database.connections).toBeDefined();
      expect(result.database.connections.active).toBe(5);
    });

    it('should detect Redis memory pressure', async () => {
      jest.spyOn(redisHealthIndicator, 'isHealthy').mockResolvedValue({
        redis: {
          status: 'up',
          memory: {
            used: 900,
            max: 1000,
            percentage: 90,
          },
        },
      });

      const result = await controller.checkRedis();

      expect(result.redis.status).toBe('degraded');
      expect(result.redis.message).toContain('memory pressure');
    });
  });

  describe('WebSocket health check', () => {
    it('should verify active WebSocket connections', async () => {
      jest.spyOn(wsHealthIndicator, 'isHealthy').mockResolvedValue({
        websocket: {
          status: 'up',
          connections: {
            active: 150,
            max: 1000,
          },
          message_rate: 100, // messages per second
        },
      });

      const result = await controller.checkWebSockets();

      expect((result.websocket as any).connections.active).toBe(150);
      expect((result.websocket as any).message_rate).toBe(100);
    });

    it('should report degraded when approaching connection limit', async () => {
      jest.spyOn(wsHealthIndicator, 'isHealthy').mockResolvedValue({
        websocket: {
          status: 'up',
          connections: {
            active: 900,
            max: 1000,
          },
        },
      });

      const result = await controller.checkWebSockets();

      expect(result.websocket.status).toBe('degraded');
      expect(result.websocket.message).toContain('connection limit');
    });
  });

  describe('disk space health check', () => {
    it('should monitor available disk space', async () => {
      jest.spyOn(diskHealthIndicator, 'checkStorage').mockResolvedValue({
        disk: {
          status: 'up',
          path: '/',
          free: 50 * 1024 * 1024 * 1024, // 50GB
          threshold: 10 * 1024 * 1024 * 1024, // 10GB threshold
        },
      });

      const result = await controller.checkDiskSpace();

      expect(result.disk.status).toBe('up');
      expect((result.disk as any).free).toBeGreaterThan((result.disk as any).threshold);
    });

    it('should warn when disk space is low', async () => {
      jest.spyOn(diskHealthIndicator, 'checkStorage').mockResolvedValue({
        disk: {
          status: 'up',
          path: '/',
          free: 5 * 1024 * 1024 * 1024, // 5GB
          threshold: 10 * 1024 * 1024 * 1024, // 10GB threshold
        },
      });

      const result = await controller.checkDiskSpace();

      expect(result.disk.status).toBe('degraded');
      expect(result.disk.message.toLowerCase()).toContain('low disk space');
    });
  });

  describe('detailed health metrics', () => {
    it('should aggregate performance metrics', async () => {
      const metrics = await controller.getDetailedMetrics();

      expect(metrics).toHaveProperty('timestamp');
      expect(metrics).toHaveProperty('uptime');
      expect(metrics).toHaveProperty('memory');
      expect(metrics).toHaveProperty('cpu');
      expect(metrics).toHaveProperty('response_times');
      expect(metrics.response_times).toHaveProperty('router');
      expect(metrics.response_times).toHaveProperty('engine');
    });

    it('should track health check history', async () => {
      jest.spyOn(healthCheckService, 'check').mockResolvedValue({
        status: 'ok',
        info: {},
        error: {},
        details: {},
      } as any);

      // Simulate multiple health checks
      await controller.checkComprehensive();
      await controller.checkComprehensive();
      await controller.checkComprehensive();

      const history = await controller.getHealthHistory();

      expect(history.checks).toHaveLength(3);
      expect(history.checks[0]).toHaveProperty('timestamp');
      expect(history.checks[0]).toHaveProperty('status');
      expect(history.checks[0]).toHaveProperty('duration_ms');
    });
  });

  describe('graceful degradation', () => {
    it('should handle engine service unavailability gracefully', async () => {
      jest
        .spyOn(engineClientService, 'checkHealth')
        .mockRejectedValue(new Error('Connection refused'));

      const result = await controller.checkEngine();

      expect(result.engine.status).toBe('down');
      expect(result.engine.error).toBe('Connection refused');
      expect(result.engine.fallback_mode).toBe(true);
    });

    it('should provide cached health data when services are slow', async () => {
      // Seed cache with a successful result
      jest.spyOn(httpHealthIndicator, 'pingCheck').mockResolvedValue({
        router: { status: 'up' },
      });
      await controller.checkWithTimeout();

      // Simulate slow response to trigger timeout + cached fallback
      (controller as any).HEALTH_CHECK_TIMEOUT_MS = 1;
      jest.spyOn(httpHealthIndicator, 'pingCheck').mockImplementation(() => new Promise(() => {}));

      const result = await controller.checkWithTimeout();

      expect((result as any).router.status).toBe('unknown');
      expect((result as any).router.cached).toBe(true);
      expect((result as any).router.cache_age_ms).toBeDefined();
    });
  });
});
