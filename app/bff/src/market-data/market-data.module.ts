import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { EngineClientModule } from '../engine-client/engine-client.module';
import { MarketDataGateway } from './market-data.gateway';

@Module({
  imports: [ConfigModule, EngineClientModule],
  providers: [MarketDataGateway],
  exports: [MarketDataGateway],
})
export class MarketDataModule {}
