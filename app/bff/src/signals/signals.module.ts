import { Module } from '@nestjs/common';
import { BullModule } from '@nestjs/bull';
import { SignalsController } from './signals.controller';
import { SignalsService } from './signals.service';
import { SnapshotsModule } from '../snapshots/snapshots.module';

@Module({
  imports: [SnapshotsModule, BullModule.registerQueue({ name: 'snapshot' })],
  controllers: [SignalsController],
  providers: [SignalsService],
  exports: [SignalsService],
})
export class SignalsModule {}
