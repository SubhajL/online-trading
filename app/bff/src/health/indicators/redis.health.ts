import { Injectable, Inject } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult, HealthCheckError } from '@nestjs/terminus';
import { Redis } from 'ioredis';

@Injectable()
export class RedisHealthIndicator extends HealthIndicator {
  constructor(@Inject('REDIS_CLIENT') private readonly redis: Redis) {
    super();
  }

  async isHealthy(key: string): Promise<HealthIndicatorResult> {
    const startTime = Date.now();

    try {
      // Ping Redis
      await this.redis.ping();
      const latency = Date.now() - startTime;

      // Get memory info
      const info = await this.redis.info('memory');
      const memoryInfo = this.parseMemoryInfo(info);

      const result = this.getStatus(key, true, {
        status: 'up',
        latency,
        memory: memoryInfo,
      });

      // Check for high latency
      if (latency > 50) {
        (result[key] as Record<string, unknown>).status = 'degraded';
        result[key].message = `Redis responsive but high latency: ${latency}ms`;
      } else {
        result[key].message = 'Redis is healthy';
      }

      return result;
    } catch (error) {
      throw new HealthCheckError(
        'Redis health check failed',
        this.getStatus(key, false, {
          status: 'down',
          error: (error as Error).message,
          latency: Date.now() - startTime,
        }),
      );
    }
  }

  private parseMemoryInfo(info: string): { used: number; max: number; percentage: number } {
    const lines = info.split('\n');
    let used = 0;
    let max = 1073741824; // Default 1GB

    for (const line of lines) {
      if (line.startsWith('used_memory:')) {
        used = parseInt(line.split(':')[1], 10);
      } else if (line.startsWith('maxmemory:')) {
        const parsedMax = parseInt(line.split(':')[1], 10);
        if (parsedMax > 0) {
          max = parsedMax;
        }
      }
    }

    const percentage = (used / max) * 100;

    return {
      used: Math.round(used / 1024 / 1024), // Convert to MB
      max: Math.round(max / 1024 / 1024), // Convert to MB
      percentage: Math.round(percentage),
    };
  }
}
