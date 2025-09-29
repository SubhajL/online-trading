import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BullModule } from '@nestjs/bull';
import { SignalsController } from './signals.controller';
import { SignalsService } from './signals.service';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { Alert } from '../alerts/entities/alert.entity';
import { AlertsModule } from '../alerts/alerts.module';
import { SnapshotsModule } from '../snapshots/snapshots.module';

@Module({
  imports: [
    TypeOrmModule.forFeature([Alert, AlertSnapshot]),
    BullModule.registerQueue({
      name: 'signal-alerts',
    }),
    AlertsModule,
    SnapshotsModule,
  ],
  controllers: [SignalsController],
  providers: [SignalsService],
  exports: [SignalsService],
})
export class SignalsModule {}
