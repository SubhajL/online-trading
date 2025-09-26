import { Module } from '@nestjs/common';
import { TerminusModule } from '@nestjs/terminus';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { HealthController } from './health.controller';
import { EnhancedHealthController } from './health.controller.enhanced';
import { RedisHealthIndicator } from './indicators/redis.health';
import { WebSocketHealthIndicator } from './indicators/websocket.health';
import { DiskHealthIndicator } from './indicators/disk.health';
import { WebSocketHealthGateway } from '../websockets/websocket.gateway';
import { Redis } from 'ioredis';

@Module({
  imports: [ConfigModule, TerminusModule, HttpModule, EngineClientModule],
  controllers: [HealthController, EnhancedHealthController],
  providers: [
    {
      provide: 'REDIS_CLIENT',
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => {
        return new Redis({
          host: configService.get<string>('REDIS_HOST', 'localhost'),
          port: configService.get<number>('REDIS_PORT', 6379),
          password: configService.get<string>('REDIS_PASSWORD'),
        });
      },
    },
    RedisHealthIndicator,
    WebSocketHealthIndicator,
    DiskHealthIndicator,
    WebSocketHealthGateway,
  ],
})
export class HealthModule {}
