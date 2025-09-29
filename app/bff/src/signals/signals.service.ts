import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectQueue } from '@nestjs/bull';
import { InjectRepository } from '@nestjs/typeorm';
import { Queue } from 'bull';
import { Repository } from 'typeorm';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { Alert } from '../alerts/entities/alert.entity';
import { AlertsService } from '../alerts/alerts.service';
import { SnapshotsService } from '../snapshots/snapshots.service';
import { CreateSignalAlertDto } from './dto/create-signal-alert.dto';

@Injectable()
export class SignalsService {
  constructor(
    @InjectQueue('signal-alerts') private signalQueue: Queue,
    @InjectRepository(Alert) private alertRepository: Repository<Alert>,
    @InjectRepository(AlertSnapshot) private snapshotRepository: Repository<AlertSnapshot>,
    private alertsService: AlertsService,
    private snapshotsService: SnapshotsService,
  ) {}

  async createAlert(dto: CreateSignalAlertDto) {
    // Check for existing alert to ensure idempotency
    const existingAlert = await this.alertRepository.findOne({
      where: {
        data: { signalId: dto.signalId } as any,
      },
    });

    if (!existingAlert) {
      // Queue the signal processing
      await this.signalQueue.add('process-signal', dto);

      // Create alert record
      await this.alertRepository.save({
        type: 'smc',
        priority: 'high',
        title: `Signal: ${dto.side} ${dto.symbol}`,
        message: `Trading signal for ${dto.symbol} - ${dto.side} at ${dto.entry}`,
        data: dto,
        read: false,
      });
    }

    return { signalId: dto.signalId };
  }

  async getSnapshot(signalId: string) {
    const snapshot = await this.snapshotRepository.findOne({
      where: { signalId },
    });

    if (!snapshot) {
      throw new NotFoundException('Snapshot not found');
    }

    return snapshot;
  }
}