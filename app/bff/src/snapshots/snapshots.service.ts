import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { AlertSnapshotDto } from '../alerts/dto/alert-snapshot.dto';
import * as fs from 'fs/promises';
import * as path from 'path';

@Injectable()
export class SnapshotsService {
  private readonly logger = new Logger(SnapshotsService.name);
  private readonly storageDir = process.env.SNAPSHOT_STORAGE_DIR || '/var/app/snapshots';

  constructor(
    @InjectRepository(AlertSnapshot)
    private readonly snapshotRepository: Repository<AlertSnapshot>,
  ) {}

  async saveSnapshot(
    signalId: string,
    imageBuffer: Buffer,
    metadata: Record<string, unknown>,
  ): Promise<AlertSnapshotDto> {
    // Check if snapshot already exists
    const existing = await this.snapshotRepository.findOne({
      where: { signalId },
    });

    if (existing) {
      this.logger.debug(`Snapshot already exists for signal ${signalId}`);
      return this.mapToDto(existing);
    }

    // Sanitize signalId to prevent path traversal
    const safeSignalId = signalId.replace(/[^a-zA-Z0-9_-]/g, '_');
    const filename = `${safeSignalId}.png`;
    const imagePath = path.join(this.storageDir, filename);

    // Ensure directory exists
    await fs.mkdir(this.storageDir, { recursive: true });

    // Write file to disk
    await fs.writeFile(imagePath, imageBuffer);

    // Save to database
    const snapshot = this.snapshotRepository.create({
      signalId,
      symbol: String(metadata.symbol ?? ''),
      timeframe: String(metadata.timeframe ?? ''),
      imagePath,
      meta: metadata,
    });

    const saved = await this.snapshotRepository.save(snapshot);
    return this.mapToDto(saved);
  }

  async getSnapshot(id: string): Promise<AlertSnapshotDto | null> {
    const snapshot = await this.snapshotRepository.findOne({
      where: { id },
    });

    if (!snapshot) {
      return null;
    }

    return this.mapToDto(snapshot);
  }

  async getSnapshotBySignalId(signalId: string): Promise<AlertSnapshotDto | null> {
    const snapshot = await this.snapshotRepository.findOne({
      where: { signalId },
    });

    if (!snapshot) {
      return null;
    }

    return this.mapToDto(snapshot);
  }

  async deleteOldSnapshots(olderThanDays = 30): Promise<number> {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - olderThanDays);

    // Find old snapshots
    const oldSnapshots = await this.snapshotRepository
      .createQueryBuilder('snapshot')
      .where('snapshot.createdAt < :cutoffDate', { cutoffDate })
      .getMany();

    // Delete files
    for (const snapshot of oldSnapshots) {
      try {
        await fs.unlink(snapshot.imagePath);
      } catch (error) {
        this.logger.warn(
          `Failed to delete file ${snapshot.imagePath}: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    }

    // Delete database records
    const result = await this.snapshotRepository
      .createQueryBuilder()
      .delete()
      .where('createdAt < :cutoffDate', { cutoffDate })
      .execute();

    return result.affected || 0;
  }

  private mapToDto(entity: AlertSnapshot): AlertSnapshotDto {
    // Sanitize signalId for URL to match saved filename
    const safeSignalId = entity.signalId.replace(/[^a-zA-Z0-9_-]/g, '_');
    return {
      id: entity.id,
      signalId: entity.signalId,
      symbol: entity.symbol,
      timeframe: entity.timeframe,
      imagePath: entity.imagePath,
      imageUrl: `/api/snapshots/${safeSignalId}.png`,
      meta: entity.meta,
      createdAt: entity.createdAt,
    };
  }
}
