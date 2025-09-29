import {
  Controller,
  Get,
  Post,
  Body,
  Param,
  HttpCode,
  HttpStatus,
  UseGuards,
} from '@nestjs/common';
import { AuthGuard } from '@nestjs/passport';
import { SignalsService } from './signals.service';
import { CreateSignalAlertDto } from './dto/create-signal-alert.dto';

@Controller('api/signals')
export class SignalsController {
  constructor(private readonly signalsService: SignalsService) {}

  @Post('alert')
  @UseGuards(AuthGuard('api-key'))
  @HttpCode(HttpStatus.CREATED)
  async createAlert(@Body() createSignalAlertDto: CreateSignalAlertDto) {
    const result = await this.signalsService.createAlert(createSignalAlertDto);
    return {
      success: true,
      signalId: result.signalId,
      message: 'Signal alert queued for processing',
    };
  }

  @Get(':signalId/snapshot')
  @UseGuards(AuthGuard('api-key'))
  async getSnapshot(@Param('signalId') signalId: string) {
    const snapshot = await this.signalsService.getSnapshot(signalId);
    return {
      ...snapshot,
      imageUrl: `/uploads/snapshots/${signalId}.png`,
    };
  }
}
