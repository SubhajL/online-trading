import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { EngineClientService } from './engine-client.service';

@Module({
  imports: [ConfigModule, EventEmitterModule],
  providers: [EngineClientService],
  exports: [EngineClientService],
})
export class EngineClientModule {}
