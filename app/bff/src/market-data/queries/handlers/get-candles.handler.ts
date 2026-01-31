import { IQueryHandler, QueryHandler } from '@nestjs/cqrs';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetCandlesQuery } from '../get-candles.query';
import { Candle } from '../../../database/entities/candle.entity';

@QueryHandler(GetCandlesQuery)
export class GetCandlesHandler implements IQueryHandler<GetCandlesQuery> {
  constructor(
    @InjectRepository(Candle)
    private readonly candleRepository: Repository<Candle>,
  ) {}

  async execute(query: GetCandlesQuery): Promise<Candle[]> {
    const { symbol, tf, startTime, endTime, limit = 100 } = query;

    const queryBuilder = this.candleRepository
      .createQueryBuilder('candle')
      .where('candle.symbol = :symbol AND candle.timeframe = :timeframe', {
        symbol,
        timeframe: tf,
      });

    if (startTime) {
      queryBuilder.andWhere('candle.open_time >= :startTime', { startTime });
    }

    if (endTime) {
      queryBuilder.andWhere('candle.open_time <= :endTime', { endTime });
    }

    return queryBuilder.orderBy('candle.open_time', 'DESC').limit(limit).getMany();
  }
}
