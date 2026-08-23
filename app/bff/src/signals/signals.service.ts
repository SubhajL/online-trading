import { Injectable, Logger } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bull';
import { Queue } from 'bull';
import { SnapshotsService } from '../snapshots/snapshots.service';
import type { SignalPayloadDto } from '../alerts/dto/signal-payload.dto';

export interface SignalAlertResponse {
  ok: boolean;
  snapshot?: {
    id: string;
    imageUrl: string;
  };
}

@Injectable()
export class SignalsService {
  private readonly logger = new Logger(SignalsService.name);

  constructor(
    private readonly snapshotsService: SnapshotsService,
    @InjectQueue('snapshot') private readonly snapshotQueue: Queue,
  ) {}

  async getSnapshotUrl(signalId: string): Promise<string | null> {
    const snapshot = await this.snapshotsService.getSnapshotBySignalId(signalId);
    return snapshot?.imageUrl ?? null;
  }

  async createSignalAlert(payload: SignalPayloadDto): Promise<SignalAlertResponse> {
    const existingSnapshot = await this.snapshotsService.getSnapshotBySignalId(payload.signalId);

    if (existingSnapshot) {
      return {
        ok: true,
        snapshot: {
          id: existingSnapshot.id,
          imageUrl: existingSnapshot.imageUrl!,
        },
      };
    }

    const job = await this.snapshotQueue.add('generate', payload, {
      jobId: payload.signalId,
      attempts: 3,
      backoff: { type: 'exponential', delay: 2000 },
    });

    this.logger.log(`Queued snapshot job ${job.id} for signal ${payload.signalId}`);

    // Sanitize signalId for URL
    const safeSignalId = payload.signalId.replace(/[^a-zA-Z0-9_-]/g, '_');
    return {
      ok: true,
      snapshot: {
        id: payload.signalId,
        imageUrl: `/api/snapshots/${safeSignalId}.png`,
      },
    };
  }
}
