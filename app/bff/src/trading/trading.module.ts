import { Module } from '@nestjs/common';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { RouterClientModule } from '../router-client/router-client.module';
import { TradingService } from './trading.service';
import { TradingController } from './trading.controller';
import { TradingGateway } from './trading.gateway';

@Module({
  imports: [EventEmitterModule, EngineClientModule, RouterClientModule],
  controllers: [TradingController],
  providers: [TradingService, TradingGateway],
  exports: [TradingService],
})
export class TradingModule {}
