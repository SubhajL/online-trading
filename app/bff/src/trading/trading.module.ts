import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { CqrsModule } from '@nestjs/cqrs';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { RouterClientModule } from '../router-client/router-client.module';
import { AuthModule } from '../auth/auth.module';
import { TradingService } from './trading.service';
import { TradingController } from './trading.controller';
import { TradingGateway } from './trading.gateway';
import { Order, Position } from '../database/entities';
import { CommandHandlers } from './commands/handlers';

@Module({
  imports: [
    EventEmitterModule,
    CqrsModule,
    TypeOrmModule.forFeature([Order, Position]),
    EngineClientModule,
    RouterClientModule,
    AuthModule,
  ],
  controllers: [TradingController],
  providers: [TradingService, TradingGateway, ...CommandHandlers],
  exports: [TradingService],
})
export class TradingModule {}
