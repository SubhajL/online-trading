import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { CqrsModule } from '@nestjs/cqrs';
import { TypeOrmModule } from '@nestjs/typeorm';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { AuthModule } from '../auth/auth.module';
import { MarketDataGateway } from './market-data.gateway';
import { MarketDataController } from './market-data.controller';
import { Candle, Indicators, SmcEvent, Zone } from '../database/entities';
import { QueryHandlers } from './queries/handlers';

@Module({
  imports: [
    ConfigModule,
    CqrsModule,
    TypeOrmModule.forFeature([Candle, Indicators, SmcEvent, Zone]),
    EngineClientModule,
    AuthModule,
  ],
  controllers: [MarketDataController],
  providers: [MarketDataGateway, ...QueryHandlers],
  exports: [MarketDataGateway],
})
export class MarketDataModule {}
