import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { CqrsModule } from '@nestjs/cqrs';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { RouterClientModule } from '../router-client/router-client.module';
import { AuthModule } from '../auth/auth.module';
import { OrdersModule } from '../orders/orders.module';
import { TradingService } from './trading.service';
import { InternalTradingController, TradingController } from './trading.controller';
import { TradingGateway } from './trading.gateway';
import { CommandHandlers } from './commands/handlers';
import { EmergencyCloseService } from './emergency-close.service';
import { EmergencyCloseOperationEntity } from './entities/emergency-close-operation.entity';
import { EmergencyCloseOperationRepository } from './repositories/emergency-close-operation.repository';

@Module({
  imports: [
    EventEmitterModule,
    CqrsModule,
    TypeOrmModule.forFeature([EmergencyCloseOperationEntity]),
    EngineClientModule,
    RouterClientModule,
    AuthModule,
    OrdersModule,
  ],
  controllers: [TradingController, InternalTradingController],
  providers: [
    TradingService,
    TradingGateway,
    EmergencyCloseService,
    EmergencyCloseOperationRepository,
    ...CommandHandlers,
  ],
  exports: [TradingService],
})
export class TradingModule {}
