import { Module } from '@nestjs/common';
import { EventEmitterModule } from '@nestjs/event-emitter';
import { BullModule } from '@nestjs/bull';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { loadConfiguration } from './config/configuration';
import { ServeStaticModule } from '@nestjs/serve-static';
import { HealthModule } from './health/health.module';
import { EngineClientModule } from './engine-client/engine-client.module';
import { RouterClientModule } from './router-client/router-client.module';
import { MarketDataModule } from './market-data/market-data.module';
import { TradingModule } from './trading/trading.module';
import { AuthModule } from './auth/auth.module';
import { DatabaseModule } from './database/database.module';
import { AlertsModule } from './alerts/alerts.module';
import { SnapshotsModule } from './snapshots/snapshots.module';
import { BalancesModule } from './balances/balances.module';
import { OrdersModule } from './orders/orders.module';
import { DashboardModule } from './dashboard/dashboard.module';
import { SignalsModule } from './signals/signals.module';
import { SoakModule } from './soak/soak.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      load: [loadConfiguration],
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
    ServeStaticModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (configService: ConfigService) => [
        {
          rootPath: configService.get<string>('SNAPSHOT_STORAGE_DIR', '/var/app/snapshots'),
          serveRoot: '/api/snapshots',
          serveStaticOptions: {
            index: false,
            maxAge: 86400000, // 1 day cache
          },
        },
      ],
    }),
    DatabaseModule,
    AuthModule,
    HealthModule,
    EngineClientModule,
    RouterClientModule,
    MarketDataModule,
    TradingModule,
    AlertsModule,
    SnapshotsModule,
    BalancesModule,
    OrdersModule,
    DashboardModule,
    SignalsModule,
    SoakModule,
  ],
})
export class AppModule {}
