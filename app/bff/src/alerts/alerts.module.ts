import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BullModule } from '@nestjs/bull';
import { AlertsController } from './alerts.controller';
import { InternalAlertsController } from './internal-alerts.controller';
import { AlertsService } from './alerts.service';
import { AlertsGateway } from './alerts.gateway';
import { Alert } from './entities/alert.entity';
import { SnapshotsModule } from '../snapshots/snapshots.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [
    TypeOrmModule.forFeature([Alert]),
    BullModule.registerQueue({
      name: 'snapshot',
    }),
    SnapshotsModule,
    AuthModule,
  ],
  controllers: [AlertsController, InternalAlertsController],
  providers: [AlertsService, AlertsGateway],
  exports: [AlertsService],
})
export class AlertsModule {}
