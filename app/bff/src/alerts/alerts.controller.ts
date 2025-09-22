import {
  Controller,
  Get,
  Put,
  Delete,
  Param,
  Query,
  Res,
  UseGuards,
  HttpCode,
  HttpStatus,
} from '@nestjs/common';
import { Response } from 'express';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { AlertsService } from './alerts.service';
import {
  Alert,
  AlertFilters,
  AlertStats,
  PaginatedAlertsDto,
  SearchAlertsDto,
  UpdateCountDto,
  UnreadCountDto,
} from './dto/alert.dto';

@Controller('api/alerts')
@UseGuards(JwtAuthGuard)
export class AlertsController {
  constructor(private readonly alertsService: AlertsService) {}

  @Get()
  async findAll(
    @Query('page') page = 1,
    @Query('limit') limit = 20,
    @Query() filters: AlertFilters,
  ): Promise<PaginatedAlertsDto> {
    return this.alertsService.findAll(+page, +limit, filters);
  }

  @Get('stats')
  async getStats(): Promise<AlertStats> {
    return this.alertsService.getStats();
  }

  @Get('unread-count')
  async getUnreadCount(): Promise<UnreadCountDto> {
    return this.alertsService.getUnreadCount();
  }

  @Get('search')
  async search(
    @Query('q') query: string,
    @Query('limit') limit = 50,
  ): Promise<SearchAlertsDto> {
    return this.alertsService.search(query, +limit);
  }

  @Get('export')
  async export(
    @Query('format') format: 'csv' | 'json',
    @Query() filters: AlertFilters,
    @Res() res: Response,
  ): Promise<void> {
    const data = await this.alertsService.export(format, filters);

    const contentType = format === 'csv' ? 'text/csv' : 'application/json';
    const filename = `alerts.${format}`;

    res.set({
      'Content-Type': contentType,
      'Content-Disposition': `attachment; filename="${filename}"`,
    });
    res.send(data);
  }

  @Get(':id')
  async findOne(@Param('id') id: string): Promise<Alert> {
    return this.alertsService.findOne(id);
  }

  @Put(':id/read')
  @HttpCode(HttpStatus.OK)
  async markAsRead(@Param('id') id: string): Promise<Alert> {
    return this.alertsService.markAsRead(id);
  }

  @Put('read-all')
  @HttpCode(HttpStatus.OK)
  async markAllAsRead(): Promise<UpdateCountDto> {
    return this.alertsService.markAllAsRead();
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async delete(@Param('id') id: string): Promise<void> {
    await this.alertsService.delete(id);
  }
}