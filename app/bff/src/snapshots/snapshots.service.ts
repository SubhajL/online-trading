import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AlertSnapshot } from '../database/entities/alert-snapshot.entity';
import { AlertSnapshotDto } from '../alerts/dto/alert-snapshot.dto';
import { v4 as uuidv4 } from 'uuid';
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
    metadata: any,
  ): Promise<AlertSnapshotDto> {
    // Check if snapshot already exists
    const existing = await this.snapshotRepository.findOne({
      where: { signalId },
    });

    if (existing) {
      this.logger.debug(`Snapshot already exists for signal ${signalId}`);
      return this.mapToDto(existing);
    }

    // Generate unique filename
    const snapshotId = uuidv4();
    const filename = `${snapshotId}.png`;
    const imagePath = path.join(this.storageDir, filename);

    // Ensure directory exists
    await fs.mkdir(this.storageDir, { recursive: true });

    // Write file to disk
    await fs.writeFile(imagePath, imageBuffer);

    // Save to database
    const snapshot = this.snapshotRepository.create({
      signalId,
      symbol: metadata.symbol,
      timeframe: metadata.timeframe,
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
    return {
      id: entity.id,
      signalId: entity.signalId,
      symbol: entity.symbol,
      timeframe: entity.timeframe,
      imagePath: entity.imagePath,
      imageUrl: `/snapshots/${entity.id}.png`,
      meta: entity.meta,
      createdAt: entity.createdAt,
    };
  }
}
