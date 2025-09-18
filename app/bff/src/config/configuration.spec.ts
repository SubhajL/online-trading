import { loadConfiguration } from './configuration';

describe('loadConfiguration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('loads default configuration values', () => {
    delete process.env.NODE_ENV;
    const config = loadConfiguration();

    expect(config.nodeEnv).toBe('development');
    expect(config.port).toBe(3001);
    expect(config.engine.host).toBe('localhost');
    expect(config.engine.port).toBe(6379);
    expect(config.engine.type).toBe('redis');
    expect(config.router.url).toBe('http://localhost:8080');
    expect(config.router.timeout).toBe(30000);
    expect(config.router.retryAttempts).toBe(3);
    expect(config.router.retryDelay).toBe(1000);
    expect(config.websocket.corsOrigin).toBe('http://localhost:3000');
    expect(config.websocket.namespace).toBe('/trading');
  });

  it('overrides configuration from environment variables', () => {
    process.env.NODE_ENV = 'production';
    process.env.PORT = '4000';
    process.env.ENGINE_HOST = '192.168.1.100';
    process.env.ENGINE_PORT = '7000';
    process.env.ENGINE_TYPE = 'tcp';
    process.env.ROUTER_URL = 'https://api.router.com';
    process.env.ROUTER_TIMEOUT = '60000';
    process.env.ROUTER_RETRY_ATTEMPTS = '5';
    process.env.ROUTER_RETRY_DELAY = '2000';
    process.env.WS_CORS_ORIGIN = 'https://app.example.com';
    process.env.WS_NAMESPACE = '/ws';

    const config = loadConfiguration();

    expect(config.nodeEnv).toBe('production');
    expect(config.port).toBe(4000);
    expect(config.engine.host).toBe('192.168.1.100');
    expect(config.engine.port).toBe(7000);
    expect(config.engine.type).toBe('tcp');
    expect(config.router.url).toBe('https://api.router.com');
    expect(config.router.timeout).toBe(60000);
    expect(config.router.retryAttempts).toBe(5);
    expect(config.router.retryDelay).toBe(2000);
    expect(config.websocket.corsOrigin).toBe('https://app.example.com');
    expect(config.websocket.namespace).toBe('/ws');
  });

  it('includes redis configuration when engine type is redis', () => {
    process.env.ENGINE_TYPE = 'redis';
    process.env.REDIS_HOST = 'redis.example.com';
    process.env.REDIS_PORT = '6380';
    process.env.REDIS_PASSWORD = 'secret';
    process.env.REDIS_DB = '1';

    const config = loadConfiguration();

    expect(config.redis).toBeDefined();
    expect(config.redis!.host).toBe('redis.example.com');
    expect(config.redis!.port).toBe(6380);
    expect(config.redis!.password).toBe('secret');
    expect(config.redis!.db).toBe(1);
  });

  it('includes rate limiting configuration', () => {
    process.env.RATE_LIMIT_WINDOW_MS = '120000';
    process.env.RATE_LIMIT_MAX_REQUESTS = '200';

    const config = loadConfiguration();

    expect(config.rateLimit.windowMs).toBe(120000);
    expect(config.rateLimit.maxRequests).toBe(200);
  });

  it('includes logging configuration', () => {
    process.env.LOG_LEVEL = 'warn';
    process.env.LOG_FORMAT = 'text';

    const config = loadConfiguration();

    expect(config.logging.level).toBe('warn');
    expect(config.logging.format).toBe('text');
  });

  it('validates numeric environment variables', () => {
    process.env.PORT = 'not-a-number';

    const config = loadConfiguration();

    expect(config.port).toBe(3001); // Should fall back to default
  });
});

describe('Configuration types', () => {
  it('exports proper type definitions', () => {
    const config = loadConfiguration();

    // Type checking - these should compile without errors
    const nodeEnv: string = config.nodeEnv;
    const port: number = config.port;
    const engineType: 'redis' | 'tcp' = config.engine.type;

    expect(nodeEnv).toBeTruthy();
    expect(port).toBeTruthy();
    expect(engineType).toBeTruthy();
  });
});
