import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DashboardController } from './dashboard.controller';
import { DashboardService } from './dashboard.service';
import { BalancesModule } from '../balances/balances.module';
import { TradingModule } from '../trading/trading.module';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { EquitySampleEntity } from './entities/equity-sample.entity';
import { EquitySampleRepository } from './repositories/equity-sample.repository';

@Module({
  imports: [
    BalancesModule,
    TradingModule,
    EngineClientModule,
    TypeOrmModule.forFeature([EquitySampleEntity]),
  ],
  controllers: [DashboardController],
  providers: [DashboardService, EquitySampleRepository],
  exports: [DashboardService],
})
export class DashboardModule {}
