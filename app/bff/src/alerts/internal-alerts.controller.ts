import { Controller, Post, Body, UseGuards, HttpCode, HttpStatus, Logger } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bull';
import { Queue } from 'bull';
import { SignalPayloadDto } from './dto/signal-payload.dto';
import { InternalApiGuard } from '../auth/guards/internal-api.guard';
import { Public } from '../auth/decorators/public.decorator';
import { SnapshotsService } from '../snapshots/snapshots.service';

@Public()
@Controller('internal/alerts')
@UseGuards(InternalApiGuard)
export class InternalAlertsController {
  private readonly logger = new Logger(InternalAlertsController.name);

  constructor(
    @InjectQueue('snapshot') private readonly snapshotQueue: Queue,
    private readonly snapshotsService: SnapshotsService,
  ) {}

  @Post('signal')
  @HttpCode(HttpStatus.OK)
  async createSignalAlert(@Body() payload: SignalPayloadDto): Promise<{
    ok: boolean;
    snapshot?: { id: string; imageUrl: string };
  }> {
    try {
      // Check if snapshot already exists
      const existingSnapshot = await this.snapshotsService.getSnapshot(payload.signalId);
      if (existingSnapshot) {
        return {
          ok: true,
          snapshot: {
            id: existingSnapshot.id,
            imageUrl: existingSnapshot.imageUrl!,
          },
        };
      }

      // Queue snapshot generation
      const job = await this.snapshotQueue.add('generate', payload, {
        attempts: 3,
        backoff: {
          type: 'exponential',
          delay: 2000,
        },
      });

      this.logger.log(`Queued snapshot generation job ${job.id} for signal ${payload.signalId}`);

      // Return immediately with a pending status
      // The actual snapshot will be generated asynchronously
      return {
        ok: true,
        snapshot: {
          id: payload.signalId,
          imageUrl: `/snapshots/${payload.signalId}.png`, // Will be available after processing
        },
      };
    } catch (error) {
      const err = error as Error;
      this.logger.error(`Failed to queue snapshot generation: ${err.message}`, err.stack);
      throw error;
    }
  }
}
