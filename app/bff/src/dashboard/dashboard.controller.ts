import { Controller, Get, UseGuards, Logger } from '@nestjs/common';
import { DashboardService } from './dashboard.service';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { DashboardSnapshotDto } from './dto/dashboard.dto';

@UseGuards(JwtAuthGuard)
@Controller('dashboard')
export class DashboardController {
  private readonly logger = new Logger(DashboardController.name);

  constructor(private readonly dashboardService: DashboardService) {}

  @Get('snapshot')
  async getSnapshot(): Promise<DashboardSnapshotDto> {
    this.logger.debug('Fetching dashboard snapshot');
    return this.dashboardService.getSnapshot();
  }
}
