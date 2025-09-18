export interface Configuration {
  nodeEnv: string;
  port: number;
  engine: {
    host: string;
    port: number;
    type: 'redis' | 'tcp';
  };
  router: {
    url: string;
    timeout: number;
    retryAttempts: number;
    retryDelay: number;
  };
  websocket: {
    corsOrigin: string;
    namespace: string;
  };
  redis?: {
    host: string;
    port: number;
    password?: string;
    db: number;
  };
  rateLimit: {
    windowMs: number;
    maxRequests: number;
  };
  logging: {
    level: string;
    format: string;
  };
}

export function loadConfiguration(): Configuration {
  const parseIntWithDefault = (value: string | undefined, defaultValue: number): number => {
    if (!value) return defaultValue;
    const parsed = parseInt(value, 10);
    return isNaN(parsed) ? defaultValue : parsed;
  };

  const config: Configuration = {
    nodeEnv: process.env.NODE_ENV || 'development',
    port: parseIntWithDefault(process.env.PORT, 3001),
    engine: {
      host: process.env.ENGINE_HOST || 'localhost',
      port: parseIntWithDefault(process.env.ENGINE_PORT, 6379),
      type: (process.env.ENGINE_TYPE as 'redis' | 'tcp') || 'redis',
    },
    router: {
      url: process.env.ROUTER_URL || 'http://localhost:8080',
      timeout: parseIntWithDefault(process.env.ROUTER_TIMEOUT, 30000),
      retryAttempts: parseIntWithDefault(process.env.ROUTER_RETRY_ATTEMPTS, 3),
      retryDelay: parseIntWithDefault(process.env.ROUTER_RETRY_DELAY, 1000),
    },
    websocket: {
      corsOrigin: process.env.WS_CORS_ORIGIN || 'http://localhost:3000',
      namespace: process.env.WS_NAMESPACE || '/trading',
    },
    rateLimit: {
      windowMs: parseIntWithDefault(process.env.RATE_LIMIT_WINDOW_MS, 60000),
      maxRequests: parseIntWithDefault(process.env.RATE_LIMIT_MAX_REQUESTS, 100),
    },
    logging: {
      level: process.env.LOG_LEVEL || 'debug',
      format: process.env.LOG_FORMAT || 'json',
    },
  };

  // Add Redis configuration if engine type is redis
  if (config.engine.type === 'redis') {
    config.redis = {
      host: process.env.REDIS_HOST || 'localhost',
      port: parseIntWithDefault(process.env.REDIS_PORT, 6379),
      password: process.env.REDIS_PASSWORD,
      db: parseIntWithDefault(process.env.REDIS_DB, 0),
    };
  }

  return config;
}
