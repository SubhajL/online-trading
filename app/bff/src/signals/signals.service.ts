import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bull';
import { Queue } from 'bull';
import { AlertsService } from '../alerts/alerts.service';
import { SnapshotsService } from '../snapshots/snapshots.service';
import { CreateSignalAlertDto } from './dto/create-signal-alert.dto';

@Injectable()
export class SignalsService {
  constructor(
    @InjectQueue('signal-alerts') private signalQueue: Queue,
    private alertsService: AlertsService,
    private snapshotsService: SnapshotsService,
  ) {}

  async createAlert(dto: CreateSignalAlertDto) {
    // Check for existing alert to ensure idempotency
    const existingAlert = await this.alertsService.findByData({
      signalId: dto.signalId,
    });

    if (existingAlert) {
      return {
        signalId: dto.signalId,
        success: true,
        message: 'Signal alert already exists',
      };
    }

    // Queue the signal processing
    await this.signalQueue.add('process-signal', dto);

    // Create alert record via service
    await this.alertsService.create({
      type: 'smc',
      priority: 'high',
      title: `Signal: ${dto.side} ${dto.symbol}`,
      message: `Trading signal for ${dto.symbol} - ${dto.side} at ${dto.entry}`,
      data: dto,
    });

    return {
      signalId: dto.signalId,
      success: true,
      message: 'Signal alert queued for processing',
    };
  }

  async getSnapshot(signalId: string) {
    const snapshot = await this.snapshotsService.findBySignalId(signalId);

    if (!snapshot) {
      throw new NotFoundException('Snapshot not found');
    }

    return snapshot;
  }
}
