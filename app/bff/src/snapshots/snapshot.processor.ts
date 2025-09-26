import { Process, Processor } from '@nestjs/bull';
import { Logger } from '@nestjs/common';
import { Job } from 'bull';
import { SnapshotsService } from './snapshots.service';
import { SnapshotGeneratorService } from './snapshot-generator.service';
import { SignalPayloadDto } from '../alerts/dto/signal-payload.dto';

@Processor('snapshot')
export class SnapshotProcessor {
  private readonly logger = new Logger(SnapshotProcessor.name);

  constructor(
    private readonly snapshotsService: SnapshotsService,
    private readonly generatorService: SnapshotGeneratorService,
  ) {}

  @Process('generate')
  async handleGenerate(job: Job<SignalPayloadDto>): Promise<void> {
    const signal = job.data;
    this.logger.log(`Processing snapshot generation for signal ${signal.signalId}`);

    try {
      // Generate PNG buffer
      const imageBuffer = await this.generatorService.generateSnapshot(signal);

      // Save to disk and database
      const snapshot = await this.snapshotsService.saveSnapshot(signal.signalId, imageBuffer, {
        symbol: signal.symbol,
        timeframe: signal.timeframe,
        entry: signal.entry,
        stopLoss: signal.stopLoss,
        takeProfit: signal.takeProfit,
        signalTime: signal.signalTime,
        side: signal.side,
        reasons: signal.reasons,
      });

      this.logger.log(`Snapshot generated and saved: ${snapshot.id}`);
    } catch (error) {
      const err = error as Error;
      this.logger.error(`Failed to process snapshot generation: ${error}`, err.stack);
      throw error; // Let Bull handle retry logic
    }
  }
}
