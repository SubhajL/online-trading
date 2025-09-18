import { Test, TestingModule } from '@nestjs/testing';
import { HealthCheckService, HttpHealthIndicator, TerminusModule } from '@nestjs/terminus';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { HealthController } from './health.controller';
import { EngineClientService } from '../engine-client/engine-client.service';

describe('HealthController', () => {
  let controller: HealthController;
  let healthCheckService: HealthCheckService;
  let engineClientService: EngineClientService;

  const mockEngineClientService = {
    checkHealth: jest.fn().mockResolvedValue({
      status: 'up',
      details: {
        connected: true,
        type: 'redis',
        host: 'localhost',
        port: 6379,
      },
    }),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      imports: [TerminusModule],
      controllers: [HealthController],
      providers: [
        {
          provide: ConfigService,
          useValue: {
            get: jest.fn((key: string) => {
              const config: Record<string, any> = {
                'router.url': 'http://localhost:8080',
                'engine.host': 'localhost',
                'engine.port': 6379,
              };
              return config[key];
            }),
          },
        },
        {
          provide: HttpHealthIndicator,
          useValue: {
            pingCheck: jest.fn().mockResolvedValue({ router: { status: 'up' } }),
          },
        },
        {
          provide: EngineClientService,
          useValue: mockEngineClientService,
        },
      ],
    }).compile();

    controller = module.get<HealthController>(HealthController);
    healthCheckService = module.get<HealthCheckService>(HealthCheckService);
    engineClientService = module.get<EngineClientService>(EngineClientService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('check', () => {
    it('returns health status for all services', async () => {
      const mockHealthCheckResult = {
        status: 'ok',
        info: {
          router: { status: 'up' },
          engine: { status: 'up' },
          database: { status: 'up' },
        },
        error: {},
        details: {
          router: { status: 'up' },
          engine: { status: 'up' },
          database: { status: 'up' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockHealthCheckResult as any);

      const result = await controller.check();

      expect(result.status).toBe('ok');
      expect(result.info).toHaveProperty('router');
      expect(result.info).toHaveProperty('engine');
      expect(result.info).toHaveProperty('database');
    });

    it('handles service failures gracefully', async () => {
      const mockHealthCheckResult = {
        status: 'error',
        info: {
          engine: { status: 'up' },
        },
        error: {
          router: { status: 'down', message: 'Connection refused' },
        },
        details: {
          engine: { status: 'up' },
          router: { status: 'down', message: 'Connection refused' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockHealthCheckResult as any);

      const result = await controller.check();

      expect(result.status).toBe('error');
      expect(result.error).toHaveProperty('router');
      expect(result.error!.router.status).toBe('down');
    });

    it('handles engine down status correctly', async () => {
      // Mock engine being down
      mockEngineClientService.checkHealth.mockResolvedValueOnce({
        status: 'down',
        details: {
          connected: false,
          type: 'redis',
          host: 'localhost',
          port: 6379,
          error: 'Connection refused',
        },
      });

      const mockHealthCheckResult = {
        status: 'error',
        info: {},
        error: {
          engine: { status: 'down', message: 'Engine is not available' },
        },
        details: {
          engine: { status: 'down', message: 'Engine is not available' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockHealthCheckResult as any);

      const result = await controller.check();

      expect(result.status).toBe('error');
      expect(result.error).toHaveProperty('engine');
    });
  });

  describe('liveness', () => {
    it('returns basic liveness status', async () => {
      const result = await controller.liveness();

      expect(result).toEqual({
        status: 'ok',
        timestamp: expect.any(Date),
        uptime: expect.any(Number),
      });
    });

    it('includes positive uptime', async () => {
      const result = await controller.liveness();

      expect(result.uptime).toBeGreaterThanOrEqual(0);
      expect(typeof result.uptime).toBe('number');
    });
  });

  describe('readiness', () => {
    it('checks readiness of critical services', async () => {
      const mockReadinessResult = {
        status: 'ok',
        info: {
          engine: { status: 'up' },
          router: { status: 'up' },
        },
        error: {},
        details: {
          engine: { status: 'up' },
          router: { status: 'up' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockReadinessResult as any);

      const result = await controller.readiness();

      expect(result.status).toBe('ok');
      expect(healthCheckService.check).toHaveBeenCalled();
    });

    it('returns not ready when critical services are down', async () => {
      const mockReadinessResult = {
        status: 'error',
        info: {},
        error: {
          engine: { status: 'down', message: 'Connection timeout' },
        },
        details: {
          engine: { status: 'down', message: 'Connection timeout' },
        },
      };

      jest.spyOn(healthCheckService, 'check').mockResolvedValue(mockReadinessResult as any);

      const result = await controller.readiness();

      expect(result.status).toBe('error');
      expect(result.error).toHaveProperty('engine');
    });
  });
});
