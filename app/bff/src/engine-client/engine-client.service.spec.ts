import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { Logger } from '@nestjs/common';
import { EngineClientService } from './engine-client.service';
import { EventEmitter2 } from '@nestjs/event-emitter';

// Mock Redis module
jest.mock('redis', () => {
  const mockRedisClient = {
    connect: jest.fn().mockResolvedValue(undefined),
    quit: jest.fn().mockResolvedValue(undefined),
    ping: jest.fn().mockResolvedValue('PONG'),
    publish: jest.fn().mockResolvedValue(1),
    pSubscribe: jest.fn().mockResolvedValue(undefined),
    on: jest.fn(),
    duplicate: jest.fn().mockReturnThis(),
  };
  return {
    createClient: jest.fn(() => mockRedisClient),
  };
});

// Mock net module for TCP
jest.mock('net', () => {
  const mockSocket: any = {
    connect: jest.fn(),
    write: jest.fn().mockReturnValue(true),
    destroy: jest.fn(),
    on: jest.fn(),
  };

  mockSocket.connect.mockImplementation((port: number, host: string, callback: () => void) => {
    setImmediate(callback);
    return mockSocket;
  });

  return {
    Socket: jest.fn(() => mockSocket),
  };
});

describe('EngineClientService', () => {
  let service: EngineClientService;
  let configService: ConfigService;

  const mockConfigService = {
    get: jest.fn((key: string) => {
      const config: any = {
        'engine.type': 'redis',
        'engine.host': 'localhost',
        'engine.port': 6379,
      };
      return config[key];
    }),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    // Reset the mock to default values
    mockConfigService.get.mockImplementation((key: string) => {
      const config: any = {
        'engine.type': 'redis',
        'engine.host': 'localhost',
        'engine.port': 6379,
      };
      return config[key];
    });

    const module: TestingModule = await Test.createTestingModule({
      imports: [],
      providers: [
        EngineClientService,
        {
          provide: ConfigService,
          useValue: mockConfigService,
        },
      ],
    }).compile();

    // Disable logger output during tests
    module.useLogger(false);

    service = module.get<EngineClientService>(EngineClientService);
    configService = module.get<ConfigService>(ConfigService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('initialization', () => {
    it('should initialize with redis configuration', () => {
      expect(configService.get).toHaveBeenCalledWith('engine.type');
      expect(configService.get).toHaveBeenCalledWith('engine.host');
      expect(configService.get).toHaveBeenCalledWith('engine.port');
    });

    it('should initialize with tcp configuration when type is tcp', async () => {
      mockConfigService.get.mockImplementation((key: string) => {
        const config: any = {
          'engine.type': 'tcp',
          'engine.host': 'localhost',
          'engine.port': 8000,
        };
        return config[key];
      });

      const module: TestingModule = await Test.createTestingModule({
        providers: [
          EngineClientService,
          {
            provide: ConfigService,
            useValue: mockConfigService,
          },
        ],
      }).compile();

      module.useLogger(false);
      const tcpService = module.get<EngineClientService>(EngineClientService);
      expect(tcpService).toBeDefined();
    });
  });

  describe('connect', () => {
    it('should connect to engine service', async () => {
      await expect(service.connect()).resolves.not.toThrow();
    });

    it('should handle connection errors', async () => {
      // Create a new service instance with failing redis connection
      const redis = require('redis');
      redis.createClient.mockImplementationOnce(() => ({
        connect: jest.fn().mockRejectedValue(new Error('Connection failed')),
        quit: jest.fn(),
        ping: jest.fn(),
        publish: jest.fn(),
        pSubscribe: jest.fn(),
        on: jest.fn(),
        duplicate: jest.fn().mockReturnThis(),
      }));

      // Create new service instance to use the mocked redis client
      const module = await Test.createTestingModule({
        providers: [
          EngineClientService,
          {
            provide: ConfigService,
            useValue: mockConfigService,
          },
        ],
      }).compile();

      module.useLogger(false);
      const failingService = module.get<EngineClientService>(EngineClientService);

      await expect(failingService.connect()).rejects.toThrow('Connection failed');
    });
  });

  describe('disconnect', () => {
    it('should disconnect from engine service', async () => {
      await service.connect();
      await expect(service.disconnect()).resolves.not.toThrow();
    });
  });

  describe('subscribe', () => {
    it('should subscribe to engine events', async () => {
      await service.connect();
      const callback = jest.fn();

      service.subscribe('candles.v1', callback);

      // Simulate event
      service.emit('candles.v1', { test: 'data' });

      expect(callback).toHaveBeenCalledWith({ test: 'data' });
    });

    it('should handle multiple subscriptions', async () => {
      await service.connect();
      const callback1 = jest.fn();
      const callback2 = jest.fn();

      service.subscribe('signals.v1', callback1);
      service.subscribe('orders.v1', callback2);

      service.emit('signals.v1', { signal: 'buy' });
      service.emit('orders.v1', { order: 'filled' });

      expect(callback1).toHaveBeenCalledWith({ signal: 'buy' });
      expect(callback2).toHaveBeenCalledWith({ order: 'filled' });
    });
  });

  describe('publish', () => {
    it('should publish events to engine', async () => {
      await service.connect();

      const event = { type: 'test', data: 'value' };
      await expect(service.publish('test.event', event)).resolves.not.toThrow();
    });

    it('should handle publish errors', async () => {
      await service.connect();

      // Mock a publish failure
      jest.spyOn(service as any, 'publishToEngine').mockRejectedValue(new Error('Publish failed'));

      await expect(service.publish('test.event', {})).rejects.toThrow('Publish failed');
    });
  });

  describe('health check', () => {
    it('should report healthy when connected', async () => {
      await service.connect();
      const health = await service.checkHealth();

      expect(health).toEqual({
        status: 'up',
        details: expect.objectContaining({
          connected: true,
          type: 'redis',
        }),
      });
    });

    it('should report unhealthy when disconnected', async () => {
      const health = await service.checkHealth();

      expect(health).toEqual({
        status: 'down',
        details: expect.objectContaining({
          connected: false,
        }),
      });
    });
  });
});
