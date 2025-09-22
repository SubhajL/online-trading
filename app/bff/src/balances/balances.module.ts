import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BalancesController } from './balances.controller';
import { BalancesService } from './balances.service';
import { BalanceEntity } from './entities/balance-entity';
import { BalanceRepository } from './repositories/balance.repository';

@Module({
  imports: [TypeOrmModule.forFeature([BalanceEntity])],
  controllers: [BalancesController],
  providers: [BalancesService, BalanceRepository],
  exports: [BalancesService],
})
export class BalancesModule {}
