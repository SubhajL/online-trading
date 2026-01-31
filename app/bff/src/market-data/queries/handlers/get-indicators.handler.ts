import { IQueryHandler, QueryHandler } from '@nestjs/cqrs';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetIndicatorsQuery } from '../get-indicators.query';
import { Indicators } from '../../../database/entities/indicators.entity';

@QueryHandler(GetIndicatorsQuery)
export class GetIndicatorsHandler implements IQueryHandler<GetIndicatorsQuery> {
  constructor(
    @InjectRepository(Indicators)
    private readonly indicatorsRepository: Repository<Indicators>,
  ) {}

  async execute(query: GetIndicatorsQuery): Promise<Indicators[]> {
    const { symbol, tf, startTime, endTime, limit = 100 } = query;

    const queryBuilder = this.indicatorsRepository
      .createQueryBuilder('indicators')
      .where('indicators.symbol = :symbol AND indicators.timeframe = :timeframe', {
        symbol,
        timeframe: tf,
      });

    if (startTime) {
      queryBuilder.andWhere('indicators.timestamp >= :startTime', { startTime });
    }

    if (endTime) {
      queryBuilder.andWhere('indicators.timestamp <= :endTime', { endTime });
    }

    return queryBuilder.orderBy('indicators.timestamp', 'DESC').limit(limit).getMany();
  }
}
