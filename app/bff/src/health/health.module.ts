import { Module } from '@nestjs/common';
import { TerminusModule } from '@nestjs/terminus';
import { HttpModule } from '@nestjs/axios';
import { ConfigModule } from '@nestjs/config';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { HealthController } from './health.controller';

@Module({
  imports: [ConfigModule, TerminusModule, HttpModule, EngineClientModule],
  controllers: [HealthController],
})
export class HealthModule {}
