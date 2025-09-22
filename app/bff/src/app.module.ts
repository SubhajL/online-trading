import { Module } from '@nestjs/common';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { ConfigModule } from './config/config.module';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
// import { MarketDataModule } from './market-data/market-data.module';
// import { TradingModule } from './trading/trading.module';
import { AuthModule } from './auth/auth.module';
import { DatabaseModule } from './database/database.module';
// import { AlertsModule } from './alerts/alerts.module';
import { BalancesModule } from './balances/balances.module';
import { OrdersModule } from './orders/orders.module';

@Module({
  imports: [
    ConfigModule.forRoot(),
    EventEmitterModule.forRoot(),
    DatabaseModule,
    AuthModule,
    HealthModule,
    EngineClientModule,
    RouterClientModule,
    // MarketDataModule,
    // TradingModule,
    // AlertsModule,
    BalancesModule,
    OrdersModule,
  ],
})
export class AppModule {}
