import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  NotFoundException,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { SignalsService, SignalAlertResponse } from './signals.service';
import { InternalApiGuard } from '../auth/guards/internal-api.guard';
import { SignalPayloadDto } from '../alerts/dto/signal-payload.dto';

@Controller('signals')
@UseGuards(InternalApiGuard)
export class SignalsController {
  constructor(private readonly signalsService: SignalsService) {}

  @Post('alert')
  @HttpCode(HttpStatus.OK)
  async createSignalAlert(@Body() payload: SignalPayloadDto): Promise<SignalAlertResponse> {
    return this.signalsService.createSignalAlert(payload);
  }

  @Get(':signalId/snapshot')
  async getSnapshot(@Param('signalId') signalId: string): Promise<{ imageUrl: string }> {
    const imageUrl = await this.signalsService.getSnapshotUrl(signalId);

    if (!imageUrl) {
      throw new NotFoundException(`Snapshot not found for signal ${signalId}`);
    }

    return { imageUrl };
  }
}
