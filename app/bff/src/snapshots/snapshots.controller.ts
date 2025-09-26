import { Controller, Get, Param, Res, NotFoundException, Header } from '@nestjs/common';
import { Response } from 'express';
import { SnapshotsService } from './snapshots.service';
import * as fs from 'fs/promises';

@Controller('snapshots')
export class SnapshotsController {
  constructor(private readonly snapshotsService: SnapshotsService) {}

  @Get(':id.png')
  @Header('Content-Type', 'image/png')
  @Header('Cache-Control', 'public, max-age=604800') // 7 days
  async getSnapshot(@Param('id') id: string, @Res() res: Response): Promise<void> {
    const snapshot = await this.snapshotsService.getSnapshot(id);

    if (!snapshot) {
      throw new NotFoundException('Snapshot not found');
    }

    try {
      const imageBuffer = await fs.readFile(snapshot.imagePath);
      res.send(imageBuffer);
    } catch (error) {
      throw new NotFoundException('Snapshot file not found');
    }
  }
}
