import { Module } from '@nestjs/common';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { BullModule } from '@nestjs/bull';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
// import { MarketDataModule } from './market-data/market-data.module';
// import { TradingModule } from './trading/trading.module';
import { AuthModule } from './auth/auth.module';
import { DatabaseModule } from './database/database.module';
import { AlertsModule } from './alerts/alerts.module';
import { SnapshotsModule } from './snapshots/snapshots.module';
import { BalancesModule } from './balances/balances.module';
import { OrdersModule } from './orders/orders.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
    }),
    EventEmitterModule.forRoot(),
    BullModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => ({
        redis: {
          host: configService.get<string>('REDIS_HOST', 'localhost'),
          port: configService.get<number>('REDIS_PORT', 6379),
          password: configService.get<string>('REDIS_PASSWORD'),
        },
      }),
    }),
    DatabaseModule,
    AuthModule,
    HealthModule,
    EngineClientModule,
    RouterClientModule,
    // MarketDataModule,
    // TradingModule,
    AlertsModule,
    SnapshotsModule,
    BalancesModule,
    OrdersModule,
  ],
})
export class AppModule {}
