import { Controller, Get, Logger, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { SoakService } from './soak.service';
import { RouterSoakStatusDto } from './dto/soak-status.dto';

@UseGuards(JwtAuthGuard)
@Controller('soak')
export class SoakController {
  private readonly logger = new Logger(SoakController.name);

  constructor(private readonly soakService: SoakService) {}

  @Get('status')
  async getStatus(): Promise<RouterSoakStatusDto> {
    this.logger.debug('Fetching router soak status');
    return this.soakService.getStatus();
  }
}
