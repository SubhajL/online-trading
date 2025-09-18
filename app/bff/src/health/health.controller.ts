import { Controller, Get } from '@nestjs/common';
import {
  HealthCheck,
  HealthCheckService,
  HttpHealthIndicator,
  HealthCheckResult,
  HealthIndicatorResult,
} from '@nestjs/terminus';
import { ConfigService } from '@nestjs/config';
import { EngineClientService } from '../engine-client/engine-client.service';

interface LivenessResponse {
  status: string;
  timestamp: Date;
  uptime: number;
}

@Controller('health')
export class HealthController {
  private readonly startTime = Date.now();

  constructor(
    private readonly health: HealthCheckService,
    private readonly http: HttpHealthIndicator,
    private readonly config: ConfigService,
    private readonly engineClient: EngineClientService,
  ) {}

  @Get()
  @HealthCheck()
  check(): Promise<HealthCheckResult> {
    return this.health.check([
      () => this.http.pingCheck('router', this.config.get<string>('router.url')!),
      () => this.checkEngine(),
      () => this.checkDatabase(),
    ]);
  }

  @Get('liveness')
  async liveness(): Promise<LivenessResponse> {
    return {
      status: 'ok',
      timestamp: new Date(),
      uptime: Date.now() - this.startTime,
    };
  }

  @Get('readiness')
  @HealthCheck()
  readiness(): Promise<HealthCheckResult> {
    return this.health.check([
      () => this.checkEngine(),
      () => this.http.pingCheck('router', this.config.get<string>('router.url')!),
    ]);
  }

  private async checkEngine(): Promise<HealthIndicatorResult> {
    const engineHealth = await this.engineClient.checkHealth();

    const result: HealthIndicatorResult = {
      engine: {
        status: engineHealth.status,
        ...engineHealth.details,
      },
    };

    if (engineHealth.status === 'down') {
      throw new Error(engineHealth.details.error || 'Engine is not available');
    }

    return result;
  }

  private async checkDatabase(): Promise<HealthIndicatorResult> {
    // For now, return a mock success. In real implementation, this would check database connection
    const result: HealthIndicatorResult = {
      database: {
        status: 'up',
      },
    };
    return result;
  }
}
