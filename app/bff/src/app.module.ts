import { Module } from '@nestjs/common';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { ConfigModule } from './config/config.module';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
import { MarketDataModule } from './market-data/market-data.module';
import { TradingModule } from './trading/trading.module';

@Module({
  imports: [
    ConfigModule.forRoot(),
    EventEmitterModule.forRoot(),
    HealthModule,
    EngineClientModule,
    RouterClientModule,
    MarketDataModule,
    TradingModule,
  ],
})
export class AppModule {}
