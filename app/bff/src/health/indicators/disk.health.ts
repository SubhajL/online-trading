import { Injectable } from '@nestjs/common';
import { HealthIndicator, HealthIndicatorResult, HealthCheckError } from '@nestjs/terminus';
import * as os from 'os';
import { promises as fs } from 'fs';
import { execSync } from 'child_process';

interface DiskStorageOptions {
  path: string;
  thresholdPercent: number;
}

@Injectable()
export class DiskHealthIndicator extends HealthIndicator {
  async checkStorage(key: string, options: DiskStorageOptions): Promise<HealthIndicatorResult> {
    try {
      const diskInfo = await this.getDiskInfo(options.path);
      const usedPercent = 100 - (diskInfo.available / diskInfo.total) * 100;

      const thresholdBytes = (diskInfo.total * options.thresholdPercent) / 100;
      const isHealthy = diskInfo.available > diskInfo.total - thresholdBytes;

      const result = this.getStatus(key, isHealthy, {
        status: 'up',
        path: options.path,
        free: diskInfo.available,
        total: diskInfo.total,
        used: diskInfo.used,
        threshold: thresholdBytes,
        usedPercent: Math.round(usedPercent),
      });

      if (!isHealthy) {
        (result[key] as Record<string, unknown>).status = 'degraded';
        result[key].message = `Low disk space: ${Math.round(usedPercent)}% used`;
      } else if (usedPercent > 80) {
        result[key].message = `Disk space usage high: ${Math.round(usedPercent)}%`;
      } else {
        result[key].message = 'Disk space healthy';
      }

      return result;
    } catch (error) {
      throw new HealthCheckError(
        'Disk health check failed',
        this.getStatus(key, false, {
          status: 'down',
          error: (error as Error).message,
          path: options.path,
        }),
      );
    }
  }

  private async getDiskInfo(path: string): Promise<{
    total: number;
    available: number;
    used: number;
  }> {
    // Platform-specific disk space check
    if (os.platform() === 'win32') {
      return this.getWindowsDiskInfo(path);
    } else {
      return this.getUnixDiskInfo(path);
    }
  }

  private async getUnixDiskInfo(path: string): Promise<{
    total: number;
    available: number;
    used: number;
  }> {
    try {
      // Use df command on Unix-like systems
      const output = execSync(`df -k "${path}" | tail -1`, { encoding: 'utf8' });
      const parts = output.trim().split(/\s+/);

      // df output format: filesystem 1K-blocks used available use% mounted
      const total = parseInt(parts[1], 10) * 1024; // Convert from KB to bytes
      const used = parseInt(parts[2], 10) * 1024;
      const available = parseInt(parts[3], 10) * 1024;

      return { total, available, used };
    } catch (error) {
      // Fallback to Node.js statfs (less accurate)
      const stats = await fs.statfs(path);
      return {
        total: stats.blocks * stats.bsize,
        available: stats.bavail * stats.bsize,
        used: (stats.blocks - stats.bfree) * stats.bsize,
      };
    }
  }

  private async getWindowsDiskInfo(path: string): Promise<{
    total: number;
    available: number;
    used: number;
  }> {
    try {
      // Use wmic on Windows
      const drive = path.substring(0, 2); // Extract drive letter
      const output = execSync(
        `wmic logicaldisk where "DeviceID='${drive}'" get Size,FreeSpace /format:value`,
        { encoding: 'utf8' },
      );

      const lines = output.trim().split('\n');
      let total = 0;
      let available = 0;

      for (const line of lines) {
        if (line.startsWith('FreeSpace=')) {
          available = parseInt(line.split('=')[1], 10) || 0;
        } else if (line.startsWith('Size=')) {
          total = parseInt(line.split('=')[1], 10) || 0;
        }
      }

      const used = total - available;
      return { total, available, used };
    } catch (error) {
      // Fallback to Node.js statfs
      const stats = await fs.statfs(path);
      return {
        total: stats.blocks * stats.bsize,
        available: stats.bavail * stats.bsize,
        used: (stats.blocks - stats.bfree) * stats.bsize,
      };
    }
  }
}
