import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { QueryBus } from '@nestjs/cqrs';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { GetCandlesDto } from './dto/get-candles.dto';
import { GetCandlesQuery } from './queries/get-candles.query';
import { GetIndicatorsQuery } from './queries/get-indicators.query';
import { GetSmcEventsQuery } from './queries/get-smc-events.query';
import { Candle } from '../database/entities/candle.entity';
import { Indicators } from '../database/entities/indicators.entity';
import { SmcEvent } from '../database/entities/smc-events.entity';

@UseGuards(JwtAuthGuard)
@Controller('api/market-data')
export class MarketDataController {
  constructor(private readonly queryBus: QueryBus) {}

  @Get('candles')
  async getCandles(@Query() dto: GetCandlesDto): Promise<Candle[]> {
    const query = new GetCandlesQuery(
      dto.symbol,
      dto.tf,
      dto.startTime ? new Date(dto.startTime) : undefined,
      dto.endTime ? new Date(dto.endTime) : undefined,
      dto.limit,
    );

    return this.queryBus.execute(query);
  }

  @Get('indicators')
  async getIndicators(@Query() dto: GetCandlesDto): Promise<Indicators[]> {
    const query = new GetIndicatorsQuery(
      dto.symbol,
      dto.tf,
      dto.startTime ? new Date(dto.startTime) : undefined,
      dto.endTime ? new Date(dto.endTime) : undefined,
      dto.limit,
    );

    return this.queryBus.execute(query);
  }

  @Get('smc-events')
  async getSmcEvents(
    @Query() dto: GetCandlesDto & { eventTypes?: string[] },
  ): Promise<SmcEvent[]> {
    const query = new GetSmcEventsQuery(
      dto.symbol,
      dto.tf,
      dto.eventTypes,
      dto.startTime ? new Date(dto.startTime) : undefined,
      dto.endTime ? new Date(dto.endTime) : undefined,
      dto.limit,
    );

    return this.queryBus.execute(query);
  }
}