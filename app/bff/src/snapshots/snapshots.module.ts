import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BullModule } from '@nestjs/bull';
import { SnapshotsController } from './snapshots.controller';
import { SnapshotsService } from './snapshots.service';
import { SnapshotGeneratorService } from './snapshot-generator.service';
import { SnapshotProcessor } from './snapshot.processor';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';

@Module({
  imports: [
    TypeOrmModule.forFeature([AlertSnapshot]),
    BullModule.registerQueue({
      name: 'snapshot',
    }),
  ],
  controllers: [SnapshotsController],
  providers: [SnapshotsService, SnapshotGeneratorService, SnapshotProcessor],
  exports: [SnapshotsService],
})
export class SnapshotsModule {}
