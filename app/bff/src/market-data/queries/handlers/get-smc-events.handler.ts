import { IQueryHandler, QueryHandler } from '@nestjs/cqrs';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { GetSmcEventsQuery } from '../get-smc-events.query';
import { SmcEventV1 } from '../../../database/entities/smc-events-v1.entity';

@QueryHandler(GetSmcEventsQuery)
export class GetSmcEventsHandler implements IQueryHandler<GetSmcEventsQuery> {
  constructor(
    @InjectRepository(SmcEventV1)
    private readonly smcEventV1Repository: Repository<SmcEventV1>,
  ) {}

  async execute(query: GetSmcEventsQuery): Promise<SmcEventV1[]> {
    const { symbol, tf, eventTypes, startTime, endTime, limit = 100 } = query;

    const queryBuilder = this.smcEventV1Repository
      .createQueryBuilder('ev')
      .where('ev.symbol = :symbol AND ev.timeframe = :timeframe', {
        symbol,
        timeframe: tf,
      });

    if (eventTypes && eventTypes.length > 0) {
      queryBuilder.andWhere('ev.event_type IN (:...eventTypes)', { eventTypes });
    }

    if (startTime) {
      queryBuilder.andWhere('ev.event_time >= :startTime', { startTime });
    }

    if (endTime) {
      queryBuilder.andWhere('ev.event_time <= :endTime', { endTime });
    }

    return queryBuilder.orderBy('ev.event_time', 'DESC').limit(limit).getMany();
  }
}
